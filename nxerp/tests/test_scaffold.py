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

	def test_no_session_or_request_hooks_registered(self):
		# Behaviour hooks must be added deliberately in Phase 2, with their own tests.
		hooks = frappe.get_hooks(app_name="nxerp")
		for hook in ("before_request", "after_request", "on_session_creation", "website_route_rules"):
			self.assertFalse(hooks.get(hook), f"{hook} is not expected in the Phase 1 scaffold")
