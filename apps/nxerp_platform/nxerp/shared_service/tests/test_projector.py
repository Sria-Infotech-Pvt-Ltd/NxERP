"""The projector against a fake owner feed and a real MariaDB. Skipped without a reachable server: run `deploy/scripts/shared.sh test`.

T14 (no loss across an outage) and T16 (a duplicate delivery is a no-op) are here, with the apply rules of blueprint 2.6.4.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared_service import projector as projector_module
from nxerp.shared_service.config import Source
from nxerp.shared_service.feedclient import FeedClient
from nxerp.shared_service.projector import Projector, TransientDbError
from nxerp.shared_service.tests.fakeowner import FakeOwner
from nxerp.shared_service.tests.support import OwnerTestCase

T10, T1030, T11, T12 = (f"2026-11-18 {h}.000000" for h in ("10:00:00", "10:30:00", "11:00:00", "12:00:00"))


class TestApplyRules(OwnerTestCase):
	def customer(self, **fields):
		return self.owner.payload_for("customer", **fields)

	def test_events_are_applied_then_the_cursor_moves_and_the_owner_is_acknowledged(self):
		self.owner.upsert("customer", "C1", display_name="Example Ltd", customer_type="Company", disabled=0)
		self.owner.upsert("customer", "C2", display_name="Other Ltd")
		self.assertEqual(self.projector.run_once(), {"stub": 2})
		self.assertEqual(self.count("customer"), 2)
		row = self.row("customer", "C1")
		self.assertEqual(
			(row["display_name"], row["customer_type"], row["disabled"], row["tenant_id"]),
			("Example Ltd", "Company", 0, "ORG-001"),
		)
		self.assertEqual((row["source_app"], row["last_seq"], row["contract_version"]), ("erpnext", 1, 1))
		self.assertEqual(self.cursor(), {"last_seq": 2, "state": "live"})
		self.assertEqual(self.owner.acked, 2)
		self.assertEqual(self.metric("applied"), 2)
		self.assertIsNotNone(self.metric("last_success"))

	def test_t16_a_duplicate_delivery_is_a_no_op(self):
		self.owner.upsert("customer", "C1", display_name="Example Ltd")
		self.projector.run_once()
		before = self.row("customer", "C1")
		self.query("UPDATE sync_cursor SET last_seq = 0")  # the owner delivers everything again
		self.assertEqual(self.projector.run_once(), {"stub": 1})
		self.assertEqual(self.row("customer", "C1"), before, "the row, including synced_at, did not change")
		self.assertEqual(self.metric("skipped_old"), 1)
		self.assertEqual(self.count("customer"), 1)

	def test_out_of_order_versions_end_at_the_newer_one(self):
		self.owner.add_event("customer", "C1", "upsert", self.customer(display_name="v2 newer"), T11)
		self.owner.add_event(
			"customer", "C1", "upsert", self.customer(display_name="v1 older"), T10
		)  # arrives after, is older
		self.projector.run_once()
		row = self.row("customer", "C1")
		self.assertEqual((row["display_name"], row["last_seq"]), ("v2 newer", 1))
		self.assertEqual(row["source_modified"].strftime("%H:%M:%S"), "11:00:00")
		self.assertEqual(self.metric("skipped_old"), 1)

	def test_a_newer_version_with_a_lower_sequence_still_wins_and_keeps_a_consistent_stamp(self):
		self.owner.add_event("customer", "C1", "upsert", self.customer(display_name="old"), T10)
		self.owner.add_event("customer", "C2", "upsert", self.customer(display_name="filler"), T10)
		self.projector.run_once()
		self.owner.add_event("customer", "C1", "upsert", self.customer(display_name="new"), T11)
		self.projector.run_once()
		row = self.row("customer", "C1")
		self.assertEqual((row["display_name"], row["last_seq"]), ("new", 3))

	def test_a_delete_is_a_tombstone_and_a_late_older_upsert_cannot_bring_it_back(self):
		self.owner.add_event("customer", "C1", "upsert", self.customer(display_name="Example Ltd"), T10)
		self.owner.add_event("customer", "C1", "delete", None, T11)
		self.owner.add_event("customer", "C1", "upsert", self.customer(display_name="late and older"), T1030)
		self.projector.run_once()
		row = self.row("customer", "C1")
		self.assertIsNotNone(row["deleted_at"])
		self.assertIsNone(row["display_name"], "personal data is removed when the owner deletes it")
		self.assertEqual(self.count("customer"), 0)
		self.assertEqual(self.count("customer", tombstones=True), 1)

	def test_a_newer_upsert_after_a_delete_brings_the_entity_back(self):
		self.owner.add_event("customer", "C1", "upsert", self.customer(display_name="first"), T10)
		self.owner.add_event("customer", "C1", "delete", None, T11)
		self.owner.add_event("customer", "C1", "upsert", self.customer(display_name="recreated"), T12)
		self.projector.run_once()
		row = self.row("customer", "C1")
		self.assertEqual((row["display_name"], row["deleted_at"]), ("recreated", None))

	def test_a_delete_for_an_entity_never_seen_leaves_a_tombstone_that_blocks_an_older_upsert(self):
		self.owner.add_event("customer", "NEW", "delete", None, T11)
		self.owner.add_event("customer", "NEW", "upsert", self.customer(display_name="older"), T10)
		self.projector.run_once()
		self.assertEqual(self.count("customer"), 0)
		self.assertEqual(self.count("customer", tombstones=True), 1)

	def test_a_resync_reads_the_entity_from_the_owner(self):
		self.owner.upsert("customer", "C1", display_name="Now")
		self.owner.bypass_change(
			"customer", "C1", keep_modified=False, display_name="Changed behind the event"
		)
		self.owner.resync("customer", "C1")
		self.projector.run_once()
		self.assertEqual(self.row("customer", "C1")["display_name"], "Changed behind the event")

	def test_a_resync_of_an_entity_the_owner_no_longer_has_is_a_tombstone(self):
		self.owner.upsert("customer", "C1", display_name="Now")
		self.owner.bypass_delete("customer", "C1")
		self.owner.resync("customer", "C1")
		self.projector.run_once()
		self.assertIsNotNone(self.row("customer", "C1")["deleted_at"])

	def test_every_active_entity_type_is_applied_with_its_own_columns(self):
		self.owner.upsert(
			"contact",
			"K1",
			customer_id="C1",
			full_name="Example Person",
			email="user@example.test",
			phone="+10000000000",
			is_primary=1,
		)
		self.owner.upsert("org_unit", "ORG-A", name="Example Org", parent_id=None, disabled=None)
		self.owner.upsert(
			"ticket_summary",
			"T1",
			customer_id="C1",
			status="Open",
			priority="High",
			opened_at="2026-11-18 09:00:00.000000",
			resolved_at=None,
			assignee_user_id="user@example.test",
		)
		self.projector.run_once()
		self.assertEqual(self.row("contact", "K1")["email"], "user@example.test")
		self.assertEqual(self.row("org_unit", "ORG-A")["tenant_id"], "ORG-A", "an org unit is its own tenant")
		ticket = self.row("ticket_summary", "T1")
		self.assertEqual(
			(ticket["status"], ticket["opened_at"].strftime("%Y-%m-%d %H:%M:%S"), ticket["resolved_at"]),
			("Open", "2026-11-18 09:00:00", None),
		)


class TestValidationAndDeadLetters(OwnerTestCase):
	def test_an_invalid_payload_is_dead_lettered_without_its_values_and_the_next_event_applies(self):
		leak_marker = "NXT-SECRET-TAX-123"
		bad = {**self.owner.payload_for("customer", display_name="Bad"), "tax_id": leak_marker}
		self.owner.add_event("customer", "BAD", "upsert", bad, T10)
		self.owner.upsert("customer", "GOOD", display_name="Good")
		self.assertEqual(self.projector.run_once(), {"stub": 2})
		self.assertIsNone(self.row("customer", "BAD"))
		self.assertEqual(self.row("customer", "GOOD")["display_name"], "Good")
		letters = self.dead_letters()
		self.assertEqual(len(letters), 1)
		self.assertIn("tax_id", letters[0]["error_text"])
		stored = json.loads(letters[0]["event_json"])
		self.assertIn("tax_id", stored["payload_fields"])
		self.assertNotIn(
			leak_marker,
			letters[0]["event_json"],
			"no payload value reaches the shared database through a dead letter",
		)
		self.assertNotIn("payload", stored)
		self.assertEqual(self.cursor()["last_seq"], 2, "the stream continued past the dead letter")
		self.assertEqual(self.metric("dead_letters"), 1)

	def test_a_contract_version_mismatch_and_a_wrong_owner_are_dead_lettered_with_a_reason(self):
		payload = self.owner.payload_for("customer", display_name="X")
		self.owner.add_event("customer", "A", "upsert", payload, T10, contract_version=99)
		self.owner.add_event("customer", "B", "upsert", payload, T10, source_app="helpdesk")
		self.owner.add_event("customer", "C", "merge", payload, T10)
		self.projector.run_once()
		reasons = " | ".join(letter["error_text"] for letter in self.dead_letters())
		self.assertIn("contract_version", reasons)
		self.assertIn("not the owner", reasons)
		self.assertIn("unknown op", reasons)
		self.assertEqual(self.count("customer"), 0)
		self.assertEqual(self.cursor()["last_seq"], 3)

	def test_a_value_longer_than_its_column_is_dead_lettered_not_retried(self):
		self.owner.add_event(
			"customer", "LONG", "upsert", self.owner.payload_for("customer", display_name="x" * 400), T10
		)
		self.projector.run_once()
		self.assertEqual(len(self.dead_letters()), 1)
		self.assertIn("longer than its column", self.dead_letters()[0]["error_text"])

	def test_a_data_error_in_a_batch_is_retried_alone_five_times_then_dead_lettered(self):
		self.owner.upsert("customer", "GOOD1", display_name="One")
		self.owner.upsert("customer", "BAD", display_name="Bad")
		self.owner.upsert("customer", "GOOD2", display_name="Two")
		import pymysql

		original = Projector._apply_event

		def flaky(this, cur, event, counts):
			if event["entity_id"] == "BAD":
				raise pymysql.err.DataError(1406, "Data too long for column")
			return original(this, cur, event, counts)

		with patch.object(Projector, "_apply_event", flaky):
			self.assertEqual(self.projector.run_once(), {"stub": 3})
		self.assertEqual(
			{r["entity_id"] for r in self.query("SELECT entity_id FROM entity_customer")}, {"GOOD1", "GOOD2"}
		)
		letters = self.dead_letters()
		self.assertEqual(
			(len(letters), letters[0]["attempts"], letters[0]["entity_id"]),
			(1, projector_module.MAX_ATTEMPTS, "BAD"),
		)
		self.assertEqual(self.cursor()["last_seq"], 3)


class TestCrashSafety(OwnerTestCase):
	def test_rows_and_cursor_are_atomic_a_kill_before_the_commit_leaves_neither(self):
		self.owner.upsert("customer", "C1", display_name="One")
		self.owner.upsert("customer", "C2", display_name="Two")

		def kill():
			raise RuntimeError("killed after the apply, before the commit")

		self.projector.before_commit = kill
		self.assertEqual(self.projector.run_once(), {"stub": "RuntimeError"})
		self.assertEqual(self.count("customer", tombstones=True), 0)
		self.assertEqual(self.cursor(), {"last_seq": 0, "state": "none"})
		self.assertEqual(self.owner.acked, 0)
		self.projector.before_commit = None
		self.assertEqual(self.projector.run_once(), {"stub": 2})
		self.assertEqual(self.count("customer"), 2)
		self.assertEqual(self.owner.acked, 2)

	def test_a_crash_between_apply_and_ack_redelivers_nothing_lost_and_the_ack_catches_up(self):
		self.owner.upsert("customer", "C1", display_name="One")
		self.owner.drop_acks = 1
		self.projector.run_once()
		self.assertEqual(
			(self.cursor()["last_seq"], self.owner.acked), (1, 0), "applied and committed, the ack was lost"
		)
		self.assertEqual(self.projector.runtime["stub"].pending_ack, 1)
		self.projector.run_once()
		self.assertEqual(self.owner.acked, 1, "the pending acknowledgement is retried")
		# a restart forgets the pending ack: the next acknowledgement covers everything before it
		self.owner.acked = 0
		restarted = self.new_projector()
		self.addCleanup(restarted.reset_connection)
		self.owner.upsert("customer", "C2", display_name="Two")
		restarted.run_once()
		self.assertEqual(self.owner.acked, 2)
		self.assertEqual(self.count("customer"), 2)

	def test_t14_no_loss_across_an_outage_of_the_projector(self):
		self.owner.upsert("customer", "C0", display_name="Before")
		self.projector.run_once()
		for index in range(20):  # the projector is down while the owner keeps changing
			self.owner.upsert("customer", f"C{index + 1}", display_name=f"During {index}")
		restarted = self.new_projector()
		self.addCleanup(restarted.reset_connection)
		restarted.run_once()
		self.assertEqual(self.count("customer"), 21)
		self.assertEqual(self.dead_letters(), [])
		self.assertEqual(self.cursor()["last_seq"], 21)

	def test_batches_are_applied_in_pieces_and_resume_where_they_stopped(self):
		for index in range(7):
			self.owner.upsert("customer", f"C{index}", display_name=f"n{index}")
		small = self.new_projector(batch_size=3)
		self.addCleanup(small.reset_connection)
		self.assertEqual(small.run_once(), {"stub": 7})
		self.assertEqual(self.count("customer"), 7)
		self.assertEqual(self.owner.acked, 7)


class TestSequenceGap(OwnerTestCase):
	def test_a_sequence_gap_applies_what_precedes_it_then_stops_the_source(self):
		self.owner.upsert("customer", "C1", display_name="One")
		self.owner.skip_seq()
		self.owner.upsert("customer", "C3", display_name="After the gap")
		self.projector.run_once()
		self.assertEqual(self.count("customer"), 1)
		self.assertIsNone(self.row("customer", "C3"))
		self.assertEqual(self.cursor(), {"last_seq": 1, "state": "gap"})
		self.assertEqual(self.metric("gap"), 1)
		pulls = self.owner.pull_calls
		self.projector.run_once()
		self.assertEqual(self.owner.pull_calls, pulls, "a stopped source is not pulled again")
		self.assertEqual(self.count("customer"), 1)

	def test_a_feed_that_went_back_behind_the_cursor_stops_the_source(self):
		self.owner.upsert("customer", "C1", display_name="One")
		self.owner.upsert("customer", "C2", display_name="Two")
		self.projector.run_once()
		self.owner.events.clear()  # the owner's outbox was reset: its head is now behind our cursor
		self.projector.runtime["stub"].last_head_check = -10_000
		self.projector.run_once()
		self.assertEqual(self.cursor()["state"], "gap")


class TestFailures(OwnerTestCase):
	def test_server_errors_back_off_and_change_nothing_then_recover(self):
		self.owner.upsert("customer", "C1", display_name="One")
		self.owner.fail_pulls = 2
		self.assertEqual(self.projector.run_once(), {"stub": "FeedUnavailable"})
		self.assertEqual(self.projector.run_once(), {"stub": "FeedUnavailable"})
		self.assertEqual(self.cursor()["state"], "none")
		self.assertEqual(self.projector.runtime["stub"].failures, 2)
		self.assertEqual(self.projector.run_once(), {"stub": 1})
		self.assertEqual(self.projector.runtime["stub"].failures, 0)
		self.assertEqual(self.metric("errors"), 2)

	def test_the_backoff_is_1_2_4_up_to_60_seconds(self):
		self.assertEqual(
			[projector_module.backoff_seconds(n) for n in range(9)], [1, 2, 4, 8, 16, 32, 60, 60, 60]
		)

	def test_a_rejected_source_stops_and_is_not_retried_for_five_minutes(self):
		now = [1000.0]
		stopped = self.new_projector(clock=lambda: now[0])
		self.addCleanup(stopped.reset_connection)
		self.owner.force_status = 403
		self.assertEqual(stopped.run_once(), {"stub": "FeedRejected"})
		self.assertEqual(stopped.runtime["stub"].next_run - 1000.0, projector_module.REJECTED_RETRY_SECONDS)
		self.assertEqual(self.metric("source_stopped"), 1)
		self.owner.force_status = None
		calls = self.owner.pull_calls
		stopped._cycle(self.source)  # on schedule: too early, nothing happens
		self.assertEqual(self.owner.pull_calls, calls)
		now[0] += projector_module.REJECTED_RETRY_SECONDS + 1
		self.owner.upsert("customer", "C1", display_name="One")
		stopped._cycle(self.source)
		self.assertEqual(self.count("customer"), 1)

	def test_a_wrong_key_is_rejected_not_retried_in_a_loop(self):
		wrong = Projector(
			lambda: self.connect("projector"),
			[self.source],
			client_factory=lambda source: FeedClient(source, "wrong:secretxx"),
			metrics=self.metrics,
		)
		self.addCleanup(wrong.reset_connection)
		self.assertEqual(wrong.run_once(), {"stub": "FeedRejected"})

	def test_one_failing_source_does_not_block_another(self):
		other = FakeOwner(key="otherkey1:othersecret2").start()
		self.addCleanup(other.stop)
		with tempfile.TemporaryDirectory() as tmp:
			second = Source("stub2", other.base_url, str(Path(tmp, "k")), None)
			projector = Projector(
				lambda: self.connect("projector"),
				[self.source, second],
				client_factory=lambda s: FeedClient(s, self.owner.key if s is self.source else other.key),
				metrics=self.metrics,
			)
			self.addCleanup(projector.reset_connection)
			self.owner.force_status = 500
			other.upsert("customer", "FROM-OTHER", display_name="Other owner")
			result = projector.run_once()
		self.assertEqual(result["stub"], "FeedUnavailable")
		self.assertEqual(result["stub2"], 1)
		self.assertEqual(self.row("customer", "FROM-OTHER")["display_name"], "Other owner")
		cursors = {
			r["source_app"]: r["last_seq"] for r in self.query("SELECT source_app, last_seq FROM sync_cursor")
		}
		self.assertEqual(cursors, {"stub2": 1})

	def test_a_transient_database_error_rolls_back_never_acks_and_recovers(self):
		import pymysql

		self.owner.upsert("customer", "C1", display_name="One")
		with patch.object(
			Projector, "_write", side_effect=pymysql.err.OperationalError(2013, "Lost connection")
		):
			self.assertEqual(self.projector.run_once(), {"stub": "TransientDbError"})
		self.assertEqual((self.owner.acked, self.count("customer", tombstones=True)), (0, 0))
		self.assertEqual(self.projector.run_once(), {"stub": 1})
		self.assertEqual(self.owner.acked, 1)
		self.assertTrue(issubclass(TransientDbError, RuntimeError))

	def test_the_lag_gauge_comes_from_the_owners_oldest_unacknowledged_age(self):
		self.owner.head_age = 7
		self.owner.upsert("customer", "C1", display_name="One")
		self.projector.run_once()
		self.assertEqual(self.metric("lag_seconds"), 7)


class TestCounters(OwnerTestCase):
	def test_counters_accumulate_across_restarts_and_gauges_replace(self):
		self.owner.upsert("customer", "C1", display_name="One")
		self.projector.run_once()
		second = self.new_projector(metrics=type(self.metrics)())
		self.addCleanup(second.reset_connection)
		self.owner.upsert("customer", "C2", display_name="Two")
		second.run_once()
		self.assertEqual(self.metric("applied"), 2)


if __name__ == "__main__":
	unittest.main()
