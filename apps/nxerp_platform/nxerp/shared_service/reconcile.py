"""The reconciler: finds and repairs drift between an owner and the shared layer. No frappe, no access to any owner's database.

The outbox cannot see a change made without a document event (`frappe.db.set_value`, raw SQL), so the shared layer is also compared
with the owners:

	recent  hourly   the owner's digest of documents modified since the last scan (minus 5 minutes): missing and stale rows
	full    nightly  the owner's complete digest (id, version stamp, payload hash) against every shared row: missing, extra, stale
	                 (the owner's stamp is newer), hash mismatch (same stamp, different content: a change made without an event)

Repair always copies owner to shared, never the reverse, with the owner-truth rule of `apply.py` (applied when the owner's stamp is not
older than ours). A row the owner no longer has becomes a tombstone (never an owner change). A repair that would write a field outside the
contract is refused and reported. An unreachable or rejecting owner is skipped and reported: its rows are never marked extra.

The compare holds one entity type's rows in memory (ids, stamps, hashes): fine for reference data of this size.
The report holds ids and counts, never values.
"""

import calendar
import logging
import time
from datetime import UTC, datetime, timezone

from nxerp.shared import payload as payload_module
from nxerp.shared import registry
from nxerp.shared_service import apply, config, sqlutil
from nxerp.shared_service.feedclient import FeedClient, FeedRejected, FeedUnavailable
from nxerp.shared_service.metrics import Metrics
from nxerp.shared_service.schema.generate_columns import table_name

log = logging.getLogger("nxerp.shared")

REPORT_ID_LIMIT = 50
RECENT_OVERLAP_SECONDS = 300
REPAIR_BATCH = 200
HASH_GUARD_MIN_ROWS = 10
HASH_GUARD_RATIO = 0.9
CATEGORIES = ("missing", "extra", "stale", "hash_mismatch", "ahead")


class HashFunctionMismatch(RuntimeError):
	"""Almost every row differs although the version stamps agree: the owner and the shared service do not hash the same way."""


def tenant_for(contract: dict, entity_id: str) -> str:
	tenant = contract["tenant"]
	return tenant["value"] if tenant["mode"] == "constant" else entity_id


def _stamp(value) -> str:
	return value.strftime(payload_module.DATETIME_FORMAT) if hasattr(value, "strftime") else str(value)


def _epoch(stamp: str) -> int:
	"""A version stamp as a number, by calendar arithmetic only: the owner's local time stays consistent with itself."""
	return calendar.timegm(datetime.strptime(stamp[:19], "%Y-%m-%d %H:%M:%S").timetuple())


def _stamp_from_epoch(epoch: float) -> str:
	return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%d %H:%M:%S")


def active_contracts() -> list:
	return [c for c in registry.load_contracts().values() if c["status"] == "active"]


