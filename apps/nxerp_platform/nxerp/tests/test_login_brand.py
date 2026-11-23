"""Whose login a site shows, and that the launcher keeps companion tiles (India Compliance next to ERPNext)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import install, launcher, registry
from nxerp.www import login


class TestLoginBrand(IntegrationTestCase):
	def entries(self, *keys):
		return [e for e in registry.APPS if e.key in keys]

	def test_helpdesk_site_is_sria_helpdesk(self):
		with patch.object(registry, "installed_entries", lambda: self.entries("helpdesk")):
			brand = login.login_brand()
		self.assertEqual((brand["variant"], brand["name"]), ("product", "Sria Helpdesk"))

	def test_erp_site_stays_nxerp(self):
		with patch.object(registry, "installed_entries", lambda: self.entries("erpnext", "helpdesk")):
			brand = login.login_brand()
		self.assertEqual((brand["variant"], brand["name"]), ("nxerp", "NXERP"))

	def test_site_without_a_product_is_the_platform(self):
		with patch.object(registry, "installed_entries", lambda: []):
			self.assertEqual(login.login_brand()["name"], "NXDESK")

	def test_unset_brand_values(self):
		self.assertTrue(install._unset("NXERP"))
		self.assertTrue(install._unset("/assets/helpdesk/nxerp_login/images/nxerp-wordmark.png", logo=True))
		self.assertFalse(install._unset("Acme Support"))

	def test_registry_declares_india_compliance_as_companion(self):
		erp = registry.get_entry("erpnext")
		self.assertIn("india_compliance", erp.desk_apps)

	def test_companion_tile_is_kept(self):
		info = frappe._dict(app_data=[{"app_name": "india_compliance", "on_apps_screen": True}])
		with patch.object(registry, "installed_entries", lambda: self.entries("erpnext")):
			launcher.extend_bootinfo(info)
		row = info.app_data[0]
		self.assertTrue(row.get("on_apps_screen"))
