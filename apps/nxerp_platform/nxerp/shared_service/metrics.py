"""Projector and reconciler metrics, kept in `sync_metric` so another process (the Read API's /v1/metrics, `status`) can read them. No frappe.

Counters (`inc`) are cumulative and survive a restart: the pending increment is added to the stored value on `flush`. Gauges
(`set`) replace the stored value. Names used:

	applied, skipped_old, dead_letters, errors            counters, per source
	lag_seconds, last_success, gap, source_stopped        gauges, per source (last_success is a unix time)
	reconcile_drift, last_reconcile_at, rebuilt_rows      gauges, per source
	outbox_pending, rebuilt_at                            gauges, per source (the owner's pending count; a unix time)

Metric values are numbers about ids and counts, never payload values.
"""

import time


class Metrics:
	def __init__(self, clock=time.time):
		self._clock = clock
		self._counters: dict = {}
		self._gauges: dict = {}
		self.totals: dict = {}  # what this process has counted, for logs and tests (not persisted)

	def inc(self, source: str, name: str, delta: float = 1) -> None:
		key = (source, name)
		self._counters[key] = self._counters.get(key, 0) + delta
		self.totals[key] = self.totals.get(key, 0) + delta

	def set(self, source: str, name: str, value: float) -> None:
		self._gauges[(source, name)] = value

	def mark_success(self, source: str) -> None:
		self.set(source, "last_success", self._clock())

	def flush(self, conn) -> int:
		"""Write pending counters and gauges. Returns the number of rows written. Nothing is lost if this raises: the pending values stay."""
		if not self._counters and not self._gauges:
			return 0
		rows = 0
		with conn.cursor() as cur:
			for (source, name), delta in list(self._counters.items()):
				cur.execute(
					"INSERT INTO sync_metric (source, name, value, updated_at) VALUES (%s, %s, %s, NOW(6)) "
					"ON DUPLICATE KEY UPDATE value = value + VALUES(value), updated_at = NOW(6)",
					(source, name, delta),
				)
				rows += 1
			for (source, name), value in list(self._gauges.items()):
				cur.execute(
					"INSERT INTO sync_metric (source, name, value, updated_at) VALUES (%s, %s, %s, NOW(6)) "
					"ON DUPLICATE KEY UPDATE value = VALUES(value), updated_at = NOW(6)",
					(source, name, value),
				)
				rows += 1
		conn.commit()
		self._counters.clear()
		self._gauges.clear()
		return rows


# ---- the text form of /v1/metrics (Phase 8E): what a monitoring system scrapes --------------------------------------------------
# name -> (type, help, stored metric). Names are the ones the alert rules use (deploy/env/shared/alerts.example.yaml).
TEXT_METRICS = {
	"outbox_lag_seconds": (
		"gauge",
		"Seconds the oldest unacknowledged event waited at the owner",
		"lag_seconds",
	),
	"outbox_pending": ("gauge", "Events waiting at the owner (from its feed head)", "outbox_pending"),
	"projector_errors": ("counter", "Projector errors, cumulative", "errors"),
	"dead_letters": ("counter", "Events that could not be applied, cumulative", "dead_letters"),
	"reconcile_drift": ("gauge", "Differences the last reconciliation found", "reconcile_drift"),
	"projector_last_success_timestamp": ("gauge", "Unix time of the last successful pull", "last_success"),
}
REBUILD_AGE = "rebuild_age_seconds"
API_REQUESTS = "read_api_requests"
API_DENIED = "read_api_denied"


def _number(value) -> str:
	number = float(value)
	return str(int(number)) if number == int(number) else repr(number)


def render_text(rows: list, api_outcomes: dict, audit_dropped: int = 0, now: float | None = None) -> str:
	"""Prometheus text exposition of the stored metrics and this process's Read API counters.

	`rows` are {"source", "name", "value"} from sync_metric. Every metric name is always declared (HELP and TYPE), with a sample per source
	that has a value. Labels are source names (validated app keys); values are numbers: never a payload, a token or an id of a row."""
	now = time.time() if now is None else now
	by_name: dict = {}
	for row in rows:
		by_name.setdefault(row["name"], {})[row["source"]] = row["value"]
	lines = []

	def declare(name, kind, text):
		lines.append(f"# HELP {name} {text}")
		lines.append(f"# TYPE {name} {kind}")

	for name, (kind, text, stored) in TEXT_METRICS.items():
		declare(name, kind, text)
		for source, value in sorted(by_name.get(stored, {}).items()):
			lines.append(f'{name}{{source="{source}"}} {_number(value)}')
	declare(REBUILD_AGE, "gauge", "Seconds since the last rebuild of the source finished")
	for source, value in sorted(by_name.get("rebuilt_at", {}).items()):
		lines.append(f'{REBUILD_AGE}{{source="{source}"}} {_number(max(0, now - float(value)))}')
	declare(API_REQUESTS, "counter", "Read API requests since this process started, all outcomes")
	lines.append(f"{API_REQUESTS} {_number(sum(api_outcomes.values()))}")
	declare(API_DENIED, "counter", "Read API requests refused since this process started")
	lines.append(f"{API_DENIED} {_number(sum(v for k, v in api_outcomes.items() if k.startswith('denied')))}")
	declare("read_api_audit_dropped", "counter", "Audit rows this process could not write")
	lines.append(f"read_api_audit_dropped {_number(audit_dropped)}")
	return "\n".join(lines) + "\n"