class Reconciler:
	def __init__(
		self,
		connect,
		sources: list,
		client_factory=None,
		metrics: Metrics | None = None,
		page: int = 500,
		clock=time.time,
	):
		self._connect = connect
		self.sources = sources
		self._client_factory = client_factory or (lambda source: FeedClient(source, config.read_key(source)))
		self.metrics = metrics or Metrics()
		self.page = page
		self._clock = clock

	def run(self, mode: str = "full", only: str | None = None) -> dict:
		"""Compare every source (or one) and repair what differs. Returns the report."""
		if mode not in ("recent", "full"):
			raise ValueError("mode must be recent or full")
		report = {"mode": mode, "sources": {}, "drift": 0, "repaired": 0, "refused": 0}
		conn = self._connect()
		try:
			for source in self.sources:
				if only and source.app_key != only:
					continue
				report["sources"][source.app_key] = self._source(conn, source, mode)
			for result in report["sources"].values():
				for counts in result.get("entities", {}).values():
					report["drift"] += sum(counts[c] for c in CATEGORIES if c != "ahead")
					report["repaired"] += counts["repaired"]
					report["refused"] += counts["refused"]
			self.metrics.flush(conn)
		finally:
			conn.close()
		return report

	# ---- one source ----------------------------------------------------------------------------------

	def _source(self, conn, source, mode: str) -> dict:
		client = self._client_factory(source)
		result = {"status": "ok", "entities": {}}
		watermark = self._read_watermark(conn, source.app_key) if mode == "recent" else None
		since = _stamp_from_epoch(watermark - RECENT_OVERLAP_SECONDS) if watermark else None
		newest = watermark or 0
		drift = 0
		try:
			for contract in active_contracts():
				try:
					counts, seen = self._entity(conn, source, client, contract, mode, since)
				except FeedRejected as exc:
					if exc.status == 422:  # this feed does not serve the entity (its owner app is elsewhere)
						continue
					raise
				result["entities"][contract["entity_type"]] = counts
				drift += sum(counts[c] for c in CATEGORIES if c != "ahead")
				newest = max(newest, seen)
		except FeedUnavailable as exc:
			result = {"status": "unreachable", "error": type(exc).__name__, "entities": result["entities"]}
			log.warning("reconcile: source %s is unreachable; its rows were left alone", source.app_key)
		except FeedRejected as exc:
			result = {"status": "rejected", "http": exc.status, "entities": result["entities"]}
			log.error(
				"reconcile: source %s rejected the request (HTTP %s); its rows were left alone",
				source.app_key,
				exc.status,
			)
		if result["status"] == "ok":
			self.metrics.set(source.app_key, "reconcile_drift", drift)
			self.metrics.set(source.app_key, "last_reconcile_at", self._clock())
			if mode == "recent" and newest:
				self.metrics.set(source.app_key, "recent_watermark", newest)
		return result

	def _read_watermark(self, conn, source: str):
		with conn.cursor() as cur:
			cur.execute(
				"SELECT value FROM sync_metric WHERE source = %s AND name = 'recent_watermark'", (source,)
			)
			row = cur.fetchone()
		conn.commit()
		return row["value"] if row else None

	# ---- one entity ----------------------------------------------------------------------------------

	def _owner_digest(self, client, entity_type: str, since: str | None) -> dict:
		items, after = {}, ""
		while True:
			page = client.digest(entity_type, modified_since=since, after_id=after, limit=self.page)
			for item in page["items"]:
				items[item["entity_id"]] = (item["source_modified"], item["payload_hash"])
			after = page["next_after_id"]
			if not after:
				return items

	def _shared_rows(self, conn, contract: dict) -> dict:
		columns = ["entity_id", "source_modified", "last_seq", "deleted_at", *apply.field_names(contract)]
		with conn.cursor() as cur:
			cur.execute(
				sqlutil.select(table_name(contract["entity_type"]), columns, where="`source_app` = %s"),
				(contract["owner_app"],),
			)
			rows = {row["entity_id"]: row for row in cur.fetchall()}
		conn.commit()
		return rows

	def _entity(self, conn, source, client, contract: dict, mode: str, since: str | None) -> tuple:
		entity_type = contract["entity_type"]
		owner = self._owner_digest(client, entity_type, since)
		shared = self._shared_rows(conn, contract)
		found = {c: [] for c in CATEGORIES}
		compared_equal_stamp = mismatched_equal_stamp = 0
		for entity_id, (owner_stamp, owner_hash) in owner.items():
			row = shared.get(entity_id)
			if row is None or row["deleted_at"] is not None:
				found["missing"].append(entity_id)
				continue
			shared_stamp = _stamp(row["source_modified"])
			if owner_stamp > shared_stamp:
				found["stale"].append(entity_id)
			elif owner_stamp < shared_stamp:
				found["ahead"].append(
					entity_id
				)  # shared newer than the owner: reported, never repaired (the owner is the truth, but this is odd)
			else:
				compared_equal_stamp += 1
				if apply.row_hash(contract, row) != owner_hash:
					found["hash_mismatch"].append(entity_id)
					mismatched_equal_stamp += 1
		if mode == "full":
			found["extra"] = sorted(
				i for i, row in shared.items() if row["deleted_at"] is None and i not in owner
			)
		if (
			compared_equal_stamp >= HASH_GUARD_MIN_ROWS
			and mismatched_equal_stamp / compared_equal_stamp >= HASH_GUARD_RATIO
		):
			raise HashFunctionMismatch(
				f"{entity_type}: {mismatched_equal_stamp} of {compared_equal_stamp} rows with equal stamps differ in hash: "
				"the owner and the shared service do not compute the same payload hash"
			)
		repaired, refused = self._repair(conn, source, client, contract, found, shared)
		counts = {
			"owner": len(owner),
			"shared": sum(1 for row in shared.values() if row["deleted_at"] is None),
			**{c: len(found[c]) for c in CATEGORIES},
			"repaired": repaired,
			"refused": len(refused),
			"ids": {c: found[c][:REPORT_ID_LIMIT] for c in CATEGORIES if found[c]},
		}
		if refused:
			counts["refused_ids"] = refused[:REPORT_ID_LIMIT]
		newest = max((_epoch(stamp) for stamp, _ in owner.values()), default=0)
		return counts, newest

	# ---- repair: owner to shared, never the reverse -------------------------------------------------

	def _repair(self, conn, source, client, contract: dict, found: dict, shared: dict) -> tuple:
		entity_type = contract["entity_type"]
		allowed = set(apply.field_names(contract))
		repaired, refused = 0, []
		to_fetch = found["missing"] + found["stale"] + found["hash_mismatch"]
		for start in range(0, len(to_fetch), REPAIR_BATCH):
			batch = to_fetch[start : start + REPAIR_BATCH]
			answer = client.snapshot_by_ids(entity_type, batch)
			with conn.cursor() as cur:
				for item in answer["items"]:
					extra = set(item["payload"]) - allowed
					if extra:  # a repair never writes a field outside the contract
						refused.append(item["entity_id"])
						log.error(
							"reconcile: refused to repair %s %s: the owner sent fields outside the contract",
							entity_type,
							item["entity_id"],
						)
						continue
					previous = shared.get(item["entity_id"])
					apply.apply_row(
						cur,
						contract,
						source_app=contract["owner_app"],
						entity_id=item["entity_id"],
						tenant_id=tenant_for(contract, item["entity_id"]),
						payload=item["payload"],
						source_modified=item["source_modified"],
						last_seq=previous["last_seq"] if previous else 0,
						contract_version=contract["contract_version"],
						force=True,
					)
					repaired += 1
			conn.commit()
		if found["extra"]:
			with conn.cursor() as cur:
				for entity_id in found["extra"]:
					row = shared[entity_id]
					apply.apply_row(
						cur,
						contract,
						source_app=contract["owner_app"],
						entity_id=entity_id,
						tenant_id=tenant_for(contract, entity_id),
						payload=None,
						source_modified=_stamp(row["source_modified"]),
						last_seq=row["last_seq"],
						contract_version=contract["contract_version"],
						deleted=True,
						force=True,
					)
					repaired += 1
			conn.commit()
		return repaired, refused


