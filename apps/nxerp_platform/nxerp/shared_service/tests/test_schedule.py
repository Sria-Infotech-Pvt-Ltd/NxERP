"""When the reconciler runs: unit tests, no database."""

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared_service.reconcile import Schedule


def at(hour: int, minute: int = 0, day: int = 18) -> float:
	return datetime(2026, 11, day, hour, minute, tzinfo=UTC).timestamp()


class TestSchedule(unittest.TestCase):
	def test_the_first_wake_up_runs_a_recent_scan(self):
		self.assertEqual(Schedule(full_hour=23).due(at(10)), ["recent"])

	def test_a_recent_scan_runs_every_hour_not_before(self):
		schedule = Schedule(full_hour=23)
		schedule.done("recent", at(10))
		self.assertEqual(schedule.due(at(10, 59)), [])
		self.assertEqual(schedule.due(at(11, 0)), ["recent"])

	def test_the_full_compare_runs_once_a_day_from_the_set_hour(self):
		schedule = Schedule(full_hour=3)
		schedule.done("recent", at(2, 30))
		self.assertEqual(schedule.due(at(3, 0)), ["full"])
		schedule.done("full", at(3, 0))
		self.assertEqual(schedule.due(at(3, 1)), [])
		self.assertEqual(schedule.due(at(4, 1)), ["recent"], "after the full compare the hourly scans go on")
		self.assertEqual(schedule.due(at(3, 0, day=19)), ["full"], "and again the next day")

	def test_a_full_compare_is_not_repeated_the_same_day_and_replaces_the_recent_scan(self):
		schedule = Schedule(full_hour=3)
		self.assertEqual(
			schedule.due(at(5)), ["full"], "a late first start still gets the day's full compare"
		)
		schedule.done("full", at(5))
		self.assertEqual(schedule.due(at(5, 10)), [])
		self.assertEqual(schedule.last_recent, at(5), "a full compare counts as the latest scan")


if __name__ == "__main__":
	unittest.main()
