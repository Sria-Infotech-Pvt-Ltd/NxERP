from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import access, registry
from nxerp.api import access as access_api
from nxerp.tests.utils import (
	ERP_ACCESS,
	HD_ACCESS,
	PLAIN_DESK_ROLE,
	delete_users,
	make_user,
	purge_test_users,
	unique_email,
)

FAKE_ROLE = "NXERP Access: Projects"


def fake_projects_entry():
	# a third NXERP app, for the multi-app persona: not installed anywhere, so it is test-only
	return registry.AppEntry(
		key="projects",
		title="Projects",
		logo="/assets/projects/logo.png",
		route="/projects",
		order=15,
		app="frappe",  # "installed" because Frappe always is
		owns=("projects_pkg",),
		access_role=FAKE_ROLE,
	)


class TestAccessResolver(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		purge_test_users()
		if not frappe.db.exists("Role", FAKE_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": FAKE_ROLE, "desk_access": 0}).insert()
		cls.created = []

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		delete_users(cls.created)
		frappe.db.rollback()
		super().tearDownClass()

	def user(self, prefix, roles=(), **kw):
		frappe.set_user("Administrator")
		doc = make_user(unique_email(prefix), roles, **kw)
		self.created.append(doc.name)
		return doc.name

	def keys(self, user):
		return [e.key for e in access.get_user_apps(user)]

	# --- personas ------------------------------------------------------------------------

	def test_administrator_gets_every_installed_app(self):
		self.assertEqual(self.keys("Administrator"), ["erpnext", "helpdesk"])
		self.assertTrue(access.is_platform_admin("Administrator"))
		self.assertEqual(access.resolve_landing("Administrator")["mode"], "launcher")

	def test_system_manager_is_platform_admin_but_holds_no_app_by_default(self):
		user = self.user("sysmgr", ["System Manager"])
		self.assertTrue(access.is_platform_admin(user))
		self.assertEqual(self.keys(user), [])  # ADR-003: System Managers are not auto-granted apps
		self.assertEqual(access.resolve_landing(user)["mode"], "none")

	def test_helpdesk_only_agent_lands_directly_on_helpdesk(self):
		user = self.user("agent", ["Agent"])
		self.assertEqual(self.keys(user), ["helpdesk"])
		landing = access.resolve_landing(user)
		self.assertEqual((landing["mode"], landing["destination"]), ("direct", "/helpdesk/home"))
		self.assertFalse(access.can_access_app(user, "erpnext"))

	def test_explicit_access_role_also_grants_helpdesk(self):
		user = self.user("hdexplicit", [PLAIN_DESK_ROLE, HD_ACCESS])
		self.assertEqual(self.keys(user), ["helpdesk"])

	def test_erpnext_only_user(self):
		user = self.user("erp", ["Sales User", ERP_ACCESS])
		self.assertEqual(self.keys(user), ["erpnext"])
		landing = access.resolve_landing(user)
		self.assertEqual((landing["mode"], landing["destination"]), ("direct", "/desk"))
		self.assertFalse(access.can_access_app(user, "helpdesk"))

	def test_erpnext_business_roles_alone_do_not_grant_the_app(self):
		user = self.user("erproles", ["Sales User", "Accounts User"])
		self.assertEqual(self.keys(user), [])

	def test_user_with_both_apps_gets_the_launcher_in_order(self):
		user = self.user("both", ["Agent Manager", ERP_ACCESS])
		self.assertEqual(self.keys(user), ["erpnext", "helpdesk"])
		landing = access.resolve_landing(user)
		self.assertEqual((landing["mode"], landing["destination"]), ("launcher", "/nxerp/apps"))
		self.assertEqual([a["key"] for a in landing["apps"]], ["erpnext", "helpdesk"])

	def test_multi_app_manager_sees_exactly_their_apps_never_erpnext(self):
		with patch.object(registry, "APPS", (*registry.APPS, fake_projects_entry())):
			user = self.user("multi", ["Agent Manager", FAKE_ROLE])
			self.assertEqual(self.keys(user), ["projects", "helpdesk"])
			landing = access.resolve_landing(user)
			self.assertEqual(landing["mode"], "launcher")
			self.assertEqual([a["key"] for a in landing["apps"]], ["projects", "helpdesk"])
			self.assertNotIn("erpnext", [a["key"] for a in landing["apps"]])

	def test_customer_has_no_staff_apps_only_the_portal(self):
		user = self.user("cust", ["HD Customer"], user_type="Website User")
		self.assertEqual(self.keys(user), [])
		self.assertTrue(access.can_use_portal(user, "helpdesk"))
		self.assertFalse(access.can_use_portal(user, "erpnext"))
		self.assertFalse(access.is_platform_admin(user))
		landing = access.resolve_landing(user)
		self.assertEqual((landing["mode"], landing["destination"]), ("direct", "/helpdesk/my-tickets"))
		self.assertEqual(landing["apps"], [])

	def test_a_website_user_never_holds_staff_access_even_if_granted(self):
		# an administrator mistake must not turn a customer into staff
		user = self.user("custgrant", ["HD Customer", HD_ACCESS], user_type="Website User")
		self.assertEqual(self.keys(user), [])
		self.assertFalse(access.can_access_app(user, "helpdesk"))

	def test_guest_gets_nothing_and_is_sent_to_login(self):
		self.assertEqual(access.get_user_apps("Guest"), [])
		self.assertFalse(access.can_access_app("Guest", "helpdesk"))
		self.assertFalse(access.can_use_portal("Guest", "helpdesk"))
		self.assertEqual(
			access.resolve_landing("Guest"), {"mode": "none", "destination": "/login", "apps": []}
		)

	def test_disabled_user_has_no_access(self):
		user = self.user("disabled", ["Agent", ERP_ACCESS], enabled=0)
		self.assertEqual(self.keys(user), [])
		self.assertFalse(access.can_use_portal(user, "helpdesk"))
		self.assertEqual(access.resolve_landing(user)["mode"], "none")

	def test_user_with_no_apps_lands_on_no_access(self):
		user = self.user("noapps", [PLAIN_DESK_ROLE])
		landing = access.resolve_landing(user)
		self.assertEqual((landing["mode"], landing["destination"]), ("none", "/nxerp/no-access"))

	def test_unknown_and_uninstalled_apps_are_never_accessible(self):
		self.assertFalse(access.can_access_app("Administrator", "does-not-exist"))
		ghost = registry.AppEntry(
			"ghost", "Ghost", "", "/ghost", 99, "not_installed_app", ("g",), "NXERP Access: Ghost"
		)
		with patch.object(registry, "APPS", (*registry.APPS, ghost)):
			self.assertNotIn("ghost", self.keys("Administrator"))

	# --- revocation ---------------------------------------------------------------------

	def test_revocation_takes_effect_immediately_without_relogin(self):
		user = self.user("revoke", [PLAIN_DESK_ROLE])
		frappe.set_user("Administrator")

		result = access_api.set_app_access(user, "helpdesk", 1)
		self.assertEqual(result["apps"], ["helpdesk"])
		self.assertTrue(access.can_access_app(user, "helpdesk"))

		result = access_api.set_app_access(user, "helpdesk", 0)
		self.assertEqual(result["apps"], [])
		self.assertFalse(access.can_access_app(user, "helpdesk"))

	def test_revoking_helpdesk_also_removes_the_implied_agent_roles(self):
		user = self.user("revokeagent", ["Agent"])
		frappe.set_user("Administrator")
		self.assertEqual(self.keys(user), ["helpdesk"])
		access_api.set_app_access(user, "helpdesk", 0)
		self.assertEqual(self.keys(user), [])
		self.assertNotIn("Agent", frappe.get_roles(user))

	def test_disabling_a_user_revokes_everything(self):
		user = self.user("disablelater", ["Agent", ERP_ACCESS])
		self.assertEqual(self.keys(user), ["erpnext", "helpdesk"])
		frappe.set_user("Administrator")
		doc = frappe.get_doc("User", user)
		doc.enabled = 0
		doc.save()
		self.assertEqual(self.keys(user), [])

	def test_the_resolver_has_no_cache_of_its_own(self):
		# every answer is derived from frappe.get_roles, so Frappe's invalidation is the only one
		import inspect

		source = inspect.getsource(access)
		self.assertNotIn("frappe.cache", source)
		self.assertNotIn("site_cache", source)
		self.assertNotIn("lru_cache", source)
