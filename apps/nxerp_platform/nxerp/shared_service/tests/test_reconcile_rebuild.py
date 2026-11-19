"""The reconciler (T17) and rebuild (T18) against a fake owner feed and a real MariaDB. Skipped without a reachable server.

Run: deploy/scripts/shared.sh test -p "test_reconcile*"
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared_service import apply
from nxerp.shared_service.feedclient import FeedClient
from nxerp.shared_service.rebuild import RebuildError, rebuild
from nxerp.shared_service.reconcile import HashFunctionMismatch, Reconciler
from nxerp.shared_service.tests.support import OwnerTestCase


class Base(OwnerTestCase):
	def seed(self, count: int = 5) -> None:
		for index in range(1, count + 1):
			self.owner.upsert(
				"customer", f"C{index}", display_name=f"Name {index}", customer_type="Company", territory="T1"
			)
		self.projector.run_once()

	def reconciler(self, **kwargs) -> Reconciler:
		return Reconciler(
			lambda: self.connect("projector"),
			[self.source],
			client_factory=lambda source: FeedClient(source, self.owner.key),
			metrics=self.metrics,
			**kwargs,
		)

	def reconcile(self, mode: str = "full") -> dict:
		return self.reconciler().run(mode)

	def customer_counts(self, report: dict) -> dict:
		return report["sources"]["stub"]["entities"]["customer"]

	def run_rebuild(self, **kwargs) -> dict:
		options = {"relay_wait": 0, "page": 2, "metrics": self.metrics}
		options.update(kwargs)
		return rebuild(
			lambda: self.connect("projector"),
			[self.source],
			client_factory=lambda source: FeedClient(source, self.owner.key),
			**options,
		)


class TestReconcile(Base):
	def test_t17_a_change_made_without_an_event_is_found_by_the_nightly_compare_and_repaired(self):
		self.seed(5)
		self.owner.bypass_change(
			"customer", "C3", territory="Moved behind the event"
		)  # same version stamp, no event
		report = self.reconcile("full")
		counts = self.customer_counts(report)
		self.assertEqual(
			(counts["hash_mismatch"], counts["repaired"], counts["ids"]["hash_mismatch"]), (1, 1, ["C3"])
		)
		self.assertEqual(self.row("customer", "C3")["territory"], "Moved behind the event")
		self.assertEqual(self.reconcile("full")["drift"], 0, "the second run finds nothing left")

	def test_a_row_the_owner_deleted_without_an_event_is_extra_and_becomes_a_tombstone(self):
		self.seed(4)
		self.owner.bypass_delete("customer", "C2")
		counts = self.customer_counts(self.reconcile("full"))
		self.assertEqual((counts["extra"], counts["ids"]["extra"]), (1, ["C2"]))
		row = self.row("customer", "C2")
		self.assertIsNotNone(row["deleted_at"])
		self.assertIsNone(row["display_name"])
		self.assertEqual(self.count("customer"), 3)
		self.assertEqual(self.reconcile("full")["drift"], 0)

	def test_an_entity_created_without_an_event_is_missing_and_repaired(self):
		self.seed(2)
		self.owner.bypass_create("customer", "BORN", display_name="born without event")
		counts = self.customer_counts(self.reconcile("full"))
		self.assertEqual((counts["missing"], counts["repaired"]), (1, 1))
		self.assertEqual(self.row("customer", "BORN")["display_name"], "born without event")

	def test_an_owner_change_with_a_newer_stamp_but_no_event_is_stale_and_repaired(self):
		self.seed(3)
		self.owner.bypass_change("customer", "C1", keep_modified=False, display_name="changed, stamp moved")
		counts = self.customer_counts(self.reconcile("full"))
		self.assertEqual((counts["stale"], counts["repaired"]), (1, 1))
		self.assertEqual(self.row("customer", "C1")["display_name"], "changed, stamp moved")

	def test_a_tombstoned_row_the_owner_has_again_is_missing_and_repaired(self):
		self.seed(2)
		self.owner.bypass_delete("customer", "C1")
		self.reconcile("full")
		self.owner.bypass_create("customer", "C1", display_name="back")
		counts = self.customer_counts(self.reconcile("full"))
		self.assertEqual(counts["missing"], 1)
		self.assertEqual(self.row("customer", "C1")["display_name"], "back")
		self.assertIsNone(self.row("customer", "C1")["deleted_at"])

	def test_the_recent_scan_only_looks_at_recently_modified_documents(self):
		# C1 was last modified hours before the others, so it is outside the window (the newest stamp minus 5 minutes)
		self.owner.upsert(
			"customer", "C1", modified="2026-11-18 08:00:00.000000", display_name="Name 1", territory="T1"
		)
		self.owner.upsert("customer", "C2", display_name="Name 2", territory="T1")
		self.owner.upsert("customer", "C3", display_name="Name 3", territory="T1")
		self.projector.run_once()
		first = self.reconcile("recent")
		self.assertEqual(first["drift"], 0)
		self.assertIsNone(
			self.owner.digest_calls[-1].get("modified_since"), "the first scan has no watermark"
		)
		self.owner.bypass_change(
			"customer", "C1", territory="old doc, changed behind the event"
		)  # stamp unchanged: outside the window
		second = self.reconcile("recent")
		self.assertEqual(
			second["drift"], 0, "a same-stamp change on an old document is the full compare's job"
		)
		self.assertIsNotNone(self.owner.digest_calls[-1].get("modified_since"))
		self.owner.bypass_change(
			"customer", "C2", keep_modified=False, display_name="moved stamp"
		)  # the recent scan sees this
		third = self.reconcile("recent")
		self.assertEqual(self.customer_counts(third)["stale"], 1)
		self.assertEqual(
			self.customer_counts(self.reconcile("full"))["hash_mismatch"],
			1,
			"the nightly compare catches the old document",
		)

	def test_the_recent_scan_never_reports_extra(self):
		self.seed(3)
		self.owner.bypass_delete("customer", "C1")
		self.assertEqual(self.customer_counts(self.reconcile("recent"))["extra"], 0)
		self.assertEqual(self.customer_counts(self.reconcile("full"))["extra"], 1)

	def test_an_unreachable_owner_is_skipped_and_its_rows_are_never_marked_extra(self):
		self.seed(3)
		for status in (500, 503):
			self.owner.force_status = status
			report = self.reconcile("full")
			self.assertEqual(report["sources"]["stub"]["status"], "unreachable")
		self.owner.force_status = None
		self.assertEqual(self.count("customer"), 3)
		self.assertEqual(self.count("customer", tombstones=True), 3)

	def test_a_rejecting_owner_is_skipped_and_reported(self):
		self.seed(2)
		self.owner.force_status = 403
		report = self.reconcile("full")
		self.assertEqual(
			(report["sources"]["stub"]["status"], report["sources"]["stub"]["http"]), ("rejected", 403)
		)
		self.assertEqual(self.count("customer"), 2)

	def test_an_entity_the_feed_does_not_serve_is_left_alone(self):
		self.seed(2)
		self.owner.served = {"contact"}  # this feed does not serve customers (their owner is elsewhere)
		report = self.reconcile("full")
		self.assertNotIn("customer", report["sources"]["stub"]["entities"])
		self.assertEqual(self.count("customer"), 2, "not served is not deleted")

	def test_a_repair_that_would_write_a_field_outside_the_contract_is_refused(self):
		self.seed(2)
		self.owner.docs["customer"]["C1"]["payload"]["tax_id"] = "NXT-LEAK-MARKER"
		report = self.reconcile("full")
		counts = self.customer_counts(report)
		self.assertEqual((counts["refused"], counts["repaired"], counts["refused_ids"]), (1, 0, ["C1"]))
		self.assertEqual(report["refused"], 1)
		self.assertEqual(self.row("customer", "C1")["display_name"], "Name 1")
		self.assertNotIn("NXT-LEAK-MARKER", json.dumps(report))

	def test_a_hash_function_difference_fails_loudly_and_repairs_nothing(self):
		self.seed(12)
		with patch.object(apply, "row_hash", return_value="0" * 64):
			with self.assertRaises(HashFunctionMismatch):
				self.reconcile("full")
		self.assertEqual(self.count("customer"), 12)

	def test_the_report_holds_ids_and_counts_never_values(self):
		self.seed(3)
		self.owner.bypass_change("customer", "C1", display_name="PRIVATE-VALUE-123")
		report = self.reconcile("full")
		self.assertNotIn("PRIVATE-VALUE-123", json.dumps(report))
		self.assertNotIn("Name 2", json.dumps(report))

	def test_metrics_record_drift_and_the_time_of_the_last_run(self):
		self.seed(3)
		self.owner.bypass_change("customer", "C1", territory="x")
		self.reconcile("full")
		self.assertEqual(self.metric("reconcile_drift"), 1)
		self.assertIsNotNone(self.metric("last_reconcile_at"))
		self.reconcile("full")
		self.assertEqual(self.metric("reconcile_drift"), 0)

	def test_every_active_entity_type_is_compared(self):
		self.owner.upsert(
			"contact",
			"K1",
			customer_id="C1",
			full_name="Example Person",
			email="user@example.test",
			is_primary=1,
		)
		self.owner.upsert("org_unit", "ORG-A", name="Org A")
		self.projector.run_once()
		self.owner.bypass_change("contact", "K1", phone="+10000000000")
		entities = self.reconcile("full")["sources"]["stub"]["entities"]
		self.assertEqual(set(entities), {"customer", "contact", "org_unit", "ticket_summary"})
		self.assertEqual(entities["contact"]["hash_mismatch"], 1)
		self.assertEqual(entities["org_unit"]["hash_mismatch"], 0)


class TestRebuild(Base):
	def test_t18_drop_the_shared_database_rebuild_and_the_full_compare_shows_no_drift(self):
		self.seed(6)
		self.owner.upsert(
			"contact",
			"K1",
			customer_id="C1",
			full_name="Example Person",
			email="user@example.test",
			is_primary=1,
		)
		self.owner.upsert("org_unit", "ORG-A", name="Org A")
		self.projector.run_once()
		before = self.count("customer")
		self.drop_and_recreate_database()
		self.assertEqual(self.count("customer", tombstones=True), 0, "the new database is empty")
		report = self.run_rebuild()
		result = report["sources"]["stub"]
		self.assertEqual((result["status"], result["drift_after"], result["dead_letters"]), ("ok", 0, 0))
		self.assertEqual(self.count("customer"), before)
		self.assertEqual(self.count("contact"), 1)
		self.assertEqual(self.count("org_unit"), 1)
		self.assertEqual(self.cursor(), {"last_seq": self.owner.events[-1]["seq"], "state": "live"})
		self.assertEqual(self.reconcile("full")["drift"], 0)
		self.assertEqual(result["entities"]["customer"]["snapshot_rows"], 6)

	def test_the_first_backfill_is_the_same_function(self):
		for index in range(4):
			self.owner.upsert("customer", f"C{index}", display_name=f"Name {index}")
		report = self.run_rebuild()
		self.assertEqual(report["sources"]["stub"]["start_seq"], 4)
		self.assertEqual(self.count("customer"), 4)
		self.assertEqual(
			self.owner.acked, 0, "a rebuild snapshots; the projector acknowledges nothing it did not replay"
		)

	def test_a_rebuild_while_the_owner_keeps_changing_converges(self):
		self.seed(6)

		def owner_keeps_changing(page_number: int) -> None:
			if page_number == 1:
				self.owner.upsert("customer", "LATE", display_name="created while the snapshot streams")
				self.owner.upsert("customer", "C1", display_name="changed while the snapshot streams")
				self.owner.delete("customer", "C2")

		self.owner.on_snapshot_page = owner_keeps_changing
		report = self.run_rebuild()
		self.owner.on_snapshot_page = None
		result = report["sources"]["stub"]
		self.assertEqual(result["drift_after"], 0)
		self.assertGreaterEqual(result["replayed"], 3, "the events after start_seq were replayed")
		self.assertEqual(self.row("customer", "LATE")["display_name"], "created while the snapshot streams")
		self.assertEqual(self.row("customer", "C1")["display_name"], "changed while the snapshot streams")
		self.assertIsNotNone(self.row("customer", "C2")["deleted_at"])
		self.assertEqual(self.reconcile("full")["drift"], 0)

	def test_a_rebuild_interrupted_midway_can_be_run_again(self):
		self.seed(5)
		self.query("DELETE FROM entity_customer")
		self.owner.fail_snapshot_after = 1
		with self.assertRaises(RebuildError) as caught:
			self.run_rebuild()
		self.assertEqual(caught.exception.report["sources"]["stub"]["status"], "interrupted")
		self.assertEqual(self.cursor()["state"], "rebuilding")
		pulls = self.owner.pull_calls
		self.projector.run_once()
		self.assertEqual(self.owner.pull_calls, pulls, "the projector leaves a rebuilding source alone")
		self.assertLess(
			self.count("customer", tombstones=True), 5, "some of it was applied before the failure"
		)
		self.owner.fail_snapshot_after = None
		report = self.run_rebuild()
		self.assertEqual(report["sources"]["stub"]["drift_after"], 0)
		self.assertEqual((self.count("customer"), self.cursor()["state"]), (5, "live"))

	def test_a_rebuild_tombstones_rows_the_owner_no_longer_has(self):
		self.seed(3)
		self.owner.bypass_delete("customer", "C3")
		result = self.run_rebuild()["sources"]["stub"]
		self.assertEqual(result["entities"]["customer"]["tombstoned"], 1)
		self.assertIsNotNone(self.row("customer", "C3")["deleted_at"])

	def test_a_rebuild_refuses_a_row_with_a_field_outside_the_contract(self):
		self.seed(2)
		self.owner.docs["customer"]["C1"]["payload"]["tax_id"] = "NXT-LEAK-MARKER"
		self.query("DELETE FROM entity_customer")
		result = self.run_rebuild()["sources"]["stub"]
		self.assertEqual(result["entities"]["customer"]["refused"], 1)
		self.assertIsNone(self.row("customer", "C1"))
		self.assertIsNotNone(self.row("customer", "C2"))

	def test_a_source_stopped_on_a_gap_is_recovered_by_a_rebuild(self):
		self.owner.upsert("customer", "C1", display_name="One")
		self.owner.skip_seq()
		self.owner.upsert("customer", "C3", display_name="After the gap")
		self.projector.run_once()
		self.assertEqual(self.cursor()["state"], "gap")
		result = self.run_rebuild()["sources"]["stub"]
		self.assertEqual((result["drift_after"], self.cursor()["state"]), (0, "live"))
		self.assertEqual(self.count("customer"), 2)
		self.assertEqual(self.metric("rebuilt_rows"), 2)

	def test_the_report_holds_counts_never_values(self):
		self.seed(2)
		self.assertNotIn("Name 1", json.dumps(self.run_rebuild()))

	def test_the_contracts_in_use_are_recorded(self):
		self.run_rebuild()
		rows = self.query("SELECT entity_type, contract_sha256 FROM contract_registry ORDER BY entity_type")
		self.assertEqual(len(rows), 7)
		self.assertTrue(all(len(r["contract_sha256"]) == 64 for r in rows))


if __name__ == "__main__":
	unittest.main()
