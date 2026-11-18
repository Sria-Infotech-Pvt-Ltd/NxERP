"""Onboarding, access requests and account creation, in process (no HTTP): the data model, the wizard's validation, the
policies, the approval path, and the rule that one user can never touch another's state."""

import inspect
import secrets
from dataclasses import replace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import access, onboarding, registry
from nxerp.api import access_request as access_request_api
from nxerp.api import account as account_api
from nxerp.api import onboarding as onboarding_api
from nxerp.tests.utils import delete_users, make_user, purge_test_users, unique_email

APP = "helpdesk"
BASICS = {"language": "en", "time_zone": "Asia/Kolkata"}


def with_policy(policy, **fields):
	"""The registry with the Helpdesk entry's policy replaced for the duration of a test."""
	entries = tuple(replace(e, signup_policy=policy, **fields) if e.key == APP else e for e in registry.APPS)
	return patch.object(registry, "APPS", entries)


class TestOnboarding(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		purge_test_users()
		cls.created = []
		cls.pw = secrets.token_urlsafe(16)
		cls.alice = cls.mk("o-alice", first_name="Alice")
		cls.bob = cls.mk("o-bob", first_name="Bob")
		cls.manager = cls.mk("o-mgr", roles=["System Manager"], first_name="Mgr")
		frappe.db.commit()

	@classmethod
	def mk(cls, prefix, roles=(), **kw):
		doc = make_user(
			unique_email(prefix),
			roles,
			password=cls.pw,
			user_type="Website User" if not roles else "System User",
			**kw,
		)
		cls.created.append(doc.name)
		return doc.name

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.wipe()
		delete_users(cls.created)
		frappe.db.commit()
		super().tearDownClass()

	@classmethod
	def wipe(cls):
		for doctype in ("NXERP Access Request", "NXERP Onboarding"):
			for name in frappe.get_all(doctype, filters={"user": ["in", cls.created]}, pluck="name"):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self.wipe()
		for user in self.created:  # undo grants from earlier tests
			if frappe.db.exists("Has Role", {"parent": user, "role": "NXERP Access: Helpdesk"}):
				frappe.db.delete(
					"Has Role", {"parent": user, "role": ["in", ("NXERP Access: Helpdesk", "Desk User")]}
				)
		frappe.db.set_value("User", self.alice, "user_type", "Website User")
		frappe.clear_cache()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def finish(self, user, extra=None):
		onboarding.save_step(user, APP, "basics", BASICS)
		if extra is not None:
			onboarding.save_step(user, APP, "about", extra)
		return onboarding.submit(user, APP)

	# --- the wizard ---------------------------------------------------------------------------

	def test_a_new_user_starts_at_the_first_step(self):
		state = onboarding.get_state(self.alice, APP)
		self.assertEqual((state["status"], state["current"]), ("wizard", "basics"))
		self.assertEqual(state["steps"], ["basics", "about", "request"])

	def test_progress_is_saved_and_resumes(self):
		onboarding.save_step(self.alice, APP, "basics", BASICS)
		state = onboarding.get_state(self.alice, APP)
		self.assertEqual((state["done"], state["current"]), (["basics"], "about"))
		self.assertEqual(state["prefill"]["time_zone"], "Asia/Kolkata")
		self.assertEqual(
			frappe.db.get_value("User", self.alice, "time_zone"),
			"Asia/Kolkata",
			"saved on the User's own field",
		)

	def test_the_optional_step_can_be_skipped_and_the_required_one_cannot(self):
		with self.assertRaises(frappe.ValidationError):
			onboarding.save_step(self.alice, APP, "basics", {})
		with self.assertRaises(frappe.ValidationError):
			onboarding.submit(self.alice, APP)
		onboarding.save_step(self.alice, APP, "basics", BASICS)
		onboarding.save_step(self.alice, APP, "about", {})
		self.assertEqual(onboarding.get_state(self.alice, APP)["current"], "request")

	def test_bad_input_is_refused(self):
		for step, data in (
			("basics", {"language": "xx-nope", "time_zone": "Asia/Kolkata"}),
			("basics", {"language": "en", "time_zone": "Mars/Base"}),
			("basics", {"language": "en", "time_zone": "Asia/Kolkata", "is_admin": "1"}),
			("basics", {"language": "en", "time_zone": ["Asia/Kolkata"]}),
			("basics", {"language": "en", "time_zone": "x" * 500}),
			("about", {"kind_of_work": "pirate"}),
			("about", {"team_size": "7"}),
			("about", "not a dict"),
			("request", {}),
			("nope", {}),
		):
			with self.assertRaises(frappe.ValidationError, msg=f"{step} {data!r}"):
				onboarding.save_step(self.alice, APP, step, data)

	def test_unknown_or_uninstalled_apps_are_refused_everywhere(self):
		for app in ("nope", "test-projects", "HELPDESK", "", None, ["helpdesk"]):
			with self.assertRaises(frappe.DoesNotExistError, msg=repr(app)):
				onboarding.get_state(self.alice, app)

	def test_the_registry_steps_are_all_known(self):
		for entry in registry.APPS:
			for step in entry.onboarding_steps:
				self.assertIn(step, onboarding.STEPS, f"{entry.key}: {step}")

	# --- submit, per policy -----------------------------------------------------------------------

	def test_request_access_creates_exactly_one_pending_request_and_no_access(self):
		state = self.finish(self.alice, {"kind_of_work": "support", "team_size": "2-10"})
		self.assertEqual(state["status"], "pending")
		self.assertEqual(
			frappe.db.count(
				"NXERP Access Request", {"user": self.alice, "app_key": APP, "status": "Pending"}
			),
			1,
		)
		self.assertFalse(access.can_access_app(self.alice, APP), "signing up and asking never grants access")
		self.assertEqual(onboarding.submit(self.alice, APP)["status"], "pending")
		self.assertEqual(
			frappe.db.count("NXERP Access Request", {"user": self.alice}), 1, "submit twice is harmless"
		)

	def test_invite_only_creates_no_request(self):
		with with_policy("invite_only"):
			state = self.finish(self.alice)
		self.assertEqual(state["status"], "invitation")
		self.assertEqual(frappe.db.count("NXERP Access Request", {"user": self.alice}), 0)

	def test_open_portal_grants_the_portal_role_and_never_a_staff_role(self):
		with with_policy("open_portal", portal_roles=("HD Customer",)):
			state = self.finish(self.alice)
			self.assertEqual(state["status"], "granted")
			roles = set(frappe.get_roles(self.alice))
			self.assertIn("HD Customer", roles)
			self.assertFalse(access.can_access_app(self.alice, APP))
			self.assertTrue(access.can_use_portal(self.alice, APP))
		self.assertEqual(frappe.db.count("NXERP Access Request", {"user": self.alice}), 0)

	def test_open_portal_without_a_portal_role_falls_back_to_a_request(self):
		with with_policy("open_portal", portal_roles=()):
			self.assertEqual(self.finish(self.alice)["status"], "pending")

	def test_the_per_user_cap_stops_a_flood_of_requests(self):
		for _i in range(onboarding_cap()):
			req = frappe.get_doc(
				{"doctype": "NXERP Access Request", "user": self.alice, "app_key": APP}
			).insert(ignore_permissions=True)
			frappe.db.set_value("NXERP Access Request", req.name, "status", "Cancelled")
		with self.assertRaises(frappe.ValidationError):
			self.finish(self.alice)

	# --- the request record ---------------------------------------------------------------------

	def test_the_request_record_validates(self):
		def new(**kw):
			return frappe.get_doc(
				{"doctype": "NXERP Access Request", "user": self.alice, "app_key": APP, **kw}
			)

		for bad in (
			{"app_key": "nope"},
			{"app_key": "test-projects"},
			{"user": "Administrator"},
			{"note": "x" * 501},
			{"status": "Approved"},
		):
			with self.assertRaises(frappe.ValidationError, msg=str(bad)):
				new(**bad).insert(ignore_permissions=True)
		first = new(note="<script>alert(1)</script>hello").insert(ignore_permissions=True)
		self.assertNotIn("<script>", first.note)
		with self.assertRaises(frappe.ValidationError):
			new().insert(ignore_permissions=True)  # one open request per user and app

	def test_only_system_managers_may_read_the_queue_directly(self):
		self.finish(self.alice)
		frappe.set_user(self.bob)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("NXERP Access Request")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				"NXERP Access Request", frappe.db.get_value("NXERP Access Request", {"user": self.alice})
			).check_permission("read")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("NXERP Onboarding", f"{self.alice}:{APP}").check_permission("read")

	# --- one user cannot touch another ----------------------------------------------------------

	def test_the_api_takes_the_user_from_the_session_only(self):
		for fn in (onboarding_api.get_state, onboarding_api.save_step, onboarding_api.submit):
			self.assertNotIn("user", inspect.signature(fn).parameters)
		self.assertNotIn("user", inspect.signature(access_request_api.decide).parameters)

	def test_one_user_cannot_read_or_change_anothers_state(self):
		frappe.set_user(self.alice)
		onboarding_api.save_step(APP, "basics", BASICS)
		onboarding_api.save_step(APP, "about", {"kind_of_work": "finance"})
		onboarding_api.submit(APP)
		frappe.set_user(self.bob)
		state = onboarding_api.get_state(APP)
		self.assertEqual((state["status"], state["done"]), ("wizard", []), "Bob sees his own blank state")
		self.assertNotIn("finance", str(state))
		onboarding_api.save_step(APP, "about", {"kind_of_work": "sales"})
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("NXERP Access Request", {"user": self.alice}), 1)
		self.assertEqual(frappe.db.count("NXERP Access Request", {"user": self.bob}), 0)
		self.assertIn("finance", frappe.db.get_value("NXERP Onboarding", f"{self.alice}:{APP}", "answers"))

	def test_guests_cannot_use_the_onboarding_api(self):
		frappe.set_user("Guest")
		for call in (
			lambda: onboarding_api.get_state(APP),
			lambda: onboarding_api.save_step(APP, "basics", BASICS),
			lambda: onboarding_api.submit(APP),
		):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_a_user_cannot_decide_their_own_request(self):
		self.finish(self.alice)
		name = frappe.db.get_value("NXERP Access Request", {"user": self.alice})
		frappe.set_user(self.alice)
		with self.assertRaises(frappe.PermissionError):
			access_request_api.decide(name, "Approve")
		self.assertFalse(access.can_access_app(self.alice, APP))

	# --- approval -------------------------------------------------------------------------------

	def test_approval_grants_through_the_one_grant_path(self):
		self.finish(self.alice)
		name = frappe.db.get_value("NXERP Access Request", {"user": self.alice})
		frappe.set_user(self.manager)
		result = access_request_api.decide(name, "Approve", "Welcome")
		self.assertEqual(result["status"], "Approved")
		self.assertIn(APP, [e.key for e in access.get_user_apps(self.alice)])
		self.assertEqual(frappe.db.get_value("User", self.alice, "user_type"), "System User")
		doc = frappe.get_doc("NXERP Access Request", name)
		self.assertEqual((doc.decided_by, doc.note), (self.manager, "Welcome"))
		self.assertEqual(onboarding.get_state(self.alice, APP)["status"], "granted")

	def test_deciding_twice_is_harmless(self):
		self.finish(self.alice)
		name = frappe.db.get_value("NXERP Access Request", {"user": self.alice})
		frappe.set_user(self.manager)
		access_request_api.decide(name, "Approve")
		again = access_request_api.decide(name, "Reject", "changed my mind")
		self.assertEqual(again["status"], "Approved")
		self.assertTrue(access.can_access_app(self.alice, APP))

	def test_rejection_grants_nothing_and_a_new_request_is_possible(self):
		self.finish(self.alice)
		name = frappe.db.get_value("NXERP Access Request", {"user": self.alice})
		frappe.set_user(self.manager)
		self.assertEqual(access_request_api.decide(name, "Reject", "Not now")["status"], "Rejected")
		self.assertFalse(access.can_access_app(self.alice, APP))
		self.assertEqual(onboarding.get_state(self.alice, APP)["status"], "wizard")

	def test_bad_decisions_are_refused(self):
		self.finish(self.alice)
		name = frappe.db.get_value("NXERP Access Request", {"user": self.alice})
		frappe.set_user(self.manager)
		for args in (
			(name, "Delete"),
			(name, ""),
			("NXAR-99999", "Approve"),
			(name, "Approve", "x" * 501),
		):
			with self.assertRaises((frappe.ValidationError, frappe.DoesNotExistError)):
				access_request_api.decide(*args)
		self.assertFalse(access.can_access_app(self.alice, APP))


