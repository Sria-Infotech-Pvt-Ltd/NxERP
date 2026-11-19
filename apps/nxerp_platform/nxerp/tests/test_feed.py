"""The relay, the feed API and pruning (Phase 3C), on a dev site with ERPNext installed.

Run:  bench --site <site> run-tests --app nxerp --module nxerp.tests.test_feed

Concurrency is tested with a real second database connection (two transactions, one still open), not a simulation.
Each test starts from an empty outbox: these tests belong on a test site only. Test data is a fake Customer
(`user@example.test`); it, the outbox rows and the test users are removed at the end of the class.
"""

import copy
import json
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime

from nxerp.install import ensure_feed_role
from nxerp.shared import digest, feed, outbox, registry, relay
from nxerp.tests.test_outbox import CUSTOMER_FIELDS, ensure_customer_masters
from nxerp.tests.utils import delete_users, make_user, unique_email

DOCTYPE = outbox.DOCTYPE
ROLE = outbox.FEED_ROLE


def second_connection():
	"""A second, independent database connection to the site's database (its own transactions and locks)."""
	conf = frappe.local.conf
	db = frappe.database.get_db(
		host=conf.get("db_host"),
		user=conf.get("db_user") or conf.get("db_name"),
		password=conf.get("db_password"),
		port=conf.get("db_port"),
		cur_db_name=conf.get("db_name"),
	)
	db.connect()
	return db


def insert_row_on(db, entity_id, creation):
	"""An outbox row written on another connection, left uncommitted until the caller commits that connection."""
	stamp = now_datetime()
	db.sql(
		"INSERT INTO `tabNXERP Outbox Event` (name, creation, modified, modified_by, owner, docstatus, idx, source_app, "
		"entity_type, entity_id, op, contract_version, source_modified, status) "
		"VALUES (%s, %s, %s, 'Administrator', 'Administrator', 0, 0, 'erpnext', 'customer', %s, 'delete', 1, %s, 'pending')",
		(str(uuid.uuid7()), creation, stamp, entity_id, stamp),
	)


def seqs(*entity_ids):
	return {
		r.entity_id: r.seq
		for r in frappe.get_all(
			DOCTYPE, filters={"entity_id": ["in", list(entity_ids)]}, fields=["entity_id", "seq"]
		)
	}