class Schedule:
	"""When the reconciler runs: a recent scan every `recent_every` seconds, a full compare once a day at `full_hour` (UTC)."""

	def __init__(self, recent_every: int = 3600, full_hour: int = 3):
		self.recent_every = recent_every
		self.full_hour = full_hour
		self.last_recent: float | None = None
		self.last_full_day: str | None = None

	def due(self, now: float) -> list:
		"""The modes to run now, full first (a full compare covers a recent scan)."""
		moment = datetime.fromtimestamp(now, UTC)
		today = moment.strftime("%Y-%m-%d")
		if moment.hour >= self.full_hour and self.last_full_day != today:
			return ["full"]
		if self.last_recent is None or now - self.last_recent >= self.recent_every:
			return ["recent"]
		return []

	def done(self, mode: str, now: float) -> None:
		self.last_recent = now
		if mode == "full":
			self.last_full_day = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")


def run_schedule(
	reconciler: Reconciler, schedule: Schedule, clock=time.time, sleep=time.sleep, stop=lambda: False
) -> None:
	"""The reconciler process: wake up every minute, run what is due. A failed run is logged and tried again at the next due time."""
	log.info(
		"reconciler started: recent every %s s, full at %02d:00 UTC",
		schedule.recent_every,
		schedule.full_hour,
	)
	while not stop():
		now = clock()
		for mode in schedule.due(now):
			try:
				report = reconciler.run(mode)
				log.info(
					"reconcile %s: drift %s, repaired %s, refused %s",
					mode,
					report["drift"],
					report["repaired"],
					report["refused"],
				)
			except Exception as exc:  # a failure must not end the process
				log.error("reconcile %s failed: %s", mode, type(exc).__name__)
			schedule.done(mode, now)
		sleep(60)
