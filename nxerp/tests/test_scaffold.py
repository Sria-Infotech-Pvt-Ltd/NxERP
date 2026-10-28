import os

import frappe
from frappe.tests import IntegrationTestCase

PLATFORM_MODULE = "NXERP Platform"


class TestScaffold(IntegrationTestCase):
	"""Phase 1 guard: the platform app is installed and registers no behaviour yet."""

	def test_app_is_installed(self):
		self.assertIn("nxerp", frappe.get_installed_apps())

	def test_platform_module_is_registered(self):
		self.assertTrue(frappe.db.exists("Module Def", PLATFORM_MODULE))
		self.assertEqual(frappe.db.get_value("Module Def", PLATFORM_MODULE, "app_name"), "nxerp")

	def test_no_launcher_tile_registered(self):
		for tile in frappe.get_hooks("add_to_apps_screen"):
			self.assertNotEqual(tile.get("name"), "nxerp")

	def test_only_the_access_layer_hooks_are_registered(self):
		"""Phase 2 registers the access layer and nothing else. Login override, post-login redirect and
		website routes are Phase 3 and must be added deliberately, with their own tests."""
		hooks = frappe.get_hooks(app_name="nxerp")
		self.assertEqual(hooks.get("auth_hooks"), ["nxerp.enforcement.auth_hook"])
		self.assertEqual(hooks.get("after_request"), ["nxerp.enforcement.after_request"])
		self.assertEqual(hooks.get("has_permission"), {"*": ["nxerp.enforcement.has_permission"]})
		self.assertEqual(
			hooks.get("permission_query_conditions"), {"*": ["nxerp.enforcement.permission_query_conditions"]}
		)
		for hook in (
			"before_request",
			"on_session_creation",
			"on_login",
			"website_route_rules",
			"website_redirects",
		):
			self.assertFalse(hooks.get(hook), f"{hook} is not expected before Phase 3")

	def test_desk_palette_is_registered_and_shipped(self):
		css = "/assets/nxerp/css/nxerp-desk-theme.css"
		self.assertIn(css, frappe.get_hooks("app_include_css", app_name="nxerp"))
		shipped = frappe.get_app_path("nxerp", "public", "css", "nxerp-desk-theme.css")
		self.assertTrue(
			os.path.exists(shipped), "run `yarn theme:build` in the Helpdesk repo and commit the output"
		)
