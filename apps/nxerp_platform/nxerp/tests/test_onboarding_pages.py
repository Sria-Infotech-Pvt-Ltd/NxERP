"""The Phase 2 pages and endpoints over HTTP against the running site: /signup, /get-started, /welcome/<key>, the
no-access "Request access" button, and what the API refuses without a session or without a CSRF token.

Needs the dev stack (NXERP_TEST_BASE, default http://localhost:8000). Signup is closed by default, so the signup tests run
against the closed state; the open state is covered in process (test_onboarding) and by the browser journey."""

import re
import secrets

import frappe
from frappe.tests import IntegrationTestCase

from nxerp.tests.utils import ERP_ACCESS, Client, delete_users, make_user, purge_test_users, unique_email

APP = "helpdesk"


def location(resp) -> str:
	return resp.headers.get("Location", "")


class TestOnboardingPages(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		purge_test_users()
		cls.pw = secrets.token_urlsafe(16)
		cls.created = []

		def mk(prefix, roles, **kw):
			doc = make_user(unique_email(prefix), roles, password=cls.pw, **kw)
			cls.created.append(doc.name)
			return doc.name

		cls.plain = mk("g-plain", ["Website Manager"])
		cls.holder = mk("g-holder", ["Agent"])
		cls.pending = mk("g-pending", ["Website Manager"])
		cls.erp = mk("g-erp", ["Sales User", ERP_ACCESS])
		frappe.get_doc({"doctype": "NXERP Access Request", "user": cls.pending, "app_key": APP}).insert(
			ignore_permissions=True
		)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for doctype in ("NXERP Access Request", "NXERP Onboarding"):
			for name in frappe.get_all(doctype, filters={"user": ["in", cls.created]}, pluck="name"):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		delete_users(cls.created)
		frappe.db.commit()
		super().tearDownClass()

	def get(self, path, user=None):
		return (Client(user, self.pw) if user else Client()).get(path)

	# --- /signup ------------------------------------------------------------------------------

	def test_signup_shows_the_unavailable_state_while_it_is_off(self):
		if frappe.utils.cint(frappe.conf.get("nxerp_enable_signup")):
			self.skipTest("this site has signup switched on")
		r = self.get(f"/signup?app={APP}")
		self.assertEqual(r.status_code, 200)
		self.assertIn("Signup is not available", r.text)
		self.assertNotIn("nx-signup-form", r.text)
		self.assertIn("nx-hero", r.text, "the same split layout")
		self.assertIn("Support tickets", r.text, "the product's tagline is in the hero")

	def test_signup_needs_a_known_product(self):
		self.assertEqual(self.get("/signup").status_code, 301)
		self.assertEqual(location(self.get("/signup")), "/products")
		for key in ("nope", "test-projects", "HELPDESK", "helpdesk%2f"):
			self.assertEqual(self.get(f"/signup?app={key}").status_code, 404, key)

	def test_a_signed_in_visitor_is_sent_on_from_signup(self):
		r = self.get(f"/signup?app={APP}", self.plain)
		self.assertEqual((r.status_code, location(r)), (301, f"/get-started?product={APP}"))

	def test_the_sign_up_endpoint_refuses_while_signup_is_off(self):
		if frappe.utils.cint(frappe.conf.get("nxerp_enable_signup")):
			self.skipTest("this site has signup switched on")
		email = unique_email("never")
		r = Client().post(
			"/api/method/nxerp.api.account.sign_up",
			json_body={"email": email, "full_name": "Nobody", "app": APP},
		)
		# 403 while signup is off; 429 once this IP has used its 10 calls an hour (Frappe's rate limiter, kept across test runs)
		self.assertIn(r.status_code, (403, 429))
		self.assertFalse(frappe.db.exists("User", email))
		r = Client().get("/api/method/nxerp.api.account.sign_up")
		self.assertIn(r.status_code, (403, 405), "POST only")

	# --- /get-started -------------------------------------------------------------------------

	def test_get_started_for_a_guest_offers_signup_and_login(self):
		r = self.get(f"/get-started?product={APP}")
		self.assertEqual(r.status_code, 200)
		self.assertIn("Get started with Sria Helpdesk", r.text)
		self.assertIn(f'href="/signup?app={APP}"', r.text)
		self.assertIn(f'href="/login?app={APP}"', r.text)
		self.assertEqual(r.text.count("<h1"), 1)

	def test_get_started_needs_a_known_product(self):
		for path in (
			"/get-started?product=nope",
			"/get-started?product=test-projects",
			"/get-started?product=HELPDESK",
		):
			self.assertEqual(self.get(path).status_code, 404, path)
		self.assertEqual(location(self.get("/get-started")), "/products")

	def test_get_started_routes_a_signed_in_visitor(self):
		r = self.get(f"/get-started?product={APP}", self.plain)
		self.assertEqual(location(r), f"/welcome/{APP}")
		r = self.get(f"/get-started?product={APP}", self.pending)
		self.assertEqual(
			location(r), f"/welcome/{APP}", "a pending request shows the pending view on /welcome"
		)
		r = self.get(f"/get-started?product={APP}", self.holder)
		self.assertEqual(location(r), "/nxerp/go?redirect-to=%2Fhelpdesk%2Fhome")

	# --- /welcome/<key> -----------------------------------------------------------------------

	def test_welcome_needs_a_session_and_a_known_product(self):
		r = self.get(f"/welcome/{APP}")
		self.assertEqual((r.status_code, location(r)), (301, f"/login?redirect-to=/welcome/{APP}"))
		for key in ("nope", "test-projects", "HELPDESK"):
			self.assertEqual(self.get(f"/welcome/{key}", self.plain).status_code, 404, key)
		self.assertEqual(self.get("/welcome/", self.plain).status_code, 404)

	def test_welcome_renders_the_wizard_for_a_user_without_the_grant(self):
		r = self.get(f"/welcome/{APP}", self.plain)
		self.assertEqual(r.status_code, 200)
		self.assertIn('data-step="basics"', r.text)
		self.assertIn('data-step="about"', r.text)
		self.assertIn('data-step="request"', r.text)
		self.assertEqual(len(re.findall(r'class="nx-seg"', r.text)), 3, "one progress segment per step")
		self.assertNotIn(self.plain, r.text, "the page does not print the email address")
		self.assertNotIn(self.holder, r.text)

	def test_the_wizard_preselects_the_saved_language_and_time_zone(self):
		frappe.db.rollback()  # end this connection's snapshot: the web server has updated the user since
		frappe.db.set_value("User", self.plain, {"language": "en", "time_zone": "Asia/Kolkata"})
		frappe.db.commit()
		html = self.get(f"/welcome/{APP}", self.plain).text
		self.assertIn(
			'<option value="en" selected>',
			html,
			"the saved language is selected, not the first one in the list",
		)
		self.assertIn('<option value="Asia/Kolkata" selected>', html)

	def test_welcome_shows_the_pending_view_when_a_request_is_open(self):
		r = self.get(f"/welcome/{APP}", self.pending)
		self.assertRegex(r.text, r'id="nx-pending"(?! hidden)')
		self.assertIn("Request sent", r.text)
		self.assertIn('id="nx-wizard" hidden', r.text)

	def test_welcome_sends_a_holder_on_to_the_app(self):
		r = self.get(f"/welcome/{APP}", self.holder)
		self.assertEqual(location(r), "/nxerp/go?redirect-to=/helpdesk/home")

	def test_welcome_is_reachable_through_the_router_after_login(self):
		r = self.get(f"/nxerp/go?redirect-to=/welcome/{APP}", self.plain)
		self.assertEqual(location(r), f"/welcome/{APP}")
		r = self.get("/nxerp/go?redirect-to=/welcome/not-a-product", self.plain)
		self.assertNotIn("welcome", location(r))

	# --- the no-access page ---------------------------------------------------------------------

	def test_no_access_offers_request_access_for_the_named_app_only(self):
		html = self.get(f"/nxerp/no-access?app={APP}", self.plain).text
		self.assertIn("data-request-access", html)
		self.assertIn(f'href="/welcome/{APP}"', html)
		self.assertLess(
			html.index("Request access"),
			html.index("Back to my applications"),
			"the primary button comes first",
		)
		for word in ("ERPNext", "NXERP Access", "System Manager", "Agent"):
			self.assertNotIn(word, html)
		for path in ("/nxerp/no-access", "/nxerp/no-access?app=nope", "/nxerp/no-access?app=erpnext%2F"):
			self.assertNotIn("data-request-access", self.get(path, self.plain).text, path)
		self.assertNotIn(
			"data-request-access", self.get(f"/nxerp/no-access?app={APP}").text, "never for a guest"
		)

	def test_the_gate_still_keeps_a_requester_out_of_the_app(self):
		r = self.get("/helpdesk/home", self.pending)
		self.assertEqual(r.status_code, 302)
		self.assertIn("/nxerp/no-access", location(r))

	# --- the API without a session or a CSRF token -------------------------------------------------

	def test_the_onboarding_api_needs_a_session(self):
		for method, call in (
			("get_state", lambda c: c.get(f"/api/method/nxerp.api.onboarding.get_state?app={APP}")),
			(
				"save_step",
				lambda c: c.post(
					"/api/method/nxerp.api.onboarding.save_step",
					json_body={"app": APP, "step": "basics", "data": {}},
				),
			),
			("submit", lambda c: c.post("/api/method/nxerp.api.onboarding.submit", json_body={"app": APP})),
			(
				"decide",
				lambda c: c.post(
					"/api/method/nxerp.api.access_request.decide",
					json_body={"name": "NXAR-00001", "decision": "Approve"},
				),
			),
		):
			self.assertIn(call(Client()).status_code, (401, 403), method)

	def test_a_state_changing_call_without_the_csrf_token_is_refused(self):
		client = Client(self.plain, self.pw)
		# a session only has a CSRF token once a page has issued one (the wizard page does, as in a browser)
		self.assertEqual(client.get(f"/welcome/{APP}").status_code, 200)
		r = client.post(
			"/api/method/nxerp.api.onboarding.save_step",
			json_body={"app": APP, "step": "basics", "data": {"language": "en", "time_zone": "Asia/Kolkata"}},
		)
		self.assertIn(r.status_code, (400, 403), "Frappe's CSRF check, unchanged")
		self.assertFalse(frappe.db.exists("NXERP Onboarding", f"{self.plain}:{APP}"))
