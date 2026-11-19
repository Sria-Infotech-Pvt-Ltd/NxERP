"""The projector: the only writer of the shared database. No frappe, no access to any owner's database.

For each source (an owner's feed) it pulls events after the stored cursor, checks them, applies them with the version rule in ONE
transaction together with the cursor update, and only then acknowledges them to the owner:

	pull -> validate -> (resync: fetch the entity) -> apply + cursor in one transaction -> commit -> ack

Guarantees (blueprint 2.6): at-least-once delivery, idempotent apply (a replay changes nothing), per-source order by `seq`,
per-entity order by version stamp, rows and cursor atomic, resumable after any crash, and the cursor never advances past an event
that was not applied except by dead-lettering it (reason recorded, counted, alerted). A gap in the sequence stops that source.

Sources are independent: a source that fails backs off (1, 2, 4 ... 60 seconds) without delaying the others; a source the owner
rejects (a wrong key) is stopped and retried only every five minutes, so it cannot spin. Logs carry ids and counts, never payload values.
"""

import logging
import re
import time

from nxerp.shared import registry
from nxerp.shared_service import apply, config
from nxerp.shared_service.feedclient import FeedClient, FeedRejected, FeedUnavailable
from nxerp.shared_service.metrics import Metrics

log = logging.getLogger("nxerp.shared")

BATCH_SIZE = 500
MAX_ATTEMPTS = 5
BACKOFF_CAP = 60
REJECTED_RETRY_SECONDS = 300
IDLE_HEAD_CHECK_SECONDS = 60
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{1,6})?$")
TRANSIENT_DB_CODES = {1205, 1213, 2003, 2006, 2013, 2055}  # lock wait, deadlock, connection lost
DATA_ERRORS = ("DataError", "IntegrityError", "DataError", "ProgrammingError", "NotSupportedError")


def backoff_seconds(failures: int) -> int:
	"""1, 2, 4, 8 ... capped at 60 for failure number 0, 1, 2 ..."""
	return min(BACKOFF_CAP, 2 ** max(0, failures))


class TransientDbError(RuntimeError):
	"""A database error worth retrying (connection lost, lock wait, deadlock): roll back, back off, never ack."""


def _is_transient(exc: Exception) -> bool:
	return type(exc).__module__.startswith("pymysql") and bool(exc.args) and exc.args[0] in TRANSIENT_DB_CODES


def _is_data_error(exc: Exception) -> bool:
	return type(exc).__module__.startswith("pymysql") and type(exc).__name__ in DATA_ERRORS


def validate_event(event) -> list:
	"""Everything wrong with one envelope, judged against the contracts and the column sizes (empty list = applicable)."""
	if not isinstance(event, dict):
		return ["the event is not an object"]
	problems = registry.event_problems(event)
	if problems:
		return problems
	if isinstance(event["seq"], bool) or not isinstance(event["seq"], int) or event["seq"] < 1:
		problems.append("seq must be a positive integer")
	for key, size in (("event_id", 64), ("entity_id", 140), ("tenant_id", 64), ("source_app", 64)):
		value = event[key]
		if not isinstance(value, str) or not value or len(value) > size:
			problems.append(f"{key} is empty, not text or longer than {size}")
	if not isinstance(event["source_modified"], str) or not STAMP.fullmatch(event["source_modified"]):
		problems.append("source_modified is not a datetime")
	if event["op"] == "upsert" and isinstance(event["payload"], dict):
		contract = registry.get_contract(event["entity_type"])
		for field in contract["fields"]:
			value = event["payload"].get(field["shared"])
			if (
				field["type"] == "string"
				and isinstance(value, str)
				and len(value) > field.get("max_length", 140)
			):
				problems.append(f"payload field {field['shared']} is longer than its column")
	return problems


class SourceRuntime:
	def __init__(self):
		self.failures = 0
		self.next_run = 0.0
		self.pending_ack: int | None = None
		self.last_head_check = 0.0
		self.rejected_reason: str | None = None


