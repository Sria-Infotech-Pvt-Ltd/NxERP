"""The unified experience over HTTP, against the running site: the NXERP /login, the router at /nxerp/go,
the launcher, the tile overrides and the kill-switch. Real sessions, real redirects, no mocks.

Needs the dev stack (NXERP_TEST_BASE, default http://localhost:8000) and NXERP_ADMIN_PASSWORD for the
Administrator persona; the Administrator tests are skipped without it.
"""

import json
import os
import re
import secrets
import time
import unittest
from urllib.parse import parse_qs, urlsplit

import frappe
from frappe.installer import update_site_config
from frappe.tests import IntegrationTestCase

from nxerp.tests.test_routing import HOSTILE
from nxerp.tests.utils import (
	ERP_ACCESS,
	HD_ACCESS,
	PLAIN_DESK_ROLE,
	Client,
	base_url,
	delete_users,
	make_user,
	purge_test_users,
	unique_email,
)

TEST_APP_ROLE = "NXERP Access: Test Projects"
TEST_APP = {
	"key": "test-projects",
	"title": "Test Projects",
	"route": "/nxerp/test-app",
	"access_role": TEST_APP_ROLE,
	"order": 30,
}
ADMIN_PASSWORD = os.environ.get("NXERP_ADMIN_PASSWORD")


def location(resp) -> str:
	"""The redirect target as path?query (a Location may be absolute to this host)."""
	parts = urlsplit(resp.headers.get("Location", ""))
	return parts.path + (f"?{parts.query}" if parts.query else "")


# Frappe caches site config in every web worker for up to 60 seconds (frappe/config.py, ttl=60), so a config
# change made by a test is seen by the server within that window. Poll for it instead of sleeping blindly.
CONFIG_TTL_WAIT = 80


def wait_until(check, timeout=CONFIG_TTL_WAIT, every=3):
	deadline = time.monotonic() + timeout
	while True:
		result = check()
		if result:
			return result
		if time.monotonic() > deadline:
			return result
		time.sleep(every)


def no_traceback(text: str) -> bool:
	"""Frappe adds the traceback to JSON errors on a site with developer_mode on (it never does that on a
	production site for a 4xx); the dev site has it on, so only enforce this where the site would."""
	return bool(frappe.conf.get("developer_mode")) or "Traceback" not in text


def tiles(html: str) -> list:
	return re.findall(r'data-app="([^"]+)"', html)


def boot_of(html: str) -> dict:
	"""frappe.boot = {...}; as rendered into /desk."""
	start = html.index("frappe.boot = ") + len("frappe.boot = ")
	value, _ = json.JSONDecoder().raw_decode(html[start:])
	return value