def onboarding_cap():
	from nxerp.nxerp_platform.doctype.nxerp_access_request.nxerp_access_request import MAX_REQUESTS_PER_USER

	return MAX_REQUESTS_PER_USER


class TestAccountSignUp(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Guest")
		# Frappe's sanitize_redirect reads the request's host and scheme
		frappe.local.request = frappe._dict(host="localhost:8000", scheme="http", headers={})
		self.email = f"nxt-signup-{secrets.token_hex(4)}@example.test"
		self.keep = (
			frappe.conf.get("nxerp_enable_signup"),
			frappe.db.get_single_value("Website Settings", "disable_signup"),
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.request = None
		frappe.local.conf["nxerp_enable_signup"] = self.keep[0]
		frappe.db.set_single_value("Website Settings", "disable_signup", self.keep[1])
		purge_test_users()
		frappe.db.commit()

	def enable(self):
		frappe.local.conf["nxerp_enable_signup"] = 1
		frappe.db.set_single_value("Website Settings", "disable_signup", 0)
		frappe.clear_cache()

	def test_signup_is_refused_and_creates_nothing_while_it_is_off(self):
		frappe.local.conf["nxerp_enable_signup"] = 0
		with self.assertRaises(frappe.PermissionError):
			account_api.create_account(self.email, "Test Person", APP)
		self.assertFalse(frappe.db.exists("User", self.email))
		self.assertFalse(account_api.signup_available())

	def test_both_the_site_config_and_frappes_own_setting_must_agree(self):
		frappe.local.conf["nxerp_enable_signup"] = 1
		frappe.db.set_single_value("Website Settings", "disable_signup", 1)
		frappe.clear_cache()
		self.assertFalse(account_api.signup_available())

	def test_signup_creates_a_website_user_with_no_staff_role_and_no_portal_role(self):
		self.enable()
		result = account_api.create_account(self.email, "  Test   Person ", APP)
		self.assertIn("next step", result["message"])
		user = frappe.get_doc("User", self.email)
		self.assertEqual((user.user_type, user.first_name), ("Website User", "Test Person"))
		roles = {r.role for r in user.roles}
		self.assertFalse(
			roles
			& {"NXERP Access: Helpdesk", "NXERP Access: ERPNext", "Agent", "System Manager", "Desk User"},
			roles,
		)
		self.assertNotIn(
			"HD Customer", roles, "Portal Settings' default role is not handed out by signing up"
		)
		self.assertFalse(access.get_user_apps(self.email))

	def test_the_answer_is_the_same_for_a_registered_email(self):
		self.enable()
		first = account_api.create_account(self.email, "Test Person", APP)
		second = account_api.create_account(self.email, "Test Person", APP)
		self.assertEqual(first, second)
		self.assertEqual(frappe.db.count("User", {"email": self.email}), 1)

	def test_bad_input_and_unknown_products_are_refused(self):
		self.enable()
		for args in (
			("not-an-email", "Test Person", APP),
			(self.email, "", APP),
			(self.email, "x" * 200, APP),
			(self.email, "Test Person", "nope"),
			(self.email, "Test Person", "test-projects"),
			(self.email, "Test Person", None),
		):
			with self.assertRaises((frappe.ValidationError, frappe.DoesNotExistError), msg=repr(args)):
				account_api.create_account(*args)
		self.assertFalse(frappe.db.exists("User", self.email))

	def test_the_post_login_destination_is_the_welcome_route(self):
		self.enable()
		account_api.create_account(self.email, "Test Person", "erpnext")
		self.assertTrue(frappe.cache.hget("redirect_after_login", self.email).endswith("/welcome/erpnext"))

	def test_the_endpoint_is_post_only_guest_callable_and_rate_limited(self):
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[account_api.sign_up], ["POST"])
		self.assertIn(account_api.sign_up, frappe.guest_methods)
		self.assertIn("@rate_limit(", inspect.getsource(account_api))
