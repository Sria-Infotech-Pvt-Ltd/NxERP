"""The public site over HTTP against the running site: Home, Products and a page per installed product.

Real requests, no mocks. Needs the dev stack (NXERP_TEST_BASE, default http://localhost:8000), like
test_unified_experience.py. Nothing here creates an account through the public pages: they only read.
"""

import re
import secrets
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import enforcement, public_site, registry
from nxerp.tests.utils import (
	ERP_ACCESS,
	PLAIN_DESK_ROLE,
	Client,
	delete_users,
	make_user,
	purge_test_users,
	unique_email,
)

PUBLIC_PATHS = ("/", "/nxerp/home", "/products", "/products/helpdesk", "/products/erpnext")

# things that must never appear on a public page
FORBIDDEN = (
	"Traceback",
	"frappe.exceptions",
	"NXERP Access",  # role names
	"System Manager",
	"Agent Manager",
	"HD Customer",
	"Royal HRMS",  # not installed
	"Project Management",
	"Budget Management",
)


def hrefs(html: str) -> list:
	return re.findall(r'href="([^"]*)"', html)


class TestPublicSite(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		purge_test_users()
		cls.password = secrets.token_urlsafe(16)
		cls.created = []

		def mk(prefix, roles, **kw):
			doc = make_user(unique_email(prefix), roles, password=cls.password, **kw)
			cls.created.append(doc.name)
			return doc.name

		cls.agent = mk("p-agent", ["Agent"], first_name="Pubagent")
		cls.both = mk("p-both", ["Agent Manager", ERP_ACCESS], first_name="Pubboth")
		cls.none = mk("p-none", [PLAIN_DESK_ROLE], first_name="Pubnone")
		cls.customer = mk("p-cust", ["HD Customer"], first_name="Pubcust", user_type="Website User")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		delete_users(cls.created)
		frappe.db.commit()
		super().tearDownClass()

	def page(self, path, user=None):
		client = Client(user, self.password) if user else Client()
		return client.get(path)

	# --- guests ---------------------------------------------------------------------------------

	def test_guests_get_the_public_pages(self):
		for path in PUBLIC_PATHS:
			r = self.page(path)
			self.assertEqual(r.status_code, 200, path)
			self.assertIn("nxp-body", r.text, path)

	def test_root_is_the_public_home_for_a_guest_not_the_login_page(self):
		html = self.page("/").text
		self.assertIn("nxp-hero", html)
		self.assertNotIn("nx-shell", html)
		self.assertEqual(html, self.page("/nxerp/home").text, "/ and /nxerp/home are the same page")

	def test_home_lists_exactly_the_installed_products(self):
		html = self.page("/").text
		keys = re.findall(r'data-product="([^"]+)"', html)
		self.assertEqual(keys, [e.key for e in registry.public_entries()])
		self.assertEqual(sorted(keys), ["erpnext", "helpdesk"])

	def test_products_lists_exactly_the_installed_products(self):
		html = self.page("/products").text
		self.assertEqual(
			re.findall(r'data-product="([^"]+)"', html), [e.key for e in registry.public_entries()]
		)
		self.assertEqual(html.count('<h1 class="nxp-title">'), 1)

	def test_display_names_not_technical_names_are_shown(self):
		html = self.page("/products").text
		self.assertIn("NXERP", html)
		self.assertIn("Sria Helpdesk", html)

	def test_product_pages_render_their_registry_copy(self):
		for entry in registry.public_entries():
			html = self.page(f"/products/{entry.key}").text
			self.assertIn(entry.public_title, html)
			self.assertIn(entry.tagline, html)
			for feature in entry.features:
				self.assertIn(feature, html)
			self.assertEqual(html.count("<h1"), 1)
			self.assertEqual(len(re.findall(r'<li style="--i: \d">\s*<div class="nxp-card">', html)), 3)

	def test_unknown_or_uninstalled_keys_are_the_same_404_as_any_page(self):
		unknown = self.page("/this-page-does-not-exist-anywhere")
		self.assertEqual(unknown.status_code, 404)
		for path in (
			"/products/unknown",
			"/products/test-projects",
			"/products/HELPDESK",
			"/products/helpdesk%2f..%2f",
			"/products/%00",
			"/product",
		):
			r = self.page(path)
			self.assertEqual(r.status_code, 404, path)
			self.assertNotIn("Traceback", r.text, path)
			self.assertNotIn("nxp-split", r.text, path)

	def test_public_pages_leak_nothing(self):
		for path in PUBLIC_PATHS:
			text = self.page(path).text
			for word in FORBIDDEN:
				self.assertNotIn(word.lower(), text.lower(), f"{path} shows {word!r}")

	def test_a_signed_in_page_shows_only_the_viewers_own_name(self):
		html = self.page("/nxerp/home", self.agent).text
		self.assertIn("Pubagent", html)
		for other in ("Pubboth", "Pubnone", "Pubcust", self.both, self.none, self.customer):
			self.assertNotIn(other, html)
		self.assertNotIn(self.agent, html, "an email address is never printed")

	def test_pages_are_not_cached_across_users(self):
		guest = self.page("/products/helpdesk").text
		self.page("/products/helpdesk", self.agent)
		self.assertEqual(guest, self.page("/products/helpdesk").text)
		self.assertIn("Get started", guest)

	def test_a_guest_sees_sign_in_and_get_started_in_the_header(self):
		html = self.page("/").text
		self.assertIn(">Sign in<", html)
		self.assertIn(">Get started<", html)
		self.assertNotIn("Open your apps", html)
		self.assertIn("/get-started", hrefs(html))
		self.assertIn("/login", hrefs(html))

	# --- signed in ------------------------------------------------------------------------------

	def test_a_holder_sees_open_not_get_started(self):
		html = self.page("/products/helpdesk", self.agent).text
		self.assertIn("Open application", html)
		self.assertIn('href="/helpdesk/home"', html)
		self.assertNotIn(
			">Get started<", html.split("<main")[1], "the page body offers no sign-up to a holder"
		)
		self.assertNotIn(">Log in<", html)

	def test_a_non_holder_still_sees_get_started(self):
		html = self.page("/products/erpnext", self.agent).text
		self.assertNotIn("Open application", html)
		self.assertIn("/get-started?product=erpnext", html)

	def test_a_signed_in_header_has_the_pill_and_open_your_apps(self):
		html = self.page("/nxerp/home", self.both).text
		self.assertIn("Open your apps", html)
		self.assertIn('href="/nxerp/go"', html)
		self.assertIn("nxp-avatar", html)
		self.assertNotIn(">Sign in<", html)

	def test_tiles_say_open_application_only_for_held_products(self):
		html = self.page("/products", self.both).text
		self.assertEqual(html.count("Open application"), 2)
		html = self.page("/products", self.none).text
		self.assertEqual(html.count("Open application"), 0)
		self.assertEqual(html.count("Learn more"), 3, "two installed products and the announced one")

	def test_a_customer_with_portal_access_opens_the_portal_not_the_app(self):
		html = self.page("/products/helpdesk", self.customer).text
		self.assertIn('href="/helpdesk/my-tickets"', html)
		html = self.page("/products/erpnext", self.customer).text
		self.assertNotIn("Open application", html)

	def test_signed_in_users_are_not_taken_from_slash_to_the_public_home(self):
		"""Only a guest's "/" is re-pointed; everyone else keeps Frappe's answer (the router decides)."""
		for user in (self.agent, self.both, self.none):
			r = self.page("/", user)
			self.assertNotIn("nxp-hero", r.text, user)
			self.assertLess(r.status_code, 500, user)

	# --- the gate -------------------------------------------------------------------------------

	def test_the_gate_lets_guests_and_everyone_through_the_public_paths(self):
		"""No gate change is needed: these paths are outside every app prefix (enforcement.evaluate_request)."""
		for path in (
			"/",
			"/products",
			"/products/helpdesk",
			"/products/erpnext",
			"/nxerp/home",
			"/get-started",
		):
			for user in ("Guest", self.none, self.customer, self.agent):
				decision = enforcement.evaluate_request(user, path, "GET", {})
				self.assertTrue(decision.allow, f"{user} {path}: {decision}")

	def test_the_home_page_hook_answers_only_guests(self):
		keep = frappe.conf.get("nxerp_keep_login_home")
		try:
			frappe.local.conf["nxerp_keep_login_home"] = 0
			self.assertEqual(public_site.website_user_home_page("Guest"), "nxerp/home")
			self.assertIsNone(public_site.website_user_home_page("Administrator"))
			self.assertIsNone(public_site.website_user_home_page(self.agent))
			frappe.local.conf["nxerp_keep_login_home"] = 1
			self.assertIsNone(
				public_site.website_user_home_page("Guest"), "the kill-switch restores the old behaviour"
			)
		finally:
			frappe.local.conf["nxerp_keep_login_home"] = keep

	def test_test_only_stand_in_apps_are_never_public(self):
		keep = frappe.conf.get("nxerp_test_apps")
		try:
			frappe.local.conf["nxerp_test_apps"] = [
				{
					"key": "test-projects",
					"title": "Test Projects",
					"route": "/nxerp/test-app",
					"access_role": "NXERP Access: Test Projects",
				}
			]
			self.assertIn("test-projects", [e.key for e in registry.installed_entries()])
			self.assertNotIn("test-projects", [e.key for e in registry.public_entries()])
			self.assertIsNone(public_site.product("test-projects"))
		finally:
			frappe.local.conf["nxerp_test_apps"] = keep

	# --- the rest of the platform still behaves ----------------------------------------------------

	def test_login_still_works_and_still_ends_at_the_router(self):
		login = self.page("/login")
		self.assertEqual(login.status_code, 200)
		self.assertIn("nx-shell", login.text)
		for user in (self.agent, self.both, self.none):
			r = Client().post("/api/method/login", data={"usr": user, "pwd": self.password})
			self.assertEqual(r.status_code, 200)
			self.assertEqual(r.json().get("home_page"), "/nxerp/go", user)

	def test_the_launcher_and_no_access_pages_still_do_not_use_the_site_stylesheet(self):
		"""Phase 1 adds rules in nxerp-site.css; the launcher and no-access page must stay exactly as they were."""
		self.assertNotIn("nxerp-site.css", self.page("/nxerp/apps", self.both).text)
		self.assertNotIn("nxerp-site.css", self.page("/nxerp/no-access", self.none).text)
		self.assertNotIn("nxerp-site.css", self.page("/login").text)


if __name__ == "__main__":
	unittest.main()


class TestIdentitySiteCatalogue(IntegrationTestCase):
	"""The identity site has no app installed: its public pages list the enabled peers' apps and link to their own sites."""

	PEERS = (
		frappe._dict(app_key="helpdesk", origin="https://hd.example.test"),
		frappe._dict(app_key="erpnext", origin="https://erp.example.test"),
	)

	def identity(self):
		from unittest.mock import patch

		conf = patch.dict(frappe.conf, {"nxerp_site_role": "identity"})
		peers = patch.object(registry, "_peers", return_value=list(self.PEERS))
		conf.start()
		peers.start()
		self.addCleanup(conf.stop)
		self.addCleanup(peers.stop)

	def test_peers_are_listed_with_links_to_their_own_sites_and_aira_stays_coming_soon(self):
		self.identity()
		by_key = {p["key"]: p for p in public_site.products()}
		self.assertIn("helpdesk", by_key)
		self.assertIn("erpnext", by_key)
		self.assertEqual(by_key["helpdesk"]["page_href"], "https://hd.example.test/products/helpdesk")
		self.assertTrue(by_key["erpnext"]["signup_href"].startswith("https://erp.example.test/signup?app="))
		self.assertTrue(by_key["erpnext"]["login_href"].startswith("https://erp.example.test/login"))
		aira = [p for p in by_key.values() if p.get("upcoming")]
		self.assertTrue(
			aira and all(p["open_href"] is None for p in aira), "an announced product has no link into an app"
		)

	def test_the_strict_lookups_used_by_sign_up_and_requests_are_unchanged(self):
		self.identity()
		self.assertEqual(
			{e.key for e in registry.public_entries()},
			{e.key for e in registry.installed_entries() if not e.test_only},
		)

	def test_without_a_site_role_the_catalogue_is_exactly_the_installed_products(self):
		self.assertEqual(
			[e.key for e in registry.catalogue_entries()], [e.key for e in registry.public_entries()]
		)
		self.assertTrue(
			all(p["page_href"].startswith("/") for p in public_site.products() if not p.get("upcoming"))
		)
