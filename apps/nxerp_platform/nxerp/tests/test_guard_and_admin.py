"""Grant management and the lockout guard: who may change access, what is audited, and what can
never be taken away. Includes the privilege-escalation cases (self-grant, non-admin grant, mass
assignment through the API)."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import access, guard
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


class TestGuardAndAdmin(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		purge_test_users()
		cls.created = []

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		delete_users(cls.created)
		frappe.db.rollback()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def user(self, prefix, roles=(), **kw):
		frappe.set_user("Administrator")
		doc = make_user(unique_email(prefix), roles, **kw)
		frappe.db.commit()  # so a rollback inside a test cannot discard the fixture
		self.created.append(doc.name)
		return doc.name

	def roles(self, user):
		frappe.clear_cache(user=user)
		return set(frappe.get_roles(user))

	# --- only a System Manager changes grants --------------------------------------------

	def test_a_normal_user_cannot_grant_through_the_api(self):
		actor = self.user("actor", ["Agent"])
		target = self.user("target", [PLAIN_DESK_ROLE])
		frappe.set_user(actor)
		with self.assertRaises(frappe.PermissionError):
			access_api.set_app_access(target, "erpnext", 1)
		with self.assertRaises(frappe.PermissionError):
			access_api.get_user_access(target)
		frappe.set_user("Administrator")
		self.assertNotIn(ERP_ACCESS, self.roles(target))

	def test_self_grant_through_a_user_record_is_blocked(self):
		# mass assignment: a user editing their own record (even bypassing Frappe's form permissions)
		actor = self.user("selfgrant", [PLAIN_DESK_ROLE])
		frappe.set_user(actor)
		doc = frappe.get_doc("User", actor)
		doc.append("roles", {"role": ERP_ACCESS})
		doc.flags.ignore_permissions = True
		with self.assertRaises(frappe.PermissionError):
			doc.save()

	def test_a_non_admin_cannot_revoke_a_grant_either(self):
		actor = self.user("revoker", [PLAIN_DESK_ROLE])
		target = self.user("revoked", [PLAIN_DESK_ROLE, ERP_ACCESS])
		frappe.set_user(actor)
		doc = frappe.get_doc("User", target)
		doc.roles = [r for r in doc.roles if r.role != ERP_ACCESS]
		doc.flags.ignore_permissions = True
		with self.assertRaises(frappe.PermissionError):
			doc.save()

	def test_a_system_manager_can_grant_and_revoke(self):
		admin = self.user("sm", ["System Manager"])
		target = self.user("grantee", [PLAIN_DESK_ROLE])
		frappe.set_user(admin)
		self.assertEqual(access_api.set_app_access(target, "erpnext", 1)["apps"], ["erpnext"])
		self.assertEqual(access_api.get_user_access(target)["apps"], ["erpnext"])
		self.assertEqual(access_api.set_app_access(target, "erpnext", 0)["apps"], [])

	def test_the_api_accepts_nothing_but_user_app_and_grant(self):
		admin = self.user("sm2", ["System Manager"])
		target = self.user("grantee2", [PLAIN_DESK_ROLE])
		frappe.set_user(admin)
		with self.assertRaises(TypeError):
			access_api.set_app_access(target, "erpnext", 1, roles=["System Manager"])
		with self.assertRaises(TypeError):
			access_api.set_app_access(target, "erpnext", 1, user_type="System User")

	def test_bad_arguments_are_rejected_cleanly(self):
		admin = self.user("sm3", ["System Manager"])
		frappe.set_user(admin)
		target = self.user("grantee3", [PLAIN_DESK_ROLE])
		frappe.set_user(admin)
		for args in (
			("no-such-user@example.test", "erpnext"),
			("Administrator", "erpnext"),
			("Guest", "erpnext"),
			(target, "no-such-app"),
			(target, None),
			(["x"], "erpnext"),
			(target, ["erpnext"]),
		):
			# Frappe also type-checks whitelisted arguments (FrappeTypeError) before our code runs
			with self.assertRaises(
				(frappe.ValidationError, frappe.DoesNotExistError, frappe.PermissionError, TypeError)
			):
				access_api.set_app_access(*args)

	def test_granting_an_access_role_never_changes_user_type(self):
		admin = self.user("sm4", ["System Manager"])
		customer = self.user("custtype", ["HD Customer"], user_type="Website User")
		frappe.set_user(admin)
		access_api.set_app_access(customer, "helpdesk", 1)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("User", customer, "user_type"), "Website User")
		self.assertEqual(access.get_user_apps(customer), [])  # still no staff apps

	# --- audit ---------------------------------------------------------------------------

	def test_grants_and_revocations_are_in_frappes_version_log(self):
		admin = self.user("sm5", ["System Manager"])
		target = self.user("audited", [PLAIN_DESK_ROLE])
		frappe.set_user(admin)
		access_api.set_app_access(target, "helpdesk", 1)
		access_api.set_app_access(target, "helpdesk", 0)
		versions = frappe.get_all(
			"Version",
			filters={"ref_doctype": "User", "docname": target},
			fields=["owner", "data"],
			order_by="creation asc",
		)
		blobs = [json.dumps(json.loads(v.data)) for v in versions]
		self.assertTrue(any(HD_ACCESS in b for b in blobs), "the grant must be recorded")
		self.assertGreaterEqual(len([b for b in blobs if HD_ACCESS in b]), 2, "grant and revocation recorded")
		self.assertTrue(all(v.owner == admin for v in versions[-2:]), "the actor is recorded")

	# --- lockout guard -------------------------------------------------------------------

	def test_administrator_cannot_be_disabled(self):
		doc = frappe.get_doc("User", "Administrator")
		doc.enabled = 0
		# Frappe refuses first (ValidationError); our guard is the second line of defence
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			doc.save()

	def test_the_last_named_system_manager_cannot_lose_the_role(self):
		last = self.user("lastadmin", ["System Manager"])
		doc = frappe.get_doc("User", last)
		doc.roles = [r for r in doc.roles if r.role != "System Manager"]
		doc.append("roles", {"role": PLAIN_DESK_ROLE})
		with patch.object(guard, "_named_admins", return_value=[]):
			with self.assertRaises(frappe.PermissionError):
				doc.save()
		frappe.db.rollback()
		doc = frappe.get_doc("User", last)
		doc.roles = [r for r in doc.roles if r.role != "System Manager"]
		doc.append("roles", {"role": PLAIN_DESK_ROLE})
		with patch.object(guard, "_named_admins", return_value=["someone-else"]):
			doc.save()  # another named administrator exists: allowed

	def test_the_last_named_system_manager_cannot_be_disabled_or_deleted(self):
		last = self.user("lastadmin2", ["System Manager"])
		doc = frappe.get_doc("User", last)
		doc.enabled = 0
		with patch.object(guard, "_named_admins", return_value=[]):
			with self.assertRaises(frappe.PermissionError):
				doc.save()
		frappe.db.rollback()
		with patch.object(guard, "_named_admins", return_value=[]):
			with self.assertRaises(frappe.PermissionError):
				frappe.delete_doc("User", last, force=True, ignore_permissions=True)

	def test_named_admin_detection(self):
		a = self.user("na1", ["System Manager"])
		b = self.user("na2", ["System Manager"], enabled=0)
		c = self.user("na3", [PLAIN_DESK_ROLE])
		admins = guard._named_admins()
		self.assertIn(a, admins)
		self.assertNotIn(b, admins)  # disabled
		self.assertNotIn(c, admins)  # no role
		self.assertNotIn("Administrator", admins)
		self.assertNotIn(a, guard._named_admins(exclude=a))

	def test_system_managers_keep_platform_admin_whatever_their_grants(self):
		admin = self.user("keepadmin", ["System Manager", ERP_ACCESS])
		frappe.set_user("Administrator")
		access_api.set_app_access(admin, "erpnext", 0)
		self.assertTrue(access.is_platform_admin(admin))
		self.assertEqual(access.get_user_apps(admin), [])

	def test_the_guard_does_not_block_install_and_patch_code(self):
		actor = self.user("patchactor", [PLAIN_DESK_ROLE])
		frappe.set_user(actor)
		doc = frappe.get_doc("User", actor)
		doc.append("roles", {"role": ERP_ACCESS})
		doc.flags.ignore_permissions = True
		frappe.flags.in_patch = True
		try:
			doc.save()
		finally:
			frappe.flags.in_patch = False
		self.assertIn(ERP_ACCESS, self.roles(actor))
