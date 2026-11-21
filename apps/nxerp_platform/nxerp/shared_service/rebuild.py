"""Backfill and rebuild: one code path for the first fill and for disaster recovery. No frappe, no access to any owner's database.

	rebuild(source):  1. mark the source's cursor `rebuilding` (the projector leaves it alone)
	                  2. wait (up to relay_wait) for the owner's relay to sequence what is pending, then record start_seq = the feed's head
	                  3. stream a snapshot of every entity the feed serves and write it with the owner-truth rule
	                  4. tombstone shared rows the owner no longer has
	                  5. set the cursor to start_seq and make it live, then replay the events after start_seq through the projector's own
	                     apply path (changes made while the snapshot was streaming arrive here and converge by version stamp)
	                  6. run a full compare and report its drift

The shared database can be dropped, migrated again and rebuilt with this one command. An interrupted rebuild leaves the source in
`rebuilding`; running the command again starts over and is safe (every write is idempotent). The report holds counts, never values.
"""

import logging
import time

from nxerp.shared_service import apply, config
from nxerp.shared_service.feedclient import FeedClient, FeedRejected
from nxerp.shared_service.metrics import Metrics
from nxerp.shared_service.projector import Projector
from nxerp.shared_service.reconcile import Reconciler, active_contracts, tenant_for
from nxerp.shared_service.schema.generate_columns import table_name
from nxerp.shared_service.sqlutil import select

log = logging.getLogger("nxerp.shared")


class RebuildError(RuntimeError):
	"""A rebuild stopped part way; the source stays in `rebuilding` and the command can be run again."""

	def __init__(self, message: str, report: dict):
		super().__init__(message)
		self.report = report


def rebuild(
	connect,
	sources: list,
	only: str | None = None,
	client_factory=None,
	metrics: Metrics | None = None,
	page: int = 500,
	relay_wait: float = 90.0,
	sleep=time.sleep,
	clock=time.monotonic,
) -> dict:
	client_factory = client_factory or (lambda source: FeedClient(source, config.read_key(source)))
	metrics = metrics or Metrics()
	report = {"sources": {}}
	for source in sources:
		if only and source.app_key != only:
			continue
		report["sources"][source.app_key] = _rebuild_source(
			connect, source, client_factory, metrics, page, relay_wait, sleep, clock, report
		)
	conn = connect()
	try:
		metrics.flush(conn)
	finally:
		conn.close()
	return report


def _wait_for_relay(client, relay_wait: float, sleep, clock) -> dict:
	deadline = clock() + relay_wait
	while True:
		head = client.head()
		if head.get("pending_count", 0) == 0 or clock() >= deadline:
			return head
		sleep(2)


def _rebuild_source(connect, source, client_factory, metrics, page, relay_wait, sleep, clock, report) -> dict:
	key = source.app_key
	result = {"status": "ok", "entities": {}}
	conn = connect()
	try:
		client = client_factory(source)
		apply.record_contracts(conn)
		with conn.cursor() as cur:
			apply.set_state(cur, key, "rebuilding")
		conn.commit()
		result["start_seq"] = start_seq = _wait_for_relay(client, relay_wait, sleep, clock)["max_seq"]
		for contract in active_contracts():
			try:
				counts = _snapshot_entity(conn, client, contract, start_seq, page)
			except FeedRejected as exc:
				if exc.status == 422:  # this feed does not serve the entity
					continue
				raise
			result["entities"][contract["entity_type"]] = counts
		with conn.cursor() as cur:
			apply.set_cursor(cur, key, start_seq, None, state="live")
		conn.commit()
	except Exception as exc:
		conn.rollback()
		result["status"] = "interrupted"
		result["error"] = type(exc).__name__
		report["sources"][key] = result
		raise RebuildError(
			f"rebuild of {key} stopped ({type(exc).__name__}); it can be run again", report
		) from exc
	finally:
		conn.close()
	projector = Projector(connect, [source], client_factory=client_factory, metrics=metrics, batch_size=page)
	try:
		result["replayed"] = projector.sync_source(source)
	finally:
		projector.reset_connection()
	check = Reconciler(connect, [source], client_factory=client_factory, metrics=metrics, page=page).run(
		"full", only=key
	)
	result["drift_after"] = check["drift"]
	result["dead_letters"] = _unresolved_dead_letters(connect, key)
	metrics.set(key, "rebuilt_rows", sum(c["snapshot_rows"] for c in result["entities"].values()))
	metrics.mark_success(key)
	metrics.set(key, "rebuilt_at", time.time())
	return result


def _unresolved_dead_letters(connect, key: str) -> int:
	conn = connect()
	try:
		with conn.cursor() as cur:
			cur.execute(
				"SELECT COUNT(*) AS n FROM sync_dead_letter WHERE source_app = %s AND resolved_at IS NULL",
				(key,),
			)
			return int(cur.fetchone()["n"])
	finally:
		conn.close()


def _snapshot_entity(conn, client, contract: dict, start_seq: int, page: int) -> dict:
	entity_type = contract["entity_type"]
	allowed = set(apply.field_names(contract))
	seen, refused, after = set(), 0, ""
	while True:
		answer = client.snapshot(entity_type, after_id=after, limit=page)
		with conn.cursor() as cur:
			for item in answer["items"]:
				seen.add(item["entity_id"])
				if set(item["payload"]) - allowed:  # never write a field outside the contract
					refused += 1
					continue
				apply.apply_row(
					cur,
					contract,
					source_app=contract["owner_app"],
					entity_id=item["entity_id"],
					tenant_id=tenant_for(contract, item["entity_id"]),
					payload=item["payload"],
					source_modified=item["source_modified"],
					last_seq=start_seq,
					contract_version=contract["contract_version"],
					force=True,
				)
		conn.commit()
		after = answer["next_after_id"]
		if not after:
			break
	tombstoned = _tombstone_missing(conn, contract, seen)
	return {"snapshot_rows": len(seen) - refused, "tombstoned": tombstoned, "refused": refused}


def _tombstone_missing(conn, contract: dict, seen: set) -> int:
	"""Shared rows of this entity the owner no longer has become tombstones (the owner is the truth)."""
	with conn.cursor() as cur:
		cur.execute(
			select(
				table_name(contract["entity_type"]),
				["entity_id", "source_modified", "last_seq"],
				where="`source_app` = %s AND `deleted_at` IS NULL",
			),
			(contract["owner_app"],),
		)
		stale = [row for row in cur.fetchall() if row["entity_id"] not in seen]
		for row in stale:
			apply.apply_row(
				cur,
				contract,
				source_app=contract["owner_app"],
				entity_id=row["entity_id"],
				tenant_id=tenant_for(contract, row["entity_id"]),
				payload=None,
				source_modified=row["source_modified"].strftime("%Y-%m-%d %H:%M:%S.%f"),
				last_seq=row["last_seq"],
				contract_version=contract["contract_version"],
				deleted=True,
				force=True,
			)
	conn.commit()
	return len(stale)
