"""The post-login router and redirect safety, in process: every decision table plus a wide set of open-redirect
payloads. HTTP behaviour (the real /login, /nxerp/go, launcher) is in test_unified_experience.py."""

from unittest.mock import patch
from urllib.parse import urlsplit

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import routing
from nxerp.tests.utils import (
	ERP_ACCESS,
	PLAIN_DESK_ROLE,
	delete_users,
	make_user,
	purge_test_users,
	unique_email,
)

# everything an attacker, or a broken link, might put in `redirect-to`
HOSTILE = [
	"//evil.example",
	"///evil.example",
	"////evil.example/x",
	"/\\evil.example",
	"\\\\evil.example",
	"\\/evil.example",
	"https://evil.example",
	"http://evil.example/helpdesk/home",
	"HTTPS://EVIL.EXAMPLE",
	"javascript:alert(1)",
	"JaVaScRiPt:alert(1)",
	"data:text/html,<script>alert(1)</script>",
	"vbscript:x",
	"/%2f%2fevil.example",
	"%2f%2fevil.example",
	"/%252f%252fevil.example",
	"/%5cevil.example",
	"%5c%5cevil.example",
	"/%09/evil.example",
	"/\t/evil.example",
	"/\n/evil.example",
	"  //evil.example",
	"/helpdesk\r\nSet-Cookie: x=1",
	"/helpdesk%0d%0aLocation:%20https://evil.example",
	"/helpdesk%00.example",
	"/helpdesk/\x7f",
	"evil.example",
	"@evil.example",
	"x" * 600,
	"/" + "%25" * 40 + "2f",
	"",
	None,
	[],
	{"a": "b"},
	123,
]

GOOD = {
	"/helpdesk/home": "/helpdesk/home",
	"/helpdesk/tickets/12?view=open": "/helpdesk/tickets/12?view=open",
	"/desk/customer": "/desk/customer",
	"/helpdesk/../desk": "/desk",  # normalised before it is judged
	"/nxerp/apps": "/nxerp/apps",
	" /helpdesk/home ": "/helpdesk/home",
}


