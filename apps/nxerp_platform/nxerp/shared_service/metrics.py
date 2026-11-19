"""Projector and reconciler metrics, kept in `sync_metric` so another process (the Read API's /v1/metrics, `status`) can read them. No frappe.

Counters (`inc`) are cumulative and survive a restart: the pending increment is added to the stored value on `flush`. Gauges
(`set`) replace the stored value. Names used:

	applied, skipped_old, dead_letters, errors            counters, per source
	lag_seconds, last_success, gap, source_stopped        gauges, per source (last_success is a unix time)
	reconcile_drift, last_reconcile_at, rebuilt_rows      gauges, per source

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