class TestFeed(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_feed_role()
		cls.group, cls.territory = ensure_customer_masters()
		cls.reader = make_user(unique_email("feed-reader"), [ROLE]).name
		cls.plain = make_user(unique_email("feed-plain"), ["Website Manager"]).name
		cls.created = []
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for key in ("nxerp_shared_publish", "nxerp_shared_publish_strict", "nxerp_outbox_retention_days"):
			frappe.local.conf.pop(key, None)
		for name in reversed(cls.created):
			if frappe.db.exists("Customer", name):
				frappe.delete_doc("Customer", name, force=True, ignore_permissions=True)
		frappe.db.delete(DOCTYPE)
		delete_users([cls.reader, cls.plain])
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.conf["nxerp_shared_publish"] = 1
		frappe.local.conf["nxerp_shared_publish_strict"] = 1
		frappe.db.delete(DOCTYPE)
		frappe.db.commit()
		self.addCleanup(self._unset)

	@staticmethod
	def _unset():
		for key in ("nxerp_shared_publish", "nxerp_shared_publish_strict", "nxerp_outbox_retention_days"):
			frappe.local.conf.pop(key, None)

	def customer(self, **fields):
		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"NXT Feed {uuid.uuid4().hex[:8]}",
				"customer_type": "Company",
				"customer_group": self.group,
				"territory": self.territory,
				**fields,
			}
		).insert()
		self.created.append(doc.name)
		return doc

	def event(self, entity_id):
		return outbox.write_event("customer", entity_id, "delete", now_datetime(), None, 1, "erpnext")

	# ---- the relay ----------------------------------------------------------------------------------------

	def test_the_sequence_is_consecutive_and_follows_commit_order_across_two_connections(self):
		for entity in ("a1", "a2", "a3"):
			self.event(entity)
		other = second_connection()
		try:
			# an older row (earlier `creation`) whose transaction stays open while newer rows commit
			insert_row_on(other, "early", add_days(now_datetime(), -1))
			self.event("a4")
			frappe.db.commit()
			self.assertEqual(relay.assign_sequence(), 4, "only committed rows are sequenced")
			self.assertEqual(seqs("a1", "a2", "a3", "a4"), {"a1": 1, "a2": 2, "a3": 3, "a4": 4})
			self.assertEqual(seqs("early"), {}, "the uncommitted row is invisible to the relay")
			other.commit()
			self.assertEqual(relay.assign_sequence(), 1)
			self.assertEqual(seqs("early"), {"early": 5}, "commit order wins over creation order")
		finally:
			other.close()
		self.assertEqual(sorted(seqs("a1", "a2", "a3", "a4", "early").values()), [1, 2, 3, 4, 5])

	def test_the_relay_works_in_batches_and_numbers_stay_consecutive(self):
		for index in range(5):
			self.event(f"b{index}")
		frappe.db.commit()
		with patch.object(relay, "BATCH_SIZE", 2):
			self.assertEqual(relay.assign_sequence(), 5)
		self.assertEqual(sorted(seqs(*[f"b{i}" for i in range(5)]).values()), [1, 2, 3, 4, 5])

	def test_a_second_relay_is_a_no_op_and_503_when_asked(self):
		self.event("c1")
		frappe.db.commit()
		other = second_connection()
		try:
			self.assertEqual(other.sql("SELECT GET_LOCK(%s, 0)", (relay.LOCK_NAME,))[0][0], 1)
			self.assertEqual(relay.assign_sequence(), 0)
			with self.assertRaises(relay.RelayBusy) as caught:
				relay.assign_sequence(raise_if_busy=True)
			self.assertEqual(caught.exception.http_status_code, 503)
			self.assertEqual(seqs("c1"), {"c1": None}, "nothing was claimed while the lock was held")
			other.sql("SELECT RELEASE_LOCK(%s)", (relay.LOCK_NAME,))
		finally:
			other.close()
		self.assertEqual(relay.assign_sequence(), 1)

	def test_a_failed_batch_leaves_its_rows_pending_and_releases_the_lock(self):
		for index in range(3):
			self.event(f"d{index}")
		frappe.db.commit()
		with patch.object(relay, "_claim_batch", side_effect=RuntimeError("batch failed")):
			with self.assertRaises(RuntimeError):
				relay.assign_sequence()
		self.assertEqual(seqs("d0", "d1", "d2"), {"d0": None, "d1": None, "d2": None})
		other = second_connection()
		try:
			self.assertEqual(
				other.sql("SELECT GET_LOCK(%s, 0)", (relay.LOCK_NAME,))[0][0], 1, "the lock was released"
			)
			other.sql("SELECT RELEASE_LOCK(%s)", (relay.LOCK_NAME,))
		finally:
			other.close()
		self.assertEqual(relay.assign_sequence(), 3)

	def test_the_relay_and_prune_are_scheduled(self):
		events = frappe.get_hooks("scheduler_events")
		self.assertIn("nxerp.shared.relay.assign_sequence", events["cron"]["* * * * *"])
		self.assertIn("nxerp.shared.relay.prune", events["daily"])

	# ---- pull, head, ack ----------------------------------------------------------------------------------

	def sequenced_customer_events(self):
		doc = self.customer()
		doc.customer_type = "Individual"
		doc.save()
		frappe.db.commit()
		relay.assign_sequence()
		return doc

	def test_pull_returns_events_after_the_cursor_in_order_as_valid_envelopes(self):
		doc = self.sequenced_customer_events()
		result = feed.pull(after_seq=0, limit=1000)
		events = result["events"]
		self.assertEqual([e["seq"] for e in events], [1, 2])
		self.assertEqual({e["entity_id"] for e in events}, {doc.name})
		for event in events:
			self.assertEqual(registry.event_problems(event), [], event)
			self.assertEqual(event["tenant_id"], "ORG-001")
			self.assertEqual(event["source_app"], "erpnext")
		self.assertEqual(events[1]["payload"]["customer_type"], "Individual")
		self.assertEqual(result["next_seq"], 2)
		after = feed.pull(after_seq=1)
		self.assertEqual([e["seq"] for e in after["events"]], [2])
		self.assertEqual(feed.pull(after_seq=2), {"events": [], "next_seq": 2})
		self.assertEqual([e["seq"] for e in feed.pull(after_seq=0, limit=1)["events"]], [1])

	def test_pull_never_returns_a_row_that_has_no_sequence_yet(self):
		self.customer()
		frappe.db.commit()
		self.assertEqual(feed.pull()["events"], [])
		relay.assign_sequence()
		self.assertEqual(len(feed.pull()["events"]), 1)

	def test_head_reports_the_state_of_the_feed(self):
		self.sequenced_customer_events()
		self.customer()
		frappe.db.commit()
		head = feed.head()
		self.assertEqual((head["max_seq"], head["pending_count"], head["acked_through"]), (2, 1, 0))
		self.assertGreaterEqual(head["oldest_pending_age_seconds"], 0)
		feed.ack(2)
		self.assertEqual(feed.head()["acked_through"], 2)

	def test_ack_is_idempotent_never_lowers_and_stays_within_the_head(self):
		self.sequenced_customer_events()
		self.assertEqual(feed.ack(2), {"acked_through": 2, "acked": 2})
		self.assertEqual(feed.ack(2), {"acked_through": 2, "acked": 0})
		self.assertEqual(feed.ack(1), {"acked_through": 2, "acked": 0}, "an older ack never lowers it")
		self.assertEqual(frappe.db.count(DOCTYPE), 2, "ack never deletes")
		for bad in (3, -1, "x", None, True):
			with self.assertRaises(feed.FeedError, msg=repr(bad)):
				feed.ack(bad)

	def test_arguments_are_validated_with_422(self):
		for kwargs in ({"after_seq": -1}, {"after_seq": "x"}, {"limit": 0}, {"limit": 1001}, {"limit": "x"}):
			with self.assertRaises(feed.FeedError, msg=repr(kwargs)):
				feed.pull(**kwargs)
		self.assertEqual(feed.FeedError.http_status_code, 422)

	def test_read_methods_are_get_and_ack_is_post_only(self):
		methods = frappe.allowed_http_methods_for_whitelisted_func
		self.assertEqual(methods[feed.ack], ["POST"])
		for fn in (feed.head, feed.pull, feed.digest, feed.snapshot):
			self.assertEqual(methods[fn], ["GET"], fn.__name__)
		self.assertEqual(sorted(methods[feed.snapshot_by_ids]), ["GET", "POST"])

	# ---- who may call --------------------------------------------------------------------------------------

	def test_a_caller_without_the_role_is_refused_everywhere_and_the_reader_is_not(self):
		calls = (
			lambda: feed.head(),
			lambda: feed.pull(),
			lambda: feed.ack(0),
			lambda: feed.digest("customer"),
			lambda: feed.snapshot("customer"),
			lambda: feed.snapshot_by_ids("customer", []),
		)
		for user in (self.plain, "Guest"):
			frappe.set_user(user)
			for call in calls:
				with self.assertRaises(frappe.PermissionError, msg=user):
					call()
		frappe.set_user(self.reader)
		self.assertEqual(feed.head()["max_seq"], 0)
		self.assertEqual(feed.pull()["events"], [])
		frappe.set_user("Administrator")

	def test_the_feed_role_is_created_idempotently_without_desk_access(self):
		ensure_feed_role()
		ensure_feed_role()
		self.assertEqual(frappe.db.count("Role", {"name": ROLE}), 1)
		self.assertEqual(frappe.db.get_value("Role", ROLE, "desk_access"), 0)

	# ---- pruning -------------------------------------------------------------------------------------------

	def test_prune_removes_old_acked_rows_only(self):
		for entity in ("p-old-acked", "p-new-acked", "p-old-claimed", "p-old-pending"):
			self.event(entity)
		frappe.db.commit()
		relay.assign_sequence()
		old = add_days(now_datetime(), -30)
		for entity in ("p-old-acked", "p-new-acked"):
			frappe.db.sql(
				"UPDATE `tabNXERP Outbox Event` SET status = 'acked', acked_at = %s WHERE entity_id = %s",
				(old if entity == "p-old-acked" else now_datetime(), entity),
			)
		frappe.db.sql(
			"UPDATE `tabNXERP Outbox Event` SET creation = %s WHERE entity_id = 'p-old-claimed'", (old,)
		)
		frappe.db.sql(
			"UPDATE `tabNXERP Outbox Event` SET creation = %s, status = 'pending', seq = NULL WHERE entity_id = 'p-old-pending'",
			(old,),
		)
		frappe.db.commit()
		self.assertEqual(relay.prune(), 1)
		left = {r.entity_id for r in frappe.get_all(DOCTYPE, fields=["entity_id"])}
		self.assertEqual(left, {"p-new-acked", "p-old-claimed", "p-old-pending"})

	def test_prune_retention_is_configurable(self):
		self.event("q1")
		frappe.db.commit()
		relay.assign_sequence()
		frappe.db.sql(
			"UPDATE `tabNXERP Outbox Event` SET status = 'acked', acked_at = %s",
			(add_days(now_datetime(), -3),),
		)
		frappe.db.commit()
		self.assertEqual(relay.prune(), 0, "the default retention is 14 days")
		frappe.local.conf["nxerp_outbox_retention_days"] = 2
		self.assertEqual(relay.prune(), 1)

	# ---- digest and snapshot -------------------------------------------------------------------------------

	def test_digest_and_snapshot_return_only_contract_fields(self):
		marker = "NXT-TAX-FEED-0001"
		doc = self.customer(tax_id=marker)
		frappe.db.commit()
		snap = _find(feed.snapshot, "customer", doc.name)
		self.assertEqual(sorted(snap["payload"]), sorted(CUSTOMER_FIELDS))
		self.assertEqual(sorted(snap), ["entity_id", "payload", "source_modified"])
		entry = _find(feed.digest, "customer", doc.name)
		self.assertEqual(sorted(entry), ["deleted", "entity_id", "payload_hash", "source_modified"])
		self.assertEqual(entry["payload_hash"], digest.payload_hash(snap["payload"]))
		self.assertEqual(entry["deleted"], 0)
		self.assertNotIn(marker, json.dumps([snap, entry]))
		by_ids = feed.snapshot_by_ids("customer", [doc.name, "no-such-customer"])
		self.assertEqual([i["entity_id"] for i in by_ids["items"]], [doc.name])
		self.assertEqual(by_ids["missing"], ["no-such-customer"])
		self.assertNotIn(marker, json.dumps(by_ids))
		as_json = feed.snapshot_by_ids("customer", json.dumps([doc.name]))
		self.assertEqual(len(as_json["items"]), 1)

	def test_digest_can_ask_for_recently_modified_documents_only(self):
		doc = self.customer()
		frappe.db.commit()
		names = [
			i["entity_id"]
			for i in feed.digest("customer", modified_since=add_days(now_datetime(), -1))["items"]
		]
		self.assertIn(doc.name, names)
		later = [
			i["entity_id"]
			for i in feed.digest("customer", modified_since=add_days(now_datetime(), 1))["items"]
		]
		self.assertNotIn(doc.name, later)
		with self.assertRaises(feed.FeedError):
			feed.digest("customer", modified_since="not a date")

	def test_pages_are_resumable_by_after_id(self):
		for _ in range(3):
			self.customer()
		frappe.db.commit()
		seen, after = [], ""
		for _ in range(50):
			page = feed.snapshot("customer", after_id=after, limit=2)
			seen += [i["entity_id"] for i in page["items"]]
			if not page["next_after_id"]:
				break
			after = page["next_after_id"]
		self.assertEqual(seen, sorted(set(seen)), "ordered by name, no repeats")
		self.assertGreaterEqual(len(seen), 3)

	def test_the_entity_type_selects_a_contract_and_nothing_else(self):
		for bad in (
			"employee_ref",
			"user_ref",
			"no_such_entity",
			"Customer",
			"tabCustomer",
			"customer; DROP",
			5,
			None,
			["customer"],
		):
			with self.assertRaises(feed.FeedError, msg=repr(bad)):
				feed.snapshot(bad)
			with self.assertRaises(feed.FeedError, msg=repr(bad)):
				feed.digest(bad)
		with self.assertRaises(feed.FeedError):
			feed.snapshot_by_ids("customer", ["x"] * 1001)
		with self.assertRaises(feed.FeedError):
			feed.snapshot_by_ids("customer", "not json")
		with self.assertRaises(feed.FeedError):
			feed.snapshot_by_ids("customer", [""])

	def test_a_document_that_cannot_be_projected_is_a_generic_500(self):
		doc = self.customer()
		frappe.db.commit()
		bad = copy.deepcopy(registry.get_contract("customer"))
		bad["fields"].append(
			{"shared": "region_code", "source": "no_such_field", "class": "S1", "type": "string"}
		)
		with patch.object(registry, "get_contract", return_value=bad):
			with self.assertRaises(feed.FeedProjectionError) as caught:
				feed.snapshot_by_ids("customer", [doc.name])
		self.assertEqual(caught.exception.http_status_code, 500)
		self.assertNotIn("no_such_field", str(caught.exception))

	# ---- off by default ------------------------------------------------------------------------------------

	def test_with_the_setting_off_the_feed_is_empty_and_the_jobs_do_nothing(self):
		self.customer()
		frappe.db.commit()
		frappe.local.conf.pop("nxerp_shared_publish")
		self.assertEqual(
			feed.head(),
			{"max_seq": 0, "pending_count": 0, "oldest_pending_age_seconds": 0, "acked_through": 0},
		)
		self.assertEqual(feed.pull(after_seq=0), {"events": [], "next_seq": 0})
		self.assertEqual(feed.ack(0), {"acked_through": 0, "acked": 0})
		self.assertEqual(feed.digest("customer"), {"items": [], "next_after_id": None})
		self.assertEqual(feed.snapshot("customer"), {"items": [], "next_after_id": None})
		self.assertEqual(feed.snapshot_by_ids("customer", ["x"]), {"items": [], "missing": []})
		self.assertEqual((relay.assign_sequence(), relay.prune()), (0, 0))
		with self.assertRaises(feed.FeedError, msg="a malformed argument is still refused"):
			feed.pull(after_seq="x")


def _find(fn, entity_type, entity_id):
	"""Page through a digest or snapshot until the entity shows up."""
	after = ""
	for _ in range(200):
		page = fn(entity_type, after_id=after, limit=500)
		for item in page["items"]:
			if item["entity_id"] == entity_id:
				return item
		if not page["next_after_id"]:
			break
		after = page["next_after_id"]
	raise AssertionError(f"{entity_id} not found")
