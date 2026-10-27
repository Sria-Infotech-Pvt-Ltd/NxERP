"""Regression: the access layer must not break ERPNext for a user who is allowed to use it.

An authorised ERPNext user loads Desk, creates master records (Customer, Item) and reads them back,
over real HTTP. The same user without the access grant is refused, even though they hold the same
ERPNext business roles, proving the gate (not a missing role) is what changed.
"""

import secrets

import frappe
from frappe.tests import IntegrationTestCase

from nxerp.api import access as access_api
from nxerp.tests.utils import (
	ERP_ACCESS,
	Client,
	allow_many_test_users,
	delete_users,
	denied_by_gate,
	make_user,
	purge_test_users,
	unique_email,
)

ERP_BUSINESS_ROLES = ("Sales User", "Sales Manager", "Accounts User", "Item Manager", "Stock Manager")


class TestErpnextSmoke(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		allow_many_test_users()
		purge_test_users()
		cls.pw = secrets.token_urlsafe(16)
		cls.user = make_user(
			unique_email("erpsmoke"), (*ERP_BUSINESS_ROLES, ERP_ACCESS), password=cls.pw
		).name
		cls.created_docs = []
		frappe.db.commit()
		cls.client = Client(cls.user, cls.pw)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for doctype, name in reversed(cls.created_docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		delete_users([cls.user])
		frappe.db.commit()
		super().tearDownClass()

	def test_authorised_user_loads_desk(self):
		resp = self.client.get("/desk")
		self.assertEqual(resp.status_code, 200)
		self.assertFalse(denied_by_gate(resp))

	def test_authorised_user_creates_and_reads_a_customer(self):
		group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		name = f"NXT Smoke Customer {secrets.token_hex(3)}"
		created = self.client.post(
			"/api/resource/Customer",
			json_body={"customer_name": name, "customer_group": group, "territory": territory},
		)
		self.assertEqual(created.status_code, 200, created.text[:300])
		doc_name = created.json()["data"]["name"]
		self.created_docs.append(("Customer", doc_name))

		read = self.client.get(f"/api/resource/Customer/{doc_name}")
		self.assertEqual(read.status_code, 200)
		self.assertEqual(read.json()["data"]["customer_name"], name)

		listed = self.client.get('/api/resource/Customer?fields=["name"]&limit_page_length=500')
		self.assertIn(doc_name, listed.text)

	def test_authorised_user_creates_and_reads_an_item(self):
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		code = f"NXT-SMOKE-{secrets.token_hex(3)}"
		created = self.client.post(
			"/api/resource/Item",
			json_body={"item_code": code, "item_name": code, "item_group": item_group, "stock_uom": "Nos"},
		)
		self.assertEqual(created.status_code, 200, created.text[:300])
		self.created_docs.append(("Item", created.json()["data"]["name"]))
		read = self.client.get(f"/api/resource/Item/{code}")
		self.assertEqual(read.status_code, 200)
		self.assertEqual(read.json()["data"]["item_group"], item_group)

	def test_same_business_roles_without_the_grant_are_refused_then_allowed_when_granted(self):
		frappe.set_user("Administrator")
		email = make_user(unique_email("erpnogrant"), ERP_BUSINESS_ROLES, password=self.pw).name
		frappe.db.commit()
		try:
			client = Client(email, self.pw)
			self.assertTrue(denied_by_gate(client.get("/desk")))
			self.assertTrue(denied_by_gate(client.get("/api/resource/Customer?limit_page_length=1")))

			access_api.set_app_access(email, "erpnext", 1)
			frappe.db.commit()
			# the same session, no re-login
			self.assertEqual(client.get("/desk").status_code, 200)
			self.assertEqual(client.get("/api/resource/Customer?limit_page_length=1").status_code, 200)

			access_api.set_app_access(email, "erpnext", 0)
			frappe.db.commit()
			self.assertTrue(denied_by_gate(client.get("/desk")))
		finally:
			frappe.set_user("Administrator")
			delete_users([email])
			frappe.db.commit()
