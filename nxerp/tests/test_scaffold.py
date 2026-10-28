import os

import frappe
from frappe.tests import IntegrationTestCase

PLATFORM_MODULE = "NXERP Platform"


class TestScaffold(IntegrationTestCase):
	"""The platform app is installed, registers its hooks deliberately, and ships its palette."""

	def test_app_is_installed(self):
		self.assertIn("nxerp", frappe.get_installed_apps())

	def test_platform_module_is_registered(self):
		self.assertTrue(frappe.db.exists("Module Def", PLATFORM_MODULE))
		self.assertEqual(frappe.db.get_value("Module Def", PLATFORM_MODULE, "app_name"), "nxerp")

	def test_no_launcher_tile_registered(self):
		for tile in frappe.get_hooks("add_to_apps_screen"):
			self.assertNotEqual(tile.get("name"), "nxerp")

	def test_only_the_expected_hooks_are_registered(self):
		"""The platform's behaviour is exactly this set. Anything added here must come with its own tests
		and a line in docs/architecture/routes.md (or the access docs), so a new hook is never silent."""
		hooks = frappe.get_hooks(app_name="nxerp")
		# Phase 2: the access layer
		self.assertEqual(hooks.get("auth_hooks"), ["nxerp.enforcement.auth_hook"])
		self.assertEqual(hooks.get("after_request"), ["nxerp.enforcement.after_request"])
		self.assertEqual(hooks.get("has_permission"), {"*": ["nxerp.enforcement.has_permission"]})
		self.assertEqual(
			hooks.get("permission_query_conditions"), {"*": ["nxerp.enforcement.permission_query_conditions"]}
		)
		# Phase 3: sign-in routing and the launcher
		self.assertEqual(hooks.get("on_session_creation"), ["nxerp.routing.on_session_creation"])
		self.assertEqual(hooks.get("extend_bootinfo"), ["nxerp.launcher.extend_bootinfo"])
		self.assertEqual(
			hooks.get("override_whitelisted_methods"), {"frappe.apps.get_apps": ["nxerp.launcher.get_apps"]}
		)
		self.assertEqual(hooks.get("website_redirects"), [{"source": "/login/.+", "target": "/login"}])
		# nothing else reaches into requests or sessions
		for hook in (
			"before_request",
			"on_login",
			"on_logout",
			"website_route_rules",
			"get_website_user_home_page",
		):
			self.assertFalse(hooks.get(hook), f"{hook} is not expected")

	def test_desk_palette_is_registered_and_shipped(self):
		css = "/assets/nxerp/css/nxerp-desk-theme.css"
		self.assertIn(css, frappe.get_hooks("app_include_css", app_name="nxerp"))
		shipped = frappe.get_app_path("nxerp", "public", "css", "nxerp-desk-theme.css")
		self.assertTrue(
			os.path.exists(shipped), "run `yarn theme:build` in the Helpdesk repo and commit the output"
		)
