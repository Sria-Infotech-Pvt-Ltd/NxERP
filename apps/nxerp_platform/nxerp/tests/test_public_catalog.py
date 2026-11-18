"""The information pages and the announced (not installed) product: public, honest, and never a way in."""

import re

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import public_catalog, registry
from nxerp.tests.utils import Client

SLUGS = ("platform", "security", "solutions", "roadmap", "company", "partners", "get-in-touch")


class TestPublicCatalog(IntegrationTestCase):
	def get(self, path):
		return Client().get(path)

	def test_every_information_page_renders_for_a_guest(self):
		for slug in SLUGS:
			r = self.get(f"/{slug}")
			self.assertEqual(r.status_code, 200, slug)
			self.assertEqual(r.text.count("<h1"), 1, slug)
			self.assertIn(public_catalog.PAGES[slug]["title"], r.text, slug)
			for word in ("Traceback", "NXERP Access", "System Manager"):
				self.assertNotIn(word, r.text, f"{slug} shows {word!r}")

	def test_the_header_menus_and_footer_are_on_every_public_page(self):
		for path in ("/", "/products", "/platform", "/products/helpdesk", "/products/aira-hrms"):
			html = self.get(path).text
			for label in ("Products", "Platform", "Solutions", "Company"):
				self.assertIn(f">{label}", html, f"{path}: {label}")
			self.assertIn("nxp-foot-cols", html, path)
			self.assertIn('id="nxp-burger"', html, path)

	def test_the_announced_product_is_marked_and_is_not_a_way_in(self):
		html = self.get("/products/aira-hrms").text
		self.assertIn("AIRA HRMS", html)
		self.assertIn("Coming soon", html)
		self.assertIn("not installed", html)
		for forbidden in (
			"/signup",
			"/get-started",
			"/login?app=",
			"/welcome/",
			"Get started in three steps",
			"Open application",
		):
			self.assertNotIn(forbidden, html.split("<main")[1], forbidden)

	def test_the_announced_product_has_no_account_flow(self):
		for path in ("/signup?app=aira-hrms", "/get-started?product=aira-hrms"):
			self.assertEqual(self.get(path).status_code, 404, path)

	def test_the_announced_product_is_listed_apart_from_the_installed_ones(self):
		for path in ("/", "/products"):
			html = self.get(path).text
			self.assertEqual(
				re.findall(r'data-product="([^"]+)"', html), [e.key for e in registry.public_entries()], path
			)
			self.assertEqual(re.findall(r'data-upcoming="([^"]+)"', html), ["aira-hrms"], path)

	def test_an_installed_product_replaces_its_announcement(self):
		self.assertEqual(public_catalog.upcoming(("aira-hrms",)), [])
		self.assertIsNone(public_catalog.upcoming_entry("aira-hrms", ("aira-hrms",)))
		self.assertIsNotNone(public_catalog.upcoming_entry("aira-hrms", ("erpnext", "helpdesk")))

	def test_announced_copy_follows_the_card_limits(self):
		for item in public_catalog.UPCOMING:
			self.assertLessEqual(len(item.tagline), registry.TAGLINE_MAX)
			self.assertLessEqual(len(item.summary), registry.SUMMARY_MAX + 40)
			self.assertLessEqual(len(item.features), registry.FEATURES_MAX)
			for feature in item.features:
				self.assertLessEqual(len(feature.split()), registry.FEATURE_WORDS_MAX)
			self.assertTrue(frappe.get_app_path("nxerp", "public", "images", item.logo.rsplit("/", 1)[1]))

	def test_page_copy_makes_no_unprovable_claims(self):
		text = " ".join(
			[b["title"] + " " + b.get("body", "") for p in public_catalog.PAGES.values() for b in p["blocks"]]
			+ [p["lead"] for p in public_catalog.PAGES.values()]
		).lower()
		for word in (
			"award",
			"certified",
			"iso 27001",
			"uptime",
			"customers worldwide",
			"trusted by",
			"best-in-class",
			"!",
		):
			self.assertNotIn(word, text, word)

	def test_every_icon_used_exists(self):
		for page in public_catalog.PAGES.values():
			for block in page["blocks"]:
				self.assertIn(block["icon"], public_catalog.ICONS)

	def test_the_contact_page_uses_the_configured_link_only(self):
		html = self.get("/get-in-touch").text
		self.assertTrue("Contact us" in html or "Contact details are not set up yet" in html)
