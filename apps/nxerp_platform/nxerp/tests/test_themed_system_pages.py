"""The standard Frappe pages of the sign-in flow (set password, message, not found, error) are served in the NXDESK look.

They override `frappe/www/<page>` from nxerp's own www folder; this checks the context each one builds (no HTTP, so it runs anywhere)."""

import importlib
import os

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import public_site


def context_of(module_name: str, **form):
	frappe.local.form_dict = frappe._dict(form)
	return importlib.import_module(f"nxerp.www.{module_name}").get_context(frappe._dict())


class TestThemedSystemPages(IntegrationTestCase):
	def test_every_page_carries_the_platform_look(self):
		for module, form in (
			("update_password", {}),
			("message", {"title": "Hello", "message": "World"}),
			("404", {}),
			("error", {}),
		):
			with self.subTest(module):
				context = context_of(module, **form)
				self.assertEqual(context.nx.name, "NXDESK")
				self.assertEqual(context.product.tagline, public_site.platform_hero().tagline)
				self.assertTrue(context.product.features)

	def test_message_keeps_frappes_title_and_text_and_offers_home(self):
		context = context_of("message", title="Link expired", message="This link has expired.")
		self.assertEqual(
			(context.state_heading, context.state_text), ("Link expired", "This link has expired.")
		)
		self.assertEqual(context.state_href, "/")

	def test_not_found_answers_404(self):
		self.assertEqual(context_of("404").http_status_code, 404)

	def test_the_set_password_page_asks_for_the_old_password_only_without_a_key(self):
		html = open(
			os.path.join(frappe.get_app_path("nxerp"), "www", "update-password.html"), encoding="utf-8"
		).read()
		self.assertIn("frappe.core.doctype.user.user.update_password", html)
		self.assertIn("nx-old-group", html)
		self.assertIn('if (!key) document.getElementById("nx-old-group").hidden = false;', html)