class Projector:
	def __init__(
		self,
		connect,
		sources: list,
		client_factory=None,
		metrics: Metrics | None = None,
		batch_size: int = BATCH_SIZE,
		clock=time.monotonic,
		sleep=time.sleep,
	):
		self._connect = connect
		self.sources = sources
		self._client_factory = client_factory or (lambda source: FeedClient(source, config.read_key(source)))
		self.metrics = metrics or Metrics()
		self.batch_size = batch_size
		self._clock = clock
		self._sleep = sleep
		self._conn = None
		self._clients: dict = {}
		self.runtime = {source.app_key: SourceRuntime() for source in sources}
		self.before_commit = None  # test hook: called after the statements, before the commit
		self.stopping = False

	# ---- connections ---------------------------------------------------------------------------------

	def conn(self):
		if self._conn is None:
			self._conn = self._connect()
		else:
			try:
				self._conn.ping(reconnect=True)
			except Exception:
				self.reset_connection()
				self._conn = self._connect()
		return self._conn

	def reset_connection(self) -> None:
		if self._conn is not None:
			try:
				self._conn.close()
			except Exception as exc:
				log.debug("closing the old database connection failed: %s", type(exc).__name__)
		self._conn = None

	def client(self, source):
		if source.app_key not in self._clients:
			self._clients[source.app_key] = self._client_factory(source)
		return self._clients[source.app_key]

	# ---- one source ----------------------------------------------------------------------------------

	def sync_source(self, source) -> int:
		"""Pull and apply until the source is caught up. Returns how many events were consumed (applied, skipped or dead-lettered)."""
		client = self.client(source)
		runtime = self.runtime[source.app_key]
		total = 0
		while not self.stopping:
			conn = self.conn()
			with conn.cursor() as cur:
				cursor = apply.get_cursor(cur, source.app_key)
			conn.commit()
			if cursor["state"] != "live":
				self.metrics.set(source.app_key, "gap", 1 if cursor["state"] == "gap" else 0)
				return total
			self._retry_ack(client, source, runtime)
			events = client.pull(cursor["last_seq"], self.batch_size)["events"]
			if not events:
				self._idle(client, source, runtime, cursor["last_seq"])
				break
			expected, usable = cursor["last_seq"] + 1, []
			for event in events:
				if not isinstance(event, dict) or event.get("seq") != expected:
					break
				usable.append(event)
				expected += 1
			if usable:
				total += self._consume(client, source, runtime, usable)
			if len(usable) < len(events):
				self._mark_gap(source, expected, events[len(usable)])
				break
			if len(events) < self.batch_size:
				break
		return total

	def _idle(self, client, source, runtime, last_seq: int) -> None:
		"""Nothing to pull: report no lag, and now and then check the owner's feed has not gone back behind our cursor."""
		self.metrics.set(source.app_key, "lag_seconds", 0)
		self.metrics.mark_success(source.app_key)
		now = self._clock()
		if now - runtime.last_head_check >= IDLE_HEAD_CHECK_SECONDS:
			runtime.last_head_check = now
			head = client.head()
			if head.get("max_seq", 0) < last_seq:
				log.error(
					"source %s: the owner's feed head %s is behind our cursor %s",
					source.app_key,
					head.get("max_seq"),
					last_seq,
				)
				self._set_state(source, "gap")
				self.metrics.set(source.app_key, "gap", 1)

	def _mark_gap(self, source, expected: int, got) -> None:
		seen = got.get("seq") if isinstance(got, dict) else None
		log.error(
			"source %s: sequence gap, expected seq %s and got %s: the source is stopped (run a rebuild)",
			source.app_key,
			expected,
			seen,
		)
		self._set_state(source, "gap")
		self.metrics.set(source.app_key, "gap", 1)

	def _set_state(self, source, state: str) -> None:
		conn = self.conn()
		with conn.cursor() as cur:
			apply.set_state(cur, source.app_key, state)
		conn.commit()

	def _retry_ack(self, client, source, runtime) -> None:
		if runtime.pending_ack is None:
			return
		try:
			client.ack(runtime.pending_ack)
			runtime.pending_ack = None
		except FeedUnavailable:
			log.warning(
				"source %s: the acknowledgement of seq %s is still pending",
				source.app_key,
				runtime.pending_ack,
			)

	# ---- applying ------------------------------------------------------------------------------------

	def _consume(self, client, source, runtime, events: list) -> int:
		prepared = [self._prepare(client, event) for event in events]
		last = events[-1]
		counts = self._write_batch(source, prepared, events)
		self.metrics.inc(source.app_key, "applied", counts["applied"])
		self.metrics.inc(source.app_key, "skipped_old", counts["skipped"])
		self.metrics.inc(source.app_key, "dead_letters", counts["dead"])
		self.metrics.mark_success(source.app_key)
		try:
			lag = client.head().get(
				"oldest_pending_age_seconds", 0
			)  # before the ack: how long the oldest event waited
			self.metrics.set(source.app_key, "lag_seconds", lag)
		except FeedUnavailable:
			pass
		try:
			client.ack(last["seq"])
			runtime.pending_ack = None
		except FeedUnavailable:
			runtime.pending_ack = last["seq"]
			log.warning(
				"source %s: could not acknowledge seq %s now, will retry", source.app_key, last["seq"]
			)
		return len(events)

	def _prepare(self, client, event: dict) -> tuple:
		"""('apply', event, None) | ('dead', event, reason). A resync becomes an upsert (or a delete) read from the owner first."""
		problems = validate_event(event)
		if problems:
			return ("dead", event, "; ".join(problems)[:1000])
		if event["op"] != "resync":
			return ("apply", event, None)
		answer = client.snapshot_by_ids(event["entity_type"], [event["entity_id"]])
		if answer.get("items"):
			item = answer["items"][0]
			resolved = {
				**event,
				"op": "upsert",
				"payload": item["payload"],
				"source_modified": item["source_modified"],
			}
			problems = validate_event(resolved)
			return ("dead", event, "; ".join(problems)[:1000]) if problems else ("apply", resolved, None)
		return ("apply", {**event, "op": "delete", "payload": None}, None)

	def _write_batch(self, source, prepared: list, events: list) -> dict:
		conn = self.conn()
		last = events[-1]
		try:
			counts = self._write(conn, source, prepared, last)
			if self.before_commit:
				self.before_commit()
			conn.commit()
			return counts
		except Exception as exc:
			conn.rollback()
			if _is_transient(exc):
				self.reset_connection()
				raise TransientDbError(f"database error {exc.args[0]}") from exc
			if not _is_data_error(exc):
				raise
		return self._write_one_by_one(source, prepared)

	def _write(self, conn, source, prepared: list, last: dict) -> dict:
		counts = {"applied": 0, "skipped": 0, "dead": 0}
		with conn.cursor() as cur:
			for kind, event, reason in prepared:
				if kind == "dead":
					apply.dead_letter(cur, source.app_key, event, reason)
					counts["dead"] += 1
				else:
					self._apply_event(cur, event, counts)
			apply.set_cursor(cur, source.app_key, last["seq"], last.get("event_id"))
		return counts

	def _apply_event(self, cur, event: dict, counts: dict) -> None:
		contract = registry.get_contract(event["entity_type"])
		changed = apply.apply_row(
			cur,
			contract,
			source_app=event["source_app"],
			entity_id=event["entity_id"],
			tenant_id=event["tenant_id"],
			payload=event["payload"],
			source_modified=event["source_modified"],
			last_seq=event["seq"],
			contract_version=event["contract_version"],
			deleted=event["op"] == "delete",
		)
		counts["applied" if changed else "skipped"] += 1

	def _write_one_by_one(self, source, prepared: list) -> dict:
		"""A batch hit a data error: apply each event alone, retry it up to MAX_ATTEMPTS, then dead-letter it and go on."""
		counts = {"applied": 0, "skipped": 0, "dead": 0}
		conn = self.conn()
		for kind, event, reason in prepared:
			attempts = 0
			while True:
				attempts += 1
				try:
					with conn.cursor() as cur:
						if kind == "dead":
							apply.dead_letter(cur, source.app_key, event, reason)
							counts["dead"] += 1
						else:
							self._apply_event(cur, event, counts)
						apply.set_cursor(cur, source.app_key, event["seq"], event.get("event_id"))
					conn.commit()
					break
				except Exception as exc:
					conn.rollback()
					if _is_transient(exc) or not _is_data_error(exc):
						self.reset_connection()
						raise
					if attempts >= MAX_ATTEMPTS:
						with conn.cursor() as cur:
							apply.dead_letter(
								cur,
								source.app_key,
								event,
								f"{type(exc).__name__} after {attempts} attempts",
								attempts,
							)
							apply.set_cursor(cur, source.app_key, event["seq"], event.get("event_id"))
						conn.commit()
						counts["dead"] += 1
						break
		return counts

	# ---- the loop ------------------------------------------------------------------------------------

	def run_once(self) -> dict:
		"""One pass over every source, each until caught up. Returns {app_key: events consumed or the error class name}."""
		result = {}
		for source in self.sources:
			result[source.app_key] = self._cycle(source, ignore_schedule=True)
		self.flush_metrics()
		return result

	def _cycle(self, source, ignore_schedule: bool = False):
		runtime = self.runtime[source.app_key]
		if not ignore_schedule and self._clock() < runtime.next_run:
			return None
		poll_seconds = 2.0
		try:
			consumed = self.sync_source(source)
			runtime.failures = 0
			runtime.rejected_reason = None
			self.metrics.set(source.app_key, "source_stopped", 0)
			runtime.next_run = self._clock() + (0 if consumed else poll_seconds)
			return consumed
		except FeedRejected as exc:
			runtime.rejected_reason = str(exc)
			runtime.next_run = self._clock() + REJECTED_RETRY_SECONDS
			self.metrics.set(source.app_key, "source_stopped", 1)
			self.metrics.inc(source.app_key, "errors")
			log.error(
				"source %s is stopped: %s (will check again in %s s)",
				source.app_key,
				exc,
				REJECTED_RETRY_SECONDS,
			)
			return type(exc).__name__
		except (FeedUnavailable, TransientDbError, config.ConfigError) as exc:
			runtime.failures += 1
			delay = backoff_seconds(runtime.failures - 1)
			runtime.next_run = self._clock() + delay
			self.metrics.inc(source.app_key, "errors")
			log.warning("source %s: %s; retrying in %s s", source.app_key, type(exc).__name__, delay)
			return type(exc).__name__
		except Exception as exc:  # never let one source's bug stop the loop
			runtime.failures += 1
			runtime.next_run = self._clock() + backoff_seconds(runtime.failures - 1)
			self.metrics.inc(source.app_key, "errors")
			log.exception("source %s: unexpected %s", source.app_key, type(exc).__name__)
			self.reset_connection()
			return type(exc).__name__

	def flush_metrics(self) -> None:
		try:
			self.metrics.flush(self.conn())
		except Exception as exc:
			log.warning("could not write metrics: %s", type(exc).__name__)
			self.reset_connection()

	def run_forever(self, poll_seconds: float = 1.0) -> None:
		log.info("projector started for %s source(s)", len(self.sources))
		try:
			apply.record_contracts(self.conn())
		except Exception as exc:
			log.warning("could not record the contracts: %s", type(exc).__name__)
			self.reset_connection()
		while not self.stopping:
			for source in self.sources:
				self._cycle(source)
			self.flush_metrics()
			self._sleep(poll_seconds)
		log.info("projector stopped")