class TestRouting(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		purge_test_users()
		cls.created = []

		def mk(prefix, roles, **kw):
			doc = make_user(unique_email(prefix), roles, **kw)
			cls.created.append(doc.name)
			return doc.name

		cls.agent = mk("r-agent", ["Agent"])
		cls.erp = mk("r-erp", ["Sales User", ERP_ACCESS])
		cls.both = mk("r-both", ["Agent Manager", ERP_ACCESS])
		cls.sysmgr = mk("r-sys", ["System Manager"])
		cls.noapps = mk("r-none", [PLAIN_DESK_ROLE])
		cls.customer = mk("r-cust", ["HD Customer"], user_type="Website User")
		cls.disabled = mk("r-off", ["Agent"], enabled=0)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		delete_users(cls.created)
		frappe.db.rollback()
		super().tearDownClass()

	# --- redirect safety -----------------------------------------------------------------

	def test_hostile_input_never_survives_as_a_url_with_a_host(self):
		for raw in HOSTILE:
			result = routing.safe_target(raw)
			if result is None:
				continue
			parts = urlsplit(result)
			self.assertEqual((parts.scheme, parts.netloc), ("", ""), repr(raw))
			self.assertTrue(result.startswith("/") and not result.startswith("//"), repr(raw))
			self.assertNotIn("\\", result, repr(raw))
			self.assertFalse(any(ord(c) < 0x20 for c in result), repr(raw))

	def test_the_obvious_attacks_are_refused_outright(self):
		for raw in (
			"//evil.example",
			"https://evil.example",
			"javascript:alert(1)",
			"/\\evil.example",
			"/%2f%2fevil.example",
			"/%252f%252fevil.example",
		):
			self.assertIsNone(routing.safe_target(raw), raw)

	def test_good_targets_are_kept_and_normalised(self):
		for raw, expected in GOOD.items():
			self.assertEqual(routing.safe_target(raw), expected, raw)

	def test_a_target_is_never_honoured_for_an_app_the_user_lacks(self):
		for raw in ("/desk", "/desk/customer", "/app/home", "/helpdesk/../desk/x"):
			self.assertIsNone(routing.authorised_target(self.agent, routing.safe_target(raw)), raw)
		for raw in ("/helpdesk/home", "/helpdesk/tickets/1", "/nxerp/apps"):
			self.assertEqual(routing.authorised_target(self.agent, routing.safe_target(raw)), raw)

	def test_unknown_internal_destinations_are_not_honoured(self):
		for raw in (
			"/me",
			"/update-password",
			"/some/page",
			"/api/method/frappe.client.get_list",
			"/helpdesk-evil/x",
			"/files/x",
		):
			self.assertIsNone(routing.authorised_target(self.both, routing.safe_target(raw)), raw)

	def test_portal_users_may_be_sent_to_the_customer_portal_only(self):
		self.assertEqual(
			routing.authorised_target(self.customer, "/helpdesk/my-tickets"), "/helpdesk/my-tickets"
		)
		self.assertIsNone(routing.authorised_target(self.customer, "/desk"))

	def test_guests_are_never_sent_anywhere_private(self):
		self.assertIsNone(routing.authorised_target("Guest", "/helpdesk/home"))
		self.assertIsNone(routing.authorised_target("Guest", "/nxerp/apps"))

	def test_login_page_carries_only_a_validated_target_through_the_router(self):
		self.assertEqual(
			routing.login_redirect_param("/helpdesk/tickets/1"),
			"/nxerp/go?redirect-to=%2Fhelpdesk%2Ftickets%2F1",
		)
		self.assertIsNone(routing.login_redirect_param("//evil.example"))
		self.assertIsNone(routing.login_redirect_param("https://evil.example"))
		already = "/nxerp/go?redirect-to=%2Fhelpdesk%2Fhome"
		self.assertEqual(routing.login_redirect_param(already), already)  # no loop

	# --- the decision after login -----------------------------------------------------------

	def route(self, user, redirect_to=None, setup_complete=True):
		with patch.object(frappe, "is_setup_complete", return_value=setup_complete):
			return routing.route(user, redirect_to)

	def test_case_1_administrator_gets_the_launcher(self):
		self.assertEqual(self.route("Administrator"), "/nxerp/apps")

	def test_first_run_administrator_goes_to_desk_so_the_setup_wizard_runs(self):
		self.assertEqual(self.route("Administrator", setup_complete=False), "/desk")
		# only the superuser: other users are not sent to a wizard they cannot finish
		self.assertEqual(self.route(self.agent, setup_complete=False), "/helpdesk/home")

	def test_case_2_helpdesk_only_user_skips_the_launcher(self):
		self.assertEqual(self.route(self.agent), "/helpdesk/home")

	def test_erpnext_only_user_goes_to_erpnext(self):
		self.assertEqual(self.route(self.erp), "/desk")

	def test_a_user_with_two_apps_gets_the_launcher(self):
		self.assertEqual(self.route(self.both), "/nxerp/apps")

	def test_no_apps_goes_to_the_no_access_page(self):
		self.assertEqual(self.route(self.noapps), "/nxerp/no-access")
		self.assertEqual(
			self.route(self.sysmgr), "/nxerp/no-access"
		)  # System Manager is not auto-granted apps

	def test_customer_goes_to_the_portal(self):
		self.assertEqual(self.route(self.customer), "/helpdesk/my-tickets")

	def test_disabled_and_guest_go_to_login(self):
		self.assertEqual(self.route(self.disabled), "/login")
		self.assertEqual(self.route("Guest"), "/login")

	def test_a_good_redirect_wins_only_when_authorised(self):
		self.assertEqual(self.route(self.agent, "/helpdesk/tickets/5"), "/helpdesk/tickets/5")
		self.assertEqual(self.route(self.both, "/desk/customer"), "/desk/customer")
		# unauthorised, hostile or malformed: the router decides
		self.assertEqual(self.route(self.agent, "/desk/customer"), "/helpdesk/home")
		self.assertEqual(self.route(self.agent, "//evil.example"), "/helpdesk/home")
		self.assertEqual(self.route(self.both, "https://evil.example"), "/nxerp/apps")
		self.assertEqual(self.route(self.noapps, "/helpdesk/home"), "/nxerp/no-access")

	def test_every_route_result_is_a_same_origin_path(self):
		users = (
			"Administrator",
			self.agent,
			self.erp,
			self.both,
			self.sysmgr,
			self.noapps,
			self.customer,
			self.disabled,
			"Guest",
		)
		for user in users:
			for raw in HOSTILE + list(GOOD):
				result = self.route(user, raw)
				self.assertTrue(result.startswith("/") and not result.startswith("//"), (user, raw, result))
				self.assertEqual(urlsplit(result).netloc, "")

	def test_the_session_hook_points_the_login_response_at_the_router(self):
		frappe.local.flags.home_page = None
		routing.on_session_creation()
		self.assertEqual(frappe.local.flags.home_page, "/nxerp/go")
		frappe.local.flags.home_page = None
