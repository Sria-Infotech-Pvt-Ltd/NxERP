"""The transactional outbox and the capture hooks (Phase 3B), on a dev site with ERPNext installed.

Run:  bench --site <site> run-tests --app nxerp --module nxerp.tests.test_outbox

Everything is off unless `nxerp_shared_publish` is set. These tests set it (and strict mode) for the current process
only, through `frappe.local.conf`; nothing is written to site config. Test data is a fake Customer and Contact
(`user@example.test`); it and its outbox rows are removed at the end of the class.
"""

import copy
import json
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from nxerp.shared import capture, digest, outbox, registry

DOCTYPE = "NXERP Outbox Event"
CUSTOMER_FIELDS = [
	"display_name",
	"customer_type",
	"customer_group",
	"territory",
	"disabled",
	"primary_contact_id",
]


def ensure_customer_masters():
	"""A Customer needs a Customer Group and a Territory; a site made without the setup wizard has none."""
	for doctype, root, child, parent_field in (
		("Customer Group", "All Customer Groups", "NXT Outbox Group", "parent_customer_group"),
		("Territory", "All Territories", "NXT Outbox Territory", "parent_territory"),
	):
		scrubbed = frappe.scrub(doctype)
		if not frappe.db.exists(doctype, root):
			frappe.get_doc({"doctype": doctype, f"{scrubbed}_name": root, "is_group": 1}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists(doctype, child):
			frappe.get_doc(
				{"doctype": doctype, f"{scrubbed}_name": child, "is_group": 0, parent_field: root}
			).insert(ignore_permissions=True)
	return "NXT Outbox Group", "NXT Outbox Territory"


def events_for(*entity_ids):
	"""Outbox rows for these entity ids, in the order they were written."""
	return frappe.get_all(
		DOCTYPE,
		filters={"entity_id": ["in", list(entity_ids)]},
		fields=[
			"name",
			"entity_type",
			"entity_id",
			"op",
			"payload",
			"payload_hash",
			"status",
			"seq",
			"source_app",
			"contract_version",
		],
		order_by="creation asc, name asc",
	)


class TestOutbox(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.group, cls.territory = ensure_customer_masters()
		cls.created: list = []  # (doctype, name)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for key in ("nxerp_shared_publish", "nxerp_shared_publish_strict"):
			frappe.local.conf.pop(key, None)
		ids = [name for _, name in cls.created]
		for doctype, name in reversed(cls.created):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		if ids:
			frappe.db.delete(DOCTYPE, {"entity_id": ["in", ids]})
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.conf["nxerp_shared_publish"] = 1
		frappe.local.conf["nxerp_shared_publish_strict"] = 1
		self.addCleanup(self._unset)

	@staticmethod
	def _unset():
		for key in ("nxerp_shared_publish", "nxerp_shared_publish_strict"):
			frappe.local.conf.pop(key, None)

	def customer(self, insert=True, **fields):
		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"NXT Outbox {uuid.uuid4().hex[:8]}",
				"customer_type": "Company",
				"customer_group": self.group,
				"territory": self.territory,
				**fields,
			}
		)
		if insert:
			doc.insert()
			self.created.append(("Customer", doc.name))
		return doc

	# ---- the lifecycle -------------------------------------------------------------------------------------

	def test_insert_edit_rename_delete_produce_the_expected_rows(self):
		doc = self.customer()
		rows = events_for(doc.name)
		self.assertEqual(
			[(r.op, r.entity_type, r.entity_id) for r in rows], [("upsert", "customer", doc.name)]
		)
		self.assertEqual(
			json.loads(rows[0].payload),
			{
				"display_name": doc.customer_name,
				"customer_type": "Company",
				"customer_group": self.group,
				"territory": self.territory,
				"disabled": 0,
				"primary_contact_id": None,
			},
		)

		doc.customer_type = "Individual"
		doc.save()
		rows = events_for(doc.name)
		self.assertEqual([r.op for r in rows], ["upsert", "upsert"])
		self.assertEqual(json.loads(rows[1].payload)["customer_type"], "Individual")

		old = doc.name
		new = f"{old} renamed"
		frappe.rename_doc("Customer", old, new, force=True)
		self.created.append(("Customer", new))
		after_rename = events_for(old, new)
		self.assertEqual(
			[(r.op, r.entity_id) for r in after_rename[-2:]],
			[("delete", old), ("upsert", new)],
			"a rename ends with a delete of the old id then an upsert of the new id",
		)
		# ERPNext's own Customer.after_rename runs db_set, which fires on_change, so an upsert of the new id can come
		# first; it is harmless (the last event for the new id is an upsert) and documented in capture-notes.md
		self.assertTrue(all(r.op == "upsert" for r in after_rename[2:-2]))
		self.assertTrue(all(r.entity_id == new for r in after_rename[2:-2]))

		before = len(events_for(old, new))
		frappe.delete_doc("Customer", new, force=True)
		deleted = events_for(old, new)[before:]
		self.assertEqual(
			[(r.op, r.entity_id) for r in deleted], [("delete", new)], "on_change during delete is ignored"
		)
		self.assertIsNone(deleted[0].payload)

	def test_db_set_is_captured_because_it_fires_on_change(self):
		doc = self.customer()
		doc.db_set("customer_type", "Individual")
		rows = events_for(doc.name)
		self.assertEqual([r.op for r in rows], ["upsert", "upsert"])
		self.assertEqual(json.loads(rows[1].payload)["customer_type"], "Individual")

	def test_event_row_shape(self):
		doc = self.customer()
		row = events_for(doc.name)[0]
		uuid.UUID(row.name)  # the event id is a UUID
		self.assertEqual(
			(row.status, row.seq, row.source_app, row.contract_version),
			("pending", None, "erpnext", registry.get_contract("customer")["contract_version"]),
		)
		self.assertEqual(row.payload_hash, digest.payload_hash(json.loads(row.payload)))

	def test_two_saves_in_two_transactions_make_two_rows(self):
		doc = self.customer()
		frappe.db.commit()
		doc.customer_type = "Individual"
		doc.save()
		frappe.db.commit()
		rows = events_for(doc.name)
		self.assertEqual(len(rows), 2)
		self.assertNotEqual(rows[0].name, rows[1].name)

	# ---- atomicity (T15) -------------------------------------------------------------------------------------

	def test_a_rolled_back_save_publishes_nothing(self):
		frappe.db.commit()
		doc = self.customer(insert=False)
		try:
			doc.insert()
			self.assertEqual(len(events_for(doc.name)), 1, "the row is written in the same transaction")
			raise RuntimeError("the request fails after the save")
		except RuntimeError:
			frappe.db.rollback()
		self.assertFalse(frappe.db.exists("Customer", doc.name))
		self.assertEqual(events_for(doc.name), [])

	def test_a_database_error_writing_the_row_fails_the_business_save(self):
		doc = self.customer(insert=False)
		with patch.object(outbox, "write_event", side_effect=RuntimeError("database down")):
			with self.assertRaises(RuntimeError):
				doc.insert()
		frappe.db.rollback()
		self.assertFalse(frappe.db.exists("Customer", doc.name))

	# ---- what leaves the owner -------------------------------------------------------------------------------

	def test_a_field_outside_the_contract_never_reaches_the_payload(self):
		secret_marker = "NXT-TAX-0001"
		doc = self.customer(tax_id=secret_marker)
		row = events_for(doc.name)[0]
		self.assertEqual(sorted(json.loads(row.payload)), sorted(CUSTOMER_FIELDS))
		self.assertNotIn(secret_marker, row.payload)
		self.assertNotIn(secret_marker, json.dumps(row))

	def test_the_payload_has_exactly_the_contract_fields_for_every_active_entity(self):
		for entity, contract in registry.load_contracts().items():
			if contract["status"] == "active":
				self.assertEqual(
					[f["shared"] for f in contract["fields"]], registry.shared_fields(entity), entity
				)

	def test_a_contact_is_captured_with_its_derived_fields(self):
		customer = self.customer()
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "NXT",
				"last_name": uuid.uuid4().hex[:6],
				"email_ids": [{"email_id": "nxt-outbox@example.test", "is_primary": 1}],
				"phone_nos": [{"phone": "+10000000000", "is_primary_phone": 1}],
				"links": [{"link_doctype": "Customer", "link_name": customer.name}],
			}
		).insert()
		self.created.append(("Contact", contact.name))
		row = events_for(contact.name)[0]
		payload = json.loads(row.payload)
		self.assertEqual(row.entity_type, "contact")
		self.assertEqual(payload["customer_id"], customer.name)
		self.assertEqual(payload["email"], "nxt-outbox@example.test")
		self.assertEqual(payload["phone"], "+10000000000")
		self.assertEqual(
			sorted(payload), sorted(f["shared"] for f in registry.get_contract("contact")["fields"])
		)

	# ---- off by default, owner only ---------------------------------------------------------------------------

	def test_setting_off_produces_nothing(self):
		for value in (0, None):
			frappe.local.conf["nxerp_shared_publish"] = value
			doc = self.customer()
			doc.customer_type = "Individual"
			doc.save()
			frappe.delete_doc("Customer", doc.name, force=True)
			self.assertEqual(events_for(doc.name), [], f"setting = {value!r}")
		frappe.local.conf.pop("nxerp_shared_publish")
		doc = self.customer()
		self.assertEqual(events_for(doc.name), [], "setting unset")

	def test_a_site_without_the_owner_app_publishes_nothing(self):
		contract = copy.deepcopy(registry.get_contract("customer"))
		contract["owner_app"] = "crm_pro"  # an app that is not installed on this site
		with patch.object(registry, "contracts_for_doctype", return_value=[contract]):
			doc = self.customer()
		self.assertEqual(events_for(doc.name), [])

	# ---- a mistake in a contract ------------------------------------------------------------------------------

	def bad_contract(self):
		contract = copy.deepcopy(registry.get_contract("customer"))
		contract["fields"].append(
			{"shared": "region_code", "source": "no_such_field", "class": "S1", "type": "string"}
		)
		return contract

	def test_strict_mode_raises_on_a_contract_that_cannot_project(self):
		doc = self.customer(insert=False)
		with patch.object(registry, "contracts_for_doctype", return_value=[self.bad_contract()]):
			with self.assertRaises(digest.ProjectionError):
				doc.insert()
		frappe.db.rollback()

	def test_outside_strict_mode_a_bad_contract_writes_a_resync_and_the_save_succeeds(self):
		frappe.local.conf["nxerp_shared_publish_strict"] = 0
		doc = self.customer(insert=False)
		with patch.object(registry, "contracts_for_doctype", return_value=[self.bad_contract()]):
			doc.insert()
		self.created.append(("Customer", doc.name))
		self.assertTrue(frappe.db.exists("Customer", doc.name), "the business change is not blocked")
		rows = events_for(doc.name)
		self.assertEqual([(r.op, r.payload, r.payload_hash) for r in rows], [("resync", None, None)])

	def test_a_verify_field_missing_from_the_doctype_is_shared_as_empty_not_an_error(self):
		company = frappe.new_doc("Company")  # in memory only, nothing is inserted
		company.company_name = "NXT Example Co"
		payload = digest.project(registry.get_contract("org_unit"), company)
		self.assertEqual(payload, {"name": "NXT Example Co", "parent_id": None, "disabled": None})

	# ---- the DocType and the hooks ----------------------------------------------------------------------------

	def test_the_doctype_shape(self):
		meta = frappe.get_meta(DOCTYPE)
		for fieldname in (
			"seq",
			"source_app",
			"entity_type",
			"entity_id",
			"op",
			"contract_version",
			"source_modified",
			"payload",
			"payload_hash",
			"status",
			"claimed_at",
			"acked_at",
		):
			self.assertTrue(meta.has_field(fieldname), fieldname)
		self.assertEqual(meta.autoname, "UUID")
		self.assertEqual(
			[(p.role, p.read, p.write, p.create, p.delete) for p in meta.permissions],
			[("System Manager", 1, 0, 0, 0)],
		)
		indexes = {}
		for row in frappe.db.sql(f"SHOW INDEX FROM `tab{DOCTYPE}`", as_dict=True):
			indexes.setdefault(row.Key_name, []).append((row.Seq_in_index, row.Column_name, row.Non_unique))
		self.assertEqual(indexes["nxerp_outbox_status_creation"], [(1, "status", 1), (2, "creation", 1)])
		self.assertEqual(indexes["nxerp_outbox_entity"], [(1, "entity_type", 1), (2, "entity_id", 1)])
		unique_on_seq = [
			name for name, cols in indexes.items() if [c[1] for c in cols] == ["seq"] and cols[0][2] == 0
		]
		self.assertTrue(unique_on_seq, "seq has a unique index")

	def test_the_outbox_doctype_has_no_document_hooks(self):
		self.assertIsNone(frappe.get_doc_hooks().get(DOCTYPE))

	def test_the_hooks_are_generated_from_the_active_contracts_only(self):
		hooks = frappe.get_doc_hooks()
		for doctype in ("Customer", "Contact", "Company", "HD Ticket"):
			for event in registry.CAPTURE_EVENTS:
				self.assertIn(
					f"nxerp.shared.capture.{event}",
					_flatten(hooks.get(doctype, {}).get(event)),
					f"{doctype} {event}",
				)
		for planned in ("Employee", "Project"):
			self.assertNotIn(
				"nxerp.shared.capture.on_change", _flatten(hooks.get(planned, {}).get("on_change"))
			)
		self.assertIn(
			"nxerp.guard.validate_user",
			_flatten(hooks.get("User", {}).get("validate")),
			"the existing User hooks stay",
		)
		for event in registry.CAPTURE_EVENTS:
			self.assertTrue(callable(getattr(capture, event)))


def _flatten(value):
	if value is None:
		return []
	return [value] if isinstance(value, str) else list(value)
