import frappe
from frappe.tests import IntegrationTestCase

from nxerp import registry


class TestRegistry(IntegrationTestCase):
	def test_keys_and_roles_are_unique(self):
		keys = [e.key for e in registry.get_registry()]
		roles = [e.access_role for e in registry.get_registry()]
		self.assertEqual(len(keys), len(set(keys)))
		self.assertEqual(len(roles), len(set(roles)))

	def test_frappe_framework_is_not_an_nxerp_app(self):
		for entry in registry.get_registry():
			self.assertNotEqual(entry.app, "frappe")
			self.assertNotIn("frappe", entry.owns)

	def test_only_installed_apps_are_active(self):
		installed = set(frappe.get_installed_apps())
		for entry in registry.installed_entries():
			self.assertIn(entry.app, installed)

	def test_active_entries_follow_launcher_order(self):
		orders = [e.order for e in registry.installed_entries()]
		self.assertEqual(orders, sorted(orders))

	def test_lookup_by_doctype_module_package_and_path(self):
		self.assertEqual(registry.entry_for_doctype("Customer").key, "erpnext")
		self.assertEqual(registry.entry_for_doctype("HD Ticket").key, "helpdesk")
		self.assertEqual(registry.entry_for_package("erpnext").key, "erpnext")
		self.assertEqual(registry.entry_for_package("payments").key, "erpnext")
		self.assertEqual(registry.entry_for_path("/helpdesk/home")[0].key, "helpdesk")
		self.assertEqual(registry.entry_for_path("/desk/user")[0].key, "erpnext")

	def test_shared_core_doctypes_belong_to_no_app(self):
		for doctype in ("User", "File", "Comment", "ToDo", "Notification Log", "Contact", "Role", "DocShare"):
			self.assertIsNone(registry.entry_for_doctype(doctype), doctype)

	def test_unknown_inputs_are_shared_not_errors(self):
		self.assertIsNone(registry.entry_for_doctype("No Such DocType"))
		self.assertIsNone(registry.entry_for_doctype(None))
		self.assertIsNone(registry.entry_for_doctype(["x"]))
		self.assertIsNone(registry.entry_for_package("frappe"))
		self.assertEqual(registry.entry_for_path("/api/method/ping"), (None, None))

	def test_path_prefixes_match_whole_segments(self):
		self.assertEqual(registry.entry_for_path("/helpdesk-evil/x"), (None, None))
		self.assertEqual(registry.entry_for_path("/desktop"), (None, None))

	def test_access_roles_exist_after_migrate(self):
		for entry in registry.installed_entries():
			self.assertTrue(frappe.db.exists("Role", entry.access_role), entry.access_role)
			self.assertEqual(frappe.db.get_value("Role", entry.access_role, "desk_access"), 0)
