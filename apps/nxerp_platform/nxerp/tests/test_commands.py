"""The owner-side command API (Phase 7A, T19), on a site that has ERPNext (the owner of customer and contact).

Real documents, real permissions, real outbox: the command is called in process as the service user, and every assertion is made on the
database afterwards. Fake data only. Everything is rolled back at the end.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from nxerp.shared import command, registry
from nxerp.tests.test_outbox import ensure_customer_masters, events_for
from nxerp.tests.utils import PLAIN_DESK_ROLE, delete_users, make_user, purge_test_users, unique_email

NEEDS_ROLE = "NXERP Access: ERPNext"


def status() -> int:
	return frappe.local.response.get("http_status_code") or 200


class TestCommands(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		purge_test_users()
		cls.created = []
		cls.group, cls.territory = ensure_customer_masters()
		for doctype, name, parent_field, root in (
			("Customer Group", "NXT Command Group", "parent_customer_group", "All Customer Groups"),
			("Territory", "NXT Command Territory", "parent_territory", "All Territories"),
		):
			if not frappe.db.exists(doctype, name):
				frappe.get_doc(
					{
						"doctype": doctype,
						f"{frappe.scrub(doctype)}_name": name,
						"is_group": 0,
						parent_field: root,
					}
				).insert(ignore_permissions=True)
		for role in (command.CALLER_ROLE, NEEDS_ROLE):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 0}).insert(
					ignore_permissions=True
				)

		def mk(*roles, **kw):
			doc = make_user(unique_email("cmd"), [PLAIN_DESK_ROLE, *roles], **kw)
			cls.created.append(doc.name)
			return doc.name

		cls.caller = mk(command.CALLER_ROLE)
		cls.caller_without_role = mk()
		cls.agent = mk("Sales User", "Sales Manager", NEEDS_ROLE)  # may change a Customer and a Contact
		cls.no_write = mk(NEEDS_ROLE)  # holds the command's role but no permission on Customer
		cls.no_command_role = mk(
			"Sales User", "Sales Manager"
		)  # may write a Customer but is not allowed to use the command
		cls.disabled_agent = mk("Sales User", NEEDS_ROLE, enabled=0)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		delete_users(cls.created)
		frappe.db.rollback()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.local.response["http_status_code"] = 200
		for p in (
			patch.dict(
				frappe.conf, {command.CALLERS_KEY: {self.caller: "helpdesk"}, "nxerp_shared_publish": 1}
			),
		):
			p.start()
			self.addCleanup(p.stop)
		self.addCleanup(frappe.set_user, "Administrator")
		self.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"NXT Command Customer {frappe.generate_hash(length=6)}",
				"customer_group": self.group,
				"territory": self.territory,
				"customer_type": "Company",
			}
		).insert(ignore_permissions=True)

	def key(self, label="k"):
		return f"{label}-{frappe.generate_hash(length=14)}"

	def call(
		self,
		fields,
		*,
		key=None,
		command_name="request_change",
		entity="customer",
		entity_id=None,
		acting=None,
		expected=None,
		as_user=None,
	):
		frappe.set_user(as_user or self.caller)
		try:
			return command.apply(
				entity_type=entity,
				entity_id=entity_id or self.customer.name,
				command=command_name,
				fields=json.dumps(fields) if isinstance(fields, dict) else fields,
				expected_version=expected,
				idempotency_key=key or self.key(),
				acting_user=self.agent if acting is None else acting,
			)
		finally:
			frappe.set_user("Administrator")

	def reload(self):
		return frappe.get_doc("Customer", self.customer.name)

	def log_rows(self, key=None):
		filters = {"idempotency_key": key} if key else {}
		return frappe.get_all(command.LOG_DOCTYPE, filters=filters, pluck="name")

	# --- T19 -------------------------------------------------------------------------------------------------------------------------------

	def test_t19_a_valid_command_changes_the_document_and_exactly_one_outbox_row_follows(self):
		before = len(events_for(self.customer.name))
		result = self.call({"customer_group": "NXT Command Group", "territory": "NXT Command Territory"})
		self.assertEqual(status(), 200)
		self.assertTrue(result["ok"])
		doc = self.reload()
		self.assertEqual((doc.customer_group, doc.territory), ("NXT Command Group", "NXT Command Territory"))
		self.assertEqual(
			doc.modified_by, self.agent, "the change is the acting user's, not the service user's"
		)
		self.assertEqual(result["source_modified"], command._stamp(doc.modified))
		events = events_for(self.customer.name)
		self.assertEqual(
			len(events) - before,
			1,
			"one change, one outbox row (written by the Phase 3 capture, not by the command)",
		)
		self.assertEqual(events[-1].op, "upsert")
		self.assertEqual(json.loads(events[-1].payload)["customer_group"], "NXT Command Group")

	def test_a_repeat_with_the_same_key_changes_nothing_and_returns_the_first_result(self):
		key = self.key("same")
		first = self.call({"territory": "NXT Command Territory"}, key=key)
		events = len(events_for(self.customer.name))
		modified = self.reload().modified
		again = self.call(
			{"territory": self.territory}, key=key
		)  # even with different values: it is the same request
		self.assertEqual(first, again)
		self.assertEqual(self.reload().territory, "NXT Command Territory")
		self.assertEqual(self.reload().modified, modified)
		self.assertEqual(len(events_for(self.customer.name)), events)
		self.assertEqual(len(self.log_rows(key)), 1)

	def test_a_key_reused_for_a_different_request_is_a_conflict(self):
		key = self.key("reuse")
		self.call({"territory": "NXT Command Territory"}, key=key)
		other = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"NXT Other {frappe.generate_hash(length=6)}",
				"customer_group": self.group,
				"territory": self.territory,
			}
		).insert(ignore_permissions=True)
		result = self.call({"territory": "NXT Command Territory"}, key=key, entity_id=other.name)
		self.assertEqual((status(), result["error"]), (409, "idempotency_key_reused"))

	def test_a_field_outside_writable_fields_is_422_and_changes_nothing(self):
		for bad in (
			{"customer_name": "Renamed"},
			{"display_name": "Renamed"},
			{"tax_id": "123"},
			{"name": "X"},
			{"territory": "NXT Command Territory", "disabled": 1},
			{"customer_type": "Individual"},
		):
			key = self.key("bad")
			result = self.call(bad, key=key)
			self.assertEqual((status(), result["error"]), (422, "field_not_writable"), bad)
			self.assertEqual(self.log_rows(key), [], "a refused request stores nothing")
		doc = self.reload()
		self.assertEqual(
			(doc.customer_name, doc.territory, doc.customer_type),
			(self.customer.customer_name, self.territory, "Company"),
		)

	def test_a_caller_without_the_role_or_not_listed_for_the_command_is_403(self):
		result = self.call({"territory": "NXT Command Territory"}, as_user=self.caller_without_role)
		self.assertEqual((status(), result["error"]), (403, "forbidden"))
		for mapping in ({}, {self.caller: "erpnext"}, {self.caller: "hrms"}, {"someone-else": "helpdesk"}):
			with patch.dict(frappe.conf, {command.CALLERS_KEY: mapping}):
				result = self.call({"territory": "NXT Command Territory"})
				self.assertEqual((status(), result["error"]), (403, "forbidden"), mapping)
		with patch.dict(frappe.conf, {command.CALLERS_KEY: "not a mapping"}):
			self.assertEqual(self.call({"territory": "NXT Command Territory"})["error"], "forbidden")
		self.assertEqual(self.reload().territory, self.territory)
		self.assertEqual(len(events_for(self.customer.name)), 1)  # only the insert of the fixture

	def test_an_acting_user_without_permission_is_403_and_changes_nothing(self):
		key = self.key("noperm")
		result = self.call({"territory": "NXT Command Territory"}, key=key, acting=self.no_write)
		self.assertEqual((status(), result["error"]), (403, "forbidden"))
		self.assertEqual(self.reload().territory, self.territory)
		self.assertEqual(self.log_rows(key), [], "the log row is rolled back with the refused change")

	def test_the_acting_user_must_be_a_real_enabled_person_who_may_use_the_command(self):
		cases = {
			"someone-who-does-not-exist@example.test": "acting_user_invalid",
			self.disabled_agent: "acting_user_invalid",
			"Administrator": "acting_user_invalid",
			"Guest": "acting_user_invalid",
			"": "acting_user_invalid",
			self.no_command_role: "acting_user_forbidden",
		}
		for user, code in cases.items():
			key = self.key("acting")
			result = self.call({"territory": "NXT Command Territory"}, key=key, acting=user)
			self.assertEqual((status(), result["error"]), (403, code), user)
			self.assertEqual(self.log_rows(key), [])
		self.assertEqual(self.reload().territory, self.territory)

	def test_a_stale_expected_version_is_409_and_the_current_one_is_accepted(self):
		stale = command._stamp(add_to_date(self.customer.modified, seconds=-30))
		key = self.key("stale")
		result = self.call({"territory": "NXT Command Territory"}, key=key, expected=stale)
		self.assertEqual((status(), result["error"]), (409, "version_conflict"))
		self.assertEqual(self.reload().territory, self.territory)
		self.assertEqual(self.log_rows(key), [])
		fresh = self.call(
			{"territory": "NXT Command Territory"}, expected=command._stamp(self.reload().modified)
		)
		self.assertTrue(fresh["ok"])

	def test_a_failing_validation_rolls_back_the_document_and_the_log_row(self):
		key = self.key("invalid")
		result = self.call({"territory": "No Such Territory"}, key=key)
		self.assertEqual((status(), result["error"]), (422, "validation_failed"))
		self.assertEqual(self.reload().territory, self.territory)
		self.assertEqual(self.log_rows(key), [])
		self.assertEqual(len(events_for(self.customer.name)), 1)

	def test_an_entity_or_command_not_in_a_contract_is_404(self):
		for entity, name in (
			("org_unit", "request_change"),
			("ticket_summary", "x.y"),
			("customer", "delete"),
			("customer", "contact.update_contact"),
			("nothing", "request_change"),
			("employee_ref", "update"),
		):
			result = self.call({"territory": "x"}, entity=entity, command_name=name)
			self.assertEqual((status(), result["error"]), (404, "unknown_command"), (entity, name))

	def test_a_missing_record_and_bad_input_are_refused_without_a_trace(self):
		result = self.call({"territory": "NXT Command Territory"}, entity_id="NO-SUCH-CUSTOMER")
		self.assertEqual((status(), result["error"]), (404, "not_found"))
		for fields in (
			"not json",
			"[]",
			"{}",
			None,
			json.dumps({"territory": "x" * 600}),
			json.dumps({"territory": ["a"]}),
		):
			result = self.call(fields)
			self.assertEqual(status(), 422, fields)
			self.assertIn(result["error"], ("bad_request", "field_not_writable"))
		for key in ("short", "has space in it!", "x" * 200):
			self.assertEqual(
				self.call({"territory": "NXT Command Territory"}, key=key)["error"], "bad_idempotency_key"
			)

	def test_the_rate_limit_is_429(self):
		with (
			patch.object(command, "RATE_LIMIT_PER_MINUTE", 2),
			patch.object(command.frappe.cache, "incrby", side_effect=[1, 2, 3, 4]),
		):
			ok1 = self.call({"territory": "NXT Command Territory"})
			ok2 = self.call({"territory": "NXT Command Territory"})
			limited = self.call({"territory": "NXT Command Territory"})
		self.assertTrue(ok1["ok"] and ok2["ok"])
		self.assertEqual((status(), limited["error"]), (429, "rate_limited"))

	def test_an_unexpected_failure_is_503_without_a_stack_trace_and_stores_nothing(self):
		key = self.key("boom")
		with patch.object(command, "_apply_fields", side_effect=RuntimeError("secret detail Traceback")):
			result = self.call({"territory": "NXT Command Territory"}, key=key)
		self.assertEqual((status(), result["error"]), (503, "unavailable"))
		self.assertNotIn("secret detail", json.dumps(result))
		self.assertNotIn("Traceback", json.dumps(result))
		self.assertEqual(self.log_rows(key), [])
		retry = self.call(
			{"territory": "NXT Command Territory"}, key=key
		)  # a retry with the same key after a 5xx is safe
		self.assertTrue(retry["ok"])

	def test_update_contact_changes_the_primary_email_and_phone_and_the_name(self):
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Old",
				"last_name": "Name",
				"email_ids": [{"email_id": "old@example.test", "is_primary": 1}],
				"phone_nos": [{"phone": "+10000000001", "is_primary_phone": 1}],
			}
		).insert(ignore_permissions=True)
		result = self.call(
			{"full_name": "New Person", "email": "new@example.test", "phone": "+10000000002"},
			command_name="update_contact",
			entity="contact",
			entity_id=contact.name,
		)
		self.assertTrue(result["ok"], result)
		doc = frappe.get_doc("Contact", contact.name)
		self.assertEqual((doc.first_name, doc.last_name), ("New", "Person"))
		self.assertEqual([r.email_id for r in doc.email_ids if r.is_primary], ["new@example.test"])
		self.assertEqual([r.phone for r in doc.phone_nos if r.is_primary_phone], ["+10000000002"])
		self.assertEqual(len(doc.email_ids), 1, "the primary row is changed, not duplicated")
		for bad in ({"email": "not-an-email"}, {"email": ""}, {"phone": ""}, {"full_name": " "}):
			again = self.call(bad, command_name="update_contact", entity="contact", entity_id=contact.name)
			self.assertEqual((status(), again["error"]), (422, "validation_failed"), bad)

	def test_the_log_prune_removes_only_rows_older_than_24_hours(self):
		for name, hours in (("old-key-1234567", 30), ("new-key-1234567", 1)):
			row = frappe.get_doc(
				{
					"doctype": command.LOG_DOCTYPE,
					"idempotency_key": name,
					"caller_app": "helpdesk",
					"entity_type": "customer",
					"entity_id": "X",
					"command": "customer.request_change",
				}
			).insert(ignore_permissions=True)
			frappe.db.set_value(
				command.LOG_DOCTYPE,
				row.name,
				"creation",
				add_to_date(now_datetime(), hours=-hours),
				update_modified=False,
			)
		self.assertGreaterEqual(command.prune_log(), 1)
		self.assertEqual(self.log_rows("old-key-1234567"), [])
		self.assertEqual(len(self.log_rows("new-key-1234567")), 1)

	def test_the_log_never_holds_a_field_value_and_the_code_never_ignores_permissions(self):
		key = self.key("novalue")
		self.call({"territory": "NXT Command Territory"}, key=key)
		row = frappe.get_all(command.LOG_DOCTYPE, filters={"idempotency_key": key}, fields=["*"])[0]
		self.assertNotIn("NXT Command Territory", json.dumps(row, default=str))
		import inspect

		source = inspect.getsource(command)
		self.assertNotIn("save(ignore_permissions", source)
		self.assertNotIn("flags.ignore_permissions", source)
		self.assertNotIn("frappe.db.sql", source)
		self.assertNotIn("db.set_value(contract", source)

	def test_every_contract_command_is_a_known_shape(self):
		"""Every command in every active contract names callers, writable fields that exist, and a role."""
		for entity_type, contract in registry.load_contracts().items():
			for item in contract["commands"]:
				self.assertTrue(item["callers"], (entity_type, item["name"]))
				shared = {f["shared"] for f in contract["fields"]}
				self.assertLessEqual(set(item["writable_fields"]), shared)
		self.assertEqual(registry.command_for("customer", "request_change")["callers"], ["helpdesk"])
		self.assertIsNone(registry.command_for("customer", "nope"))
		self.assertIsNone(registry.command_for("employee_ref", "update"))  # planned entity: no commands
