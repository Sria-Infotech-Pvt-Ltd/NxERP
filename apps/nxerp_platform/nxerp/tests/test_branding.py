import frappe
from frappe.tests import IntegrationTestCase

from nxerp import branding


class TestBranding(IntegrationTestCase):
	def test_platform_name_is_nxdesk_and_login_keeps_the_nxerp_look(self):
		self.assertEqual(branding.PLATFORM_NAME, "NXDESK")
		self.assertEqual(branding.LOGIN_NAME, "NXERP")

	def test_wordmark_is_typographic_until_both_logo_files_are_set(self):
		self.assertFalse(branding.wordmark()["image"])
		original = (branding.LOGO_LIGHT_THEME, branding.LOGO_DARK_THEME)
		try:
			branding.LOGO_LIGHT_THEME = "/assets/nxerp/x-light.svg"
			self.assertFalse(branding.wordmark()["image"], "one path alone is not enough")
			branding.LOGO_DARK_THEME = "/assets/nxerp/x-dark.svg"
			self.assertTrue(branding.wordmark()["image"])
		finally:
			branding.LOGO_LIGHT_THEME, branding.LOGO_DARK_THEME = original

	def test_support_url_follows_site_config(self):
		keep = {k: frappe.conf.get(k) for k in ("nxerp_support_url", "nxerp_support_email")}
		try:
			frappe.local.conf["nxerp_support_url"] = ""
			frappe.local.conf["nxerp_support_email"] = ""
			self.assertIsNone(branding.support_url())
			frappe.local.conf["nxerp_support_email"] = "help@example.test"
			url = branding.support_url("NXERP")
			self.assertTrue(url.startswith("https://mail.google.com/"))
			self.assertIn("NXERP%20IT%20Support", url)
			frappe.local.conf["nxerp_support_url"] = "javascript:alert(1)"
			self.assertTrue(
				branding.support_url().startswith("https://mail.google.com/"), "unsafe schemes are ignored"
			)
			frappe.local.conf["nxerp_support_url"] = "mailto:help@example.test"
			self.assertEqual(branding.support_url(), "mailto:help@example.test")
		finally:
			for key, value in keep.items():
				frappe.local.conf[key] = value