class TestUnifiedExperience(IntegrationTestCase):
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

		cls.agent = mk("u-agent", ["Agent"])
		cls.erp = mk("u-erp", ["Sales User", ERP_ACCESS])
		cls.both = mk("u-both", ["Agent Manager", ERP_ACCESS])
		cls.noapps = mk("u-none", [PLAIN_DESK_ROLE])
		cls.customer = mk("u-cust", ["HD Customer"], user_type="Website User")
		cls.disabled = mk("u-off", ["Agent"], enabled=0)
		frappe.db.commit()
		cls.setup_complete = bool(frappe.is_setup_complete())
		# a previous aborted run may have left a switch on; the web workers see the file within the cache window
		update_site_config("nxerp_stock_login", 0)
		update_site_config("nxerp_test_apps", [])
		wait_until(lambda: "nx-shell" in Client().get("/login").text)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		update_site_config("nxerp_stock_login", 0)
		update_site_config("nxerp_test_apps", [])
		if frappe.db.exists("Role", TEST_APP_ROLE):
			frappe.delete_doc("Role", TEST_APP_ROLE, force=True, ignore_permissions=True)
		delete_users(cls.created)
		frappe.db.commit()
		super().tearDownClass()

	# --- /login is the platform's ---------------------------------------------------------------

	def test_login_is_served_by_nxerp_and_owns_no_helpdesk_assets(self):
		html = Client().get("/login").text
		self.assertIn("nx-shell", html)
		self.assertIn("/assets/nxerp/nxerp_login/css/nxerp-login.css", html)
		self.assertNotIn("/assets/helpdesk/", html, "the login must not depend on any app's assets")

	def test_login_has_labelled_fields_and_a_support_path(self):
		html = Client().get("/login").text
		self.assertRegex(html, r'id="login_email"')
		self.assertRegex(html, r'for="login_email"')
		self.assertRegex(html, r'id="login_password"')
		self.assertIn("Forgot", html)

	def test_the_old_helpdesk_login_path_no_longer_exists(self):
		r = Client().get("/login/helpdesk")
		self.assertIn(r.status_code, (301, 302))
		self.assertEqual(location(r), "/login")

	# --- authentication is still Frappe's, and points at the router --------------------------------

	def test_login_response_points_at_the_router_for_every_persona(self):
		for email in (self.agent, self.erp, self.both, self.noapps):
			c = Client()
			r = c.s.post(base_url() + "/api/method/login", data={"usr": email, "pwd": self.password})
			self.assertEqual(r.status_code, 200, email)
			self.assertEqual(r.json()["home_page"], "/nxerp/go", email)

	def test_website_users_are_pointed_at_the_router_by_the_login_page(self):
		# Frappe answers a website user with its own default path; the login page re-points that at the router
		# (the browser behaviour itself is covered end to end in the Playwright suite).
		html = Client().get("/login").text
		self.assertIn("login_handlers", html)
		self.assertIn('data.home_page = "/nxerp/go"', html)

	def test_wrong_password_and_unknown_user_look_the_same(self):
		import requests

		def attempt(usr, pwd):
			return requests.post(base_url() + "/api/method/login", data={"usr": usr, "pwd": pwd}, timeout=60)

		wrong = attempt(self.agent, "definitely-wrong")
		unknown = attempt(unique_email("nobody"), "definitely-wrong")
		self.assertEqual(wrong.status_code, 401)
		self.assertEqual(unknown.status_code, 401)
		self.assertEqual(wrong.json().get("message"), unknown.json().get("message"))
		self.assertTrue(no_traceback(wrong.text))

	def test_a_disabled_user_cannot_sign_in(self):
		import requests

		r = requests.post(
			base_url() + "/api/method/login", data={"usr": self.disabled, "pwd": self.password}, timeout=60
		)
		self.assertEqual(r.status_code, 401)
		self.assertTrue(no_traceback(r.text))

	def test_a_signed_in_visitor_to_login_goes_to_the_router(self):
		r = Client(self.agent, self.password).get("/login")
		self.assertIn(r.status_code, (301, 302))
		self.assertEqual(urlsplit(location(r)).path, "/nxerp/go")

	# --- the router, one persona at a time -----------------------------------------------------

	def go(self, email, redirect_to=None):
		path = "/nxerp/go" + (f"?redirect-to={redirect_to}" if redirect_to is not None else "")
		return Client(email, self.password).get(path)

	def test_router_destinations_per_persona(self):
		expected = {
			self.agent: "/helpdesk/home",  # Case 2: one app, straight in
			self.erp: "/desk",
			self.both: "/nxerp/apps",  # more than one app: the launcher
			self.noapps: "/nxerp/no-access",
			self.customer: "/helpdesk/my-tickets",
		}
		for email, path in expected.items():
			r = self.go(email)
			self.assertIn(r.status_code, (301, 302), email)
			self.assertEqual(location(r), path, email)

	def test_the_router_sends_a_guest_to_login(self):
		r = Client().get("/nxerp/go")
		self.assertIn(r.status_code, (301, 302))
		self.assertEqual(urlsplit(location(r)).path, "/login")

	def test_an_authorised_redirect_is_honoured_and_an_unauthorised_one_is_not(self):
		self.assertEqual(location(self.go(self.agent, "/helpdesk/tickets")), "/helpdesk/tickets")
		self.assertEqual(location(self.go(self.agent, "/desk/customer")), "/helpdesk/home")
		self.assertEqual(location(self.go(self.both, "/desk/customer")), "/desk/customer")

	def test_tampered_redirect_targets_never_leave_the_site(self):
		for raw in HOSTILE:
			if not isinstance(raw, str):
				continue
			for email in (self.agent, self.both, self.noapps):
				r = self.go(email, raw.replace("\r", "").replace("\n", "").replace("\x00", ""))
				if r.status_code in (400, 404):  # the transport itself refused it
					continue
				self.assertIn(r.status_code, (301, 302), (email, raw))
				target = location(r)
				self.assertTrue(target.startswith("/") and not target.startswith("//"), (email, raw, target))
				self.assertNotIn("evil.example", r.headers.get("Location", ""), (email, raw))
				self.assertNotIn("Traceback", r.text, (email, raw))

	def test_a_tampered_target_through_the_login_page_is_dropped_or_neutralised(self):
		c = Client()
		for raw in ("//evil.example", "https://evil.example", "/%2f%2fevil.example", "javascript:alert(1)"):
			r = c.get("/login", params={"redirect-to": raw})
			self.assertIn(r.status_code, (200, 301, 302), raw)
			self.assertNotIn("evil.example", r.headers.get("Location", ""), raw)
			self.assertNotIn('"evil.example', r.text, raw)

	def test_a_safe_target_travels_through_the_router_so_it_is_checked_after_sign_in(self):
		r = Client().get("/login", params={"redirect-to": "/helpdesk/home"})
		self.assertIn(r.status_code, (301, 302))
		self.assertEqual(urlsplit(location(r)).path, "/login")
		self.assertEqual(parse_qs(urlsplit(location(r)).query)["redirect-to"][0].split("?")[0], "/nxerp/go")

	@unittest.skipUnless(ADMIN_PASSWORD, "needs NXERP_ADMIN_PASSWORD")
	def test_administrator_goes_to_the_setup_wizard_until_setup_is_done_then_the_launcher(self):
		r = Client("Administrator", ADMIN_PASSWORD).get("/nxerp/go")
		self.assertIn(r.status_code, (301, 302))
		self.assertEqual(location(r), "/nxerp/apps" if self.setup_complete else "/desk")

	# --- the launcher ------------------------------------------------------------------------

	def test_launcher_lists_only_authorised_apps_with_their_own_identities(self):
		r = Client(self.both, self.password).get("/nxerp/apps")
		self.assertEqual(r.status_code, 200)
		self.assertEqual(tiles(r.text), ["erpnext", "helpdesk"])
		for hidden in ("frappe", "payments", "telephony", "Framework", "Frappe"):
			self.assertNotIn(f'data-app="{hidden}"', r.text)
		self.assertNotRegex(
			r.text, r"NXERP\s*</(h\d|span|p|div)>\s*<[^>]*>\s*Helpdesk"
		)  # no "NXERP = Helpdesk" tile

	def test_launcher_redirects_users_who_do_not_need_it(self):
		for email, path in (
			(self.agent, "/helpdesk/home"),
			(self.erp, "/desk"),
			(self.noapps, "/nxerp/no-access"),
		):
			r = Client(email, self.password).get("/nxerp/apps")
			self.assertIn(r.status_code, (301, 302), email)
			self.assertEqual(location(r), path, email)

	def test_launcher_requires_sign_in(self):
		r = Client().get("/nxerp/apps")
		self.assertIn(r.status_code, (301, 302))
		self.assertEqual(urlsplit(location(r)).path, "/login")

	def test_no_access_page_is_friendly_and_does_not_name_apps(self):
		r = Client(self.noapps, self.password).get("/nxerp/no-access")
		self.assertEqual(r.status_code, 200)
		self.assertIn("Back to my applications", r.text)
		for leak in ("Traceback", "ERPNext", "Helpdesk", "NXERP Access"):
			self.assertNotIn(leak, r.text.split("</header>")[-1] if "</header>" in r.text else r.text)

	# --- the tile overrides ------------------------------------------------------------------

	def test_get_apps_returns_only_the_callers_apps(self):
		expected = {
			self.agent: ["helpdesk"],
			self.erp: ["erpnext"],
			self.both: ["erpnext", "helpdesk"],
			self.noapps: [],
		}
		for email, names in expected.items():
			r = Client(email, self.password).get("/api/method/frappe.apps.get_apps")
			self.assertEqual(r.status_code, 200, email)
			rows = r.json()["message"]
			self.assertEqual([row["name"] for row in rows], names, email)
			for row in rows:
				self.assertEqual(row["title"], {"erpnext": "ERPNext", "helpdesk": "Helpdesk"}[row["name"]])

	def test_desk_boot_hides_framework_and_unheld_apps_and_adds_the_launcher_for_multi_app_users(self):
		boot = boot_of(Client(self.both, self.password).get("/desk").text)
		visible = [row["app_name"] for row in boot["app_data"] if row.get("on_apps_screen")]
		self.assertEqual(sorted(visible), ["erpnext", "helpdesk"])
		self.assertEqual(boot["nxerp"]["launcher"], "/nxerp/apps")
		row = next(
			i
			for i in boot["navbar_settings"]["settings_dropdown"]
			if i.get("item_label") == "All applications"
		)
		self.assertEqual(row["route"], "/nxerp/apps")
		self.assertIn("boot.nxerp.launcher", row["condition"])  # shown only when the server set a launcher

	def test_desk_boot_has_no_launcher_row_for_a_single_app_user(self):
		boot = boot_of(Client(self.erp, self.password).get("/desk").text)
		self.assertIsNone(boot["nxerp"]["launcher"])
		# the row exists for everyone but its condition is false: boot.nxerp.launcher is null for this user
		self.assertEqual(
			[row["app_name"] for row in boot["app_data"] if row.get("on_apps_screen")], ["erpnext"]
		)

	# --- the kill-switch ---------------------------------------------------------------------

	def test_kill_switch_serves_the_stock_frappe_login_and_back(self):
		def stock():
			html = Client().get("/login").text
			return "nx-shell" not in html and "login_email" in html and html

		def branded():
			return "nx-shell" in Client().get("/login").text

		try:
			update_site_config("nxerp_stock_login", 1)
			html = wait_until(stock)
			self.assertTrue(html, "the stock Frappe login was not served within the config cache window")
			self.assertNotIn("nxerp-login.css", html)  # none of the branded page's assets
			# authentication itself is untouched: the same credentials still sign in and still reach the router
			self.assertIn(Client(self.agent, self.password).get("/nxerp/go").status_code, (301, 302))
		finally:
			update_site_config("nxerp_stock_login", 0)
			# leave the site as found, even when an assertion above failed, so later tests are not misled
			restored = wait_until(branded)
		self.assertTrue(restored, "the NXERP login did not come back after the switch was cleared")

	# --- a third app (TEST ONLY: never shipped) ------------------------------------------------

	def test_a_third_registered_app_shows_up_for_its_holders_only(self):
		if not frappe.conf.get("allow_tests"):
			self.skipTest("allow_tests is off")
		if not frappe.db.exists("Role", TEST_APP_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": TEST_APP_ROLE, "desk_access": 1}).insert(
				ignore_permissions=True
			)
			frappe.db.commit()
		manager = make_user(
			unique_email("u-mgr"), ["Agent Manager", TEST_APP_ROLE], password=self.password
		).name
		self.created.append(manager)
		frappe.db.commit()
		c = Client(manager, self.password)
		try:
			update_site_config("nxerp_test_apps", [TEST_APP])
			page = wait_until(lambda: (lambda r: r if r.status_code == 200 else None)(c.get("/nxerp/apps")))
			self.assertTrue(page, "the test-only app did not appear within the config cache window")
			self.assertEqual(tiles(page.text), ["helpdesk", "test-projects"])
			self.assertNotIn('data-app="erpnext"', page.text)  # a Helpdesk manager is not an ERPNext user
			self.assertEqual(c.get("/nxerp/test-app").status_code, 200)
			# everybody else is turned away from it
			self.assertIn(Client(self.agent, self.password).get("/nxerp/test-app").status_code, (301, 302))
			self.assertIn(Client().get("/nxerp/test-app").status_code, (301, 302))
		finally:
			update_site_config("nxerp_test_apps", [])
			# gone again once the entry is removed: the manager is back to one app, so the launcher is not needed
			removed = wait_until(lambda: c.get("/nxerp/apps").status_code in (301, 302))
		self.assertTrue(removed, "the test-only app was still listed after its entry was removed")
		self.assertIn(c.get("/nxerp/test-app").status_code, (301, 302, 404))
