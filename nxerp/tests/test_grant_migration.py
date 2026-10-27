"""The grant-migration tool: suggests grants for people who used an app before access became a grant."""

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import migration
from nxerp.tests.utils import (
	ERP_ACCESS,
	PLAIN_DESK_ROLE,
	delete_users,
	make_user,
	purge_test_users,
	unique_email,
)


class TestGrantMigration(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		purge_test_users()
		cls.created = []

		def mk(prefix, roles, **kw):
			doc = make_user(unique_email(prefix), roles, **kw)
			cls.created.append(doc.name)
			return doc.name

		cls.erp_old = mk("m-erp", ["Sales User"])  # used ERPNext before; has no grant
		cls.erp_granted = mk("m-granted", ["Sales User", ERP_ACCESS])
		cls.agent = mk("m-agent", ["Agent"])  # Helpdesk access is implied by the role already
		cls.plain = mk("m-plain", [PLAIN_DESK_ROLE])
		cls.sysmgr = mk("m-sys", ["System Manager"])
		cls.disabled = mk("m-off", ["Sales User"], enabled=0)
		cls.customer = mk("m-cust", ["Customer"], user_type="Website User")

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		delete_users(cls.created)
		frappe.db.rollback()
		super().tearDownClass()

	def mine(self, suggestions):
		return {(s["user"], s["app"]) for s in suggestions if s["user"] in self.created}

	def test_suggests_a_grant_only_for_people_who_need_one(self):
		found = self.mine(migration.find_suggestions(self.created))
		self.assertIn((self.erp_old, "erpnext"), found)
		for user in (self.erp_granted, self.agent, self.plain, self.sysmgr, self.disabled, self.customer):
			self.assertNotIn((user, "erpnext"), found, user)
			self.assertNotIn((user, "helpdesk"), found, user)

	def test_a_dry_run_changes_nothing_and_apply_grants_then_is_idempotent(self):
		before = set(frappe.get_roles(self.erp_old))
		migration.suggest_grants(only=self.created)  # dry run
		self.assertEqual(set(frappe.get_roles(self.erp_old)), before)

		migration.suggest_grants(apply=True, only=self.created)
		frappe.clear_cache(user=self.erp_old)
		self.assertIn(ERP_ACCESS, frappe.get_roles(self.erp_old))
		self.assertNotIn((self.erp_old, "erpnext"), self.mine(migration.find_suggestions(self.created)))
