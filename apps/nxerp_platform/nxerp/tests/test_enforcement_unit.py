"""The gate's decisions, table-driven and in process (no HTTP): classification, shared set,
guests, fail-closed behaviour, and the document-level and list-level hooks."""

import json
import types
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.exceptions import HTTPException

from nxerp import access, enforcement
from nxerp.tests.utils import (
	ERP_ACCESS,
	PLAIN_DESK_ROLE,
	delete_users,
	make_user,
	purge_test_users,
	unique_email,
)

CUSTOMER_DOC = json.dumps({"doctype": "Customer", "customer_name": "x"})


class TestEnforcementUnit(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		purge_test_users()
		cls.created = []

		def mk(prefix, roles, **kw):
			doc = make_user(unique_email(prefix), roles, **kw)
			cls.created.append(doc.name)
			return doc.name

		cls.agent = mk("u-agent", ["Agent"])
		cls.erp = mk("u-erp", ["Sales User", ERP_ACCESS])
		cls.sysmgr = mk("u-sys", ["System Manager"])
		cls.noapps = mk("u-none", [PLAIN_DESK_ROLE])
		cls.customer = mk("u-cust", ["HD Customer"], user_type="Website User")
		cls.disabled = mk("u-off", ["Agent", ERP_ACCESS], enabled=0)
		# holds ERPNext's business role, so only NXERP's gate (not Frappe's role check) can refuse them
		cls.erp_role_only = mk("u-erprole", ["Sales User"])

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		delete_users(cls.created)
		frappe.db.rollback()
		super().tearDownClass()

	def decide(self, user, path, form=None, method="GET"):
		return enforcement.evaluate_request(user, path, method, form or {})

	# --- pages ---------------------------------------------------------------------------

	def test_desk_pages(self):
		self.assertTrue(self.decide("Administrator", "/desk").allow)
		self.assertTrue(self.decide(self.erp, "/desk/customer").allow)
		self.assertTrue(self.decide(self.sysmgr, "/desk").allow)  # platform admin shell
		for user in (self.agent, self.noapps, self.customer):
			d = self.decide(user, "/desk")
			self.assertFalse(d.allow, user)
			self.assertEqual(d.redirect, "/nxerp/no-access?app=erpnext")

	def test_a_disabled_account_reaches_nothing_even_shared_endpoints(self):
		for path in ("/api/method/frappe.client.get_count", "/api/resource/ToDo", "/helpdesk/home", "/desk"):
			d = self.decide(self.disabled, path, {"doctype": "ToDo"})
			self.assertFalse(d.allow, path)
			self.assertEqual(d.reason, "disabled")
		# pages go to login, API calls get a JSON refusal; logging out stays possible
		self.assertEqual(self.decide(self.disabled, "/desk").redirect, "/login")
		self.assertIsNone(self.decide(self.disabled, "/api/resource/ToDo").redirect)
		self.assertTrue(self.decide(self.disabled, "/api/method/logout").allow)

	def test_portal_only_users_may_not_use_document_info_bundles(self):
		for method in ("frappe.desk.form.load.getdoc", "frappe.desk.form.load.get_docinfo"):
			d = self.decide(self.customer, f"/api/method/{method}", {"doctype": "HD Ticket", "name": "1"})
			self.assertFalse(d.allow, method)
			self.assertEqual(d.reason, "portal_method")
			# staff, and shared DocTypes, are untouched
			self.assertTrue(self.decide(self.agent, f"/api/method/{method}", {"doctype": "HD Ticket"}).allow)
			self.assertTrue(self.decide(self.customer, f"/api/method/{method}", {"doctype": "User"}).allow)

	def test_portal_only_classification(self):
		self.assertTrue(access.is_portal_only(self.customer))
		for user in (self.agent, self.erp, self.sysmgr, self.noapps, "Administrator", "Guest", self.disabled):
			self.assertFalse(access.is_portal_only(user), user)

	def test_strip_keys_is_recursive_and_exact(self):
		data = {
			"a": 1,
			"_assign": "x",
			"rows": [{"name": "1", "_assign": "y", "_comments": "z", "keep": {"_assign": "w", "ok": 2}}],
		}
		self.assertEqual(
			enforcement.strip_keys(data),
			{"a": 1, "rows": [{"name": "1", "keep": {"ok": 2}}]},
		)
		self.assertEqual(enforcement.strip_keys([1, "_assign", None]), [1, "_assign", None])

	def _response(self, payload, mimetype="application/json"):
		from werkzeug.wrappers import Response

		return Response(json.dumps(payload), mimetype=mimetype)

	def test_after_request_strips_for_portal_only_and_leaves_everyone_else(self):
		self._request("/api/resource/HD Ticket")
		payload = {"data": [{"name": "1", "_assign": '["a@example.test"]'}]}
		for user, expect_stripped in (
			(self.customer, True),
			(self.agent, False),
			(self.erp, False),
			("Administrator", False),
		):
			frappe.set_user(user)
			response = self._response(payload)
			enforcement.after_request(response=response, request=frappe.local.request)
			has_key = "_assign" in response.get_data(as_text=True)
			self.assertEqual(has_key, not expect_stripped, user)

	def test_after_request_ignores_non_json_and_non_api(self):
		frappe.set_user(self.customer)
		self._request("/helpdesk/home")
		html = self._response({"_assign": 1}, mimetype="text/html")
		enforcement.after_request(response=html, request=frappe.local.request)
		self.assertIn("_assign", html.get_data(as_text=True))

	def test_after_request_fails_closed_for_portal_users(self):
		self._request("/api/resource/HD Ticket")
		frappe.set_user(self.customer)
		response = self._response({"data": [{"_assign": "x"}]})
		with patch.object(enforcement, "strip_keys", side_effect=RuntimeError("boom")):
			enforcement.after_request(response=response, request=frappe.local.request)
		self.assertEqual(response.status_code, 403)
		self.assertNotIn("_assign", response.get_data(as_text=True))

	def test_legacy_app_prefix_is_gated_like_desk(self):
		self.assertFalse(self.decide(self.agent, "/app/home").allow)

	def test_spa_pages(self):
		for user in ("Administrator", self.agent, self.customer):  # staff and portal
			self.assertTrue(self.decide(user, "/helpdesk/home").allow, user)
		for user in (self.erp, self.sysmgr, self.noapps):
			d = self.decide(user, "/helpdesk/home")
			self.assertFalse(d.allow, user)
			self.assertEqual(d.redirect, "/nxerp/no-access?app=helpdesk")

	def test_guest_is_sent_to_login_from_both_apps(self):
		for path in ("/desk", "/helpdesk", "/helpdesk/tickets/1"):
			d = self.decide("Guest", path)
			self.assertFalse(d.allow)
			self.assertTrue(d.redirect.startswith("/login?redirect-to="), d.redirect)

	# --- API: owned methods --------------------------------------------------------------

	def test_owned_method_roots(self):
		erp_method = "/api/method/erpnext.accounts.utils.get_fiscal_year"
		hd_method = "/api/method/helpdesk.api.auth.get_user"
		self.assertTrue(self.decide(self.erp, erp_method).allow)
		self.assertFalse(self.decide(self.agent, erp_method).allow)
		self.assertTrue(self.decide(self.agent, hd_method).allow)
		self.assertFalse(self.decide(self.erp, hd_method).allow)
		self.assertTrue(self.decide(self.customer, hd_method).allow)  # portal
		self.assertFalse(self.decide(self.customer, erp_method).allow)

	def test_rpc_style_cmd_is_classified_like_the_rest_path(self):
		d = self.decide(self.agent, "/", {"cmd": "erpnext.accounts.utils.get_fiscal_year"})
		self.assertFalse(d.allow)
		self.assertEqual(d.surface, "api_method")

	def test_v2_method_path(self):
		self.assertFalse(
			self.decide(self.agent, "/api/v2/method/erpnext.accounts.utils.get_fiscal_year").allow
		)

	# --- API: DocType named in the path or the arguments ---------------------------------

	def test_resource_paths(self):
		for base in ("/api/resource/", "/api/v2/document/", "/api/v2/doctype/"):
			self.assertFalse(self.decide(self.agent, f"{base}Customer").allow, base)
			self.assertFalse(self.decide(self.agent, f"{base}Sales%20Invoice/SINV-1").allow, base)
			self.assertTrue(self.decide(self.erp, f"{base}Customer").allow, base)
			self.assertFalse(self.decide(self.erp, f"{base}HD%20Ticket").allow, base)
			self.assertTrue(self.decide(self.agent, f"{base}HD%20Ticket").allow, base)

	def test_doctype_arguments_of_generic_methods(self):
		generic = "/api/method/frappe.client.get_list"
		self.assertFalse(self.decide(self.agent, generic, {"doctype": "Customer"}).allow)
		self.assertFalse(self.decide(self.agent, generic, {"dt": "Customer"}).allow)
		self.assertTrue(self.decide(self.erp, generic, {"doctype": "Customer"}).allow)
		self.assertTrue(self.decide(self.agent, generic, {"doctype": "HD Ticket"}).allow)

	def test_json_document_arguments(self):
		insert = "/api/method/frappe.client.insert"
		self.assertFalse(self.decide(self.agent, insert, {"doc": CUSTOMER_DOC}).allow)
		self.assertFalse(
			self.decide(self.agent, insert, {"docs": json.dumps([{"doctype": "Customer"}])}).allow
		)
		self.assertTrue(self.decide(self.erp, insert, {"doc": CUSTOMER_DOC}).allow)

	def test_metadata_endpoints_are_gated_too(self):
		self.assertFalse(
			self.decide(
				self.agent, "/api/method/frappe.desk.form.load.getdoctype", {"doctype": "Customer"}
			).allow
		)
		self.assertFalse(self.decide(self.customer, "/api/v2/doctype/Customer/meta").allow)

	def test_reports_resolve_through_their_module(self):
		run = "/api/method/frappe.desk.query_report.run"
		self.assertFalse(self.decide(self.agent, run, {"report_name": "Accounts Receivable"}).allow)
		self.assertTrue(self.decide(self.erp, run, {"report_name": "Accounts Receivable"}).allow)
		self.assertTrue(self.decide(self.agent, run, {"report_name": "Ticket Summary"}).allow)
		self.assertFalse(self.decide(self.erp, run, {"report_name": "Ticket Summary"}).allow)

	def test_desk_loaders_are_gated_by_module(self):
		erp_page = frappe.db.get_value("Page", {"module": "Accounts"}, "name") or frappe.db.get_value(
			"Page", {"module": "Selling"}, "name"
		)
		erp_workspace = frappe.db.get_value("Workspace", {"module": "Accounts"}, "name")
		if erp_page:
			path = "/api/method/frappe.desk.desk_page.getpage"
			self.assertFalse(self.decide(self.agent, path, {"name": erp_page}).allow)
			self.assertTrue(self.decide(self.erp, path, {"name": erp_page}).allow)
		if erp_workspace:
			path = "/api/method/frappe.desk.desktop.get_desktop_page"
			page = json.dumps({"name": erp_workspace, "public": 1})
			self.assertFalse(self.decide(self.agent, path, {"page": page}).allow)
			self.assertTrue(self.decide(self.erp, path, {"page": page}).allow)
		self.assertTrue(erp_page or erp_workspace, "the site must have an ERPNext Page or Workspace to test")
		# a shared Page is never gated
		self.assertTrue(
			self.decide(self.agent, "/api/method/frappe.desk.desk_page.getpage", {"name": "print"}).allow
		)
		# malformed page argument must not crash or widen
		self.assertTrue(
			self.decide(
				self.agent, "/api/method/frappe.desk.desktop.get_desktop_page", {"page": "{bad"}
			).allow
		)

	def test_print_and_list_pages_use_the_doctype_gate(self):
		for path, form in (
			("/printview", {"doctype": "Customer", "name": "x"}),
			("/list", {"doctype": "Customer"}),
			("/api/method/frappe.utils.print_format.download_pdf", {"doctype": "Customer", "name": "x"}),
			("/api/method/upload_file", {"doctype": "Customer", "docname": "x"}),
			("/api/method/frappe.desk.reportview.export_query", {"doctype": "Customer"}),
		):
			d = self.decide(self.agent, path, form)
			self.assertFalse(d.allow, path)
			self.assertTrue(self.decide(self.erp, path, form).allow, path)
		# a browser page is redirected to the denial page; an API call gets JSON
		self.assertEqual(
			self.decide(self.agent, "/printview", {"doctype": "Customer"}).redirect,
			"/nxerp/no-access?app=erpnext",
		)
		self.assertIsNone(
			self.decide(self.agent, "/api/method/frappe.client.get_list", {"doctype": "Customer"}).redirect
		)

	def test_malformed_arguments_never_crash_and_never_widen(self):
		generic = "/api/method/frappe.client.get_list"
		for form in (
			{"doctype": ["Customer"]},
			{"doctype": 5},
			{"doc": "{not json"},
			{"docs": "[1,2]"},
			{"doctype": None},
		):
			self.assertTrue(
				self.decide(self.agent, generic, form).allow, form
			)  # not an owned DocType: Frappe decides

	# --- the shared set stays Frappe's -----------------------------------------------------

	def test_shared_doctypes_and_methods_are_never_gated_by_app(self):
		generic = "/api/method/frappe.client.get_list"
		for user in (self.agent, self.erp, self.sysmgr, self.noapps, self.customer):
			for doctype in (
				"User",
				"File",
				"Comment",
				"ToDo",
				"Notification Log",
				"Contact",
				"Role",
				"Version",
			):
				self.assertTrue(self.decide(user, generic, {"doctype": doctype}).allow, (user, doctype))
				self.assertTrue(self.decide(user, f"/api/resource/{doctype}").allow, (user, doctype))
			for method in (
				"frappe.desk.search.search_link",
				"frappe.sessions.clear",
				"frappe.client.get_count",
			):
				self.assertTrue(self.decide(user, f"/api/method/{method}").allow, (user, method))

	def test_unknown_custom_doctype_is_shared(self):
		self.assertTrue(self.decide(self.agent, "/api/resource/Some%20Custom%20Thing").allow)

	def test_authentication_and_the_denial_page_are_exempt(self):
		for user in ("Guest", self.noapps):
			for path in (
				"/login",
				"/logout",
				"/api/method/login",
				"/api/method/ping",
				"/nxerp/no-access",
				"/assets/helpdesk/x.js",
				"/update-password",
			):
				self.assertTrue(self.decide(user, path).allow, (user, path))

	def test_guest_api_is_left_to_frappe_allow_guest(self):
		self.assertTrue(self.decide("Guest", "/api/method/erpnext.accounts.utils.get_fiscal_year").allow)
		self.assertTrue(self.decide("Guest", "/api/resource/Customer").allow)

	def test_discovery_surfaces_are_platform_admin_only(self):
		self.assertTrue(self.decide(self.sysmgr, "/api/v2/discovery/search").allow)
		self.assertFalse(self.decide(self.agent, "/api/v2/discovery/search").allow)
		self.assertFalse(self.decide(self.erp, "/api/v2/mcp").allow)

	# --- fail closed ---------------------------------------------------------------------

	def _request(self, path, form=None, method="GET"):
		frappe.local.request = types.SimpleNamespace(path=path, method=method)
		frappe.local.form_dict = frappe._dict(form or {})

	def test_resolver_error_denies_a_normal_user_with_a_clean_response(self):
		self._request("/api/method/erpnext.accounts.utils.get_fiscal_year")
		frappe.set_user(self.erp)
		with patch.object(access, "can_reach_app", side_effect=RuntimeError("boom")):
			with self.assertRaises(HTTPException) as ctx:
				enforcement.auth_hook()
		response = ctx.exception.get_response()
		self.assertEqual(response.status_code, 403)
		self.assertNotIn("boom", response.get_data(as_text=True))
		self.assertNotIn("Traceback", response.get_data(as_text=True))

	def test_resolver_error_on_a_page_redirects_to_no_access(self):
		self._request("/helpdesk/home")
		frappe.set_user(self.agent)
		with patch.object(access, "can_access_app", side_effect=RuntimeError("boom")):
			with self.assertRaises(HTTPException) as ctx:
				enforcement.auth_hook()
		self.assertEqual(ctx.exception.get_response().status_code, 302)
		self.assertIn("/nxerp/no-access", ctx.exception.get_response().headers["Location"])

	def test_resolver_error_never_locks_out_administrator(self):
		self._request("/desk")
		frappe.set_user("Administrator")
		with (
			patch.object(access, "can_access_app", side_effect=RuntimeError("boom")),
			patch.object(enforcement, "evaluate_request", side_effect=RuntimeError("boom")),
		):
			enforcement.auth_hook()  # must not raise

	def test_denial_is_logged_without_personal_data(self):
		with patch("nxerp.audit._logger") as logger:
			self._request("/api/method/erpnext.accounts.utils.get_fiscal_year")
			frappe.set_user(self.agent)
			with self.assertRaises(HTTPException):
				enforcement.auth_hook()
		line = logger.return_value.warning.call_args[0][0]
		record = json.loads(line)
		self.assertEqual(record["event"], "nxerp.access.denied")
		self.assertEqual(record["app"], "erpnext")
		self.assertTrue(record["user_ref"].startswith("u:"))
		self.assertNotIn("@", line)
		self.assertNotIn(self.agent, line)

	# --- document level and list level -----------------------------------------------------

	def test_a_document_check_goes_through_the_hook(self):
		# frappe.has_permission reaches the wildcard hook for a user holding the business role
		customer = frappe.get_doc({"doctype": "Customer", "customer_name": "x"})
		self.assertFalse(frappe.has_permission("Customer", "read", doc=customer, user=self.erp_role_only))
		self.assertTrue(frappe.has_permission("Customer", "read", doc=customer, user=self.erp))

	def test_has_permission_hook_is_deny_only_and_app_scoped(self):
		customer = frappe.get_doc({"doctype": "Customer", "customer_name": "x"})
		ticket = frappe.get_doc({"doctype": "HD Ticket", "subject": "x"})
		todo = frappe.get_doc({"doctype": "ToDo", "description": "x"})
		self.assertFalse(enforcement.has_permission(customer, "read", self.agent))
		self.assertTrue(enforcement.has_permission(customer, "read", self.erp))
		self.assertFalse(enforcement.has_permission(ticket, "read", self.erp))
		self.assertTrue(enforcement.has_permission(ticket, "read", self.agent))
		self.assertTrue(enforcement.has_permission(todo, "read", self.noapps))  # shared
		self.assertTrue(enforcement.has_permission(customer, "read", "Administrator"))

	def test_has_permission_hook_fails_closed(self):
		customer = frappe.get_doc({"doctype": "Customer", "customer_name": "x"})
		with patch.object(access, "can_reach_app", side_effect=RuntimeError("boom")):
			self.assertFalse(enforcement.has_permission(customer, "read", self.erp))
			self.assertTrue(enforcement.has_permission(customer, "read", "Administrator"))

	def test_module_scoped_records_follow_their_module(self):
		report = frappe.get_doc({"doctype": "Report", "report_name": "x", "module": "Accounts"})
		self.assertFalse(enforcement.has_permission(report, "read", self.agent))
		self.assertTrue(enforcement.has_permission(report, "read", self.erp))
		helpdesk_report = frappe.get_doc({"doctype": "Report", "report_name": "y", "module": "Helpdesk"})
		self.assertTrue(enforcement.has_permission(helpdesk_report, "read", self.agent))

	def test_list_condition_hides_owned_doctypes_and_navigation(self):
		self.assertEqual(enforcement.permission_query_conditions(self.agent, "Customer"), "1=0")
		self.assertEqual(enforcement.permission_query_conditions(self.erp, "Customer"), "")
		self.assertEqual(enforcement.permission_query_conditions(self.noapps, "ToDo"), "")
		self.assertEqual(enforcement.permission_query_conditions("Administrator", "Customer"), "")
		condition = enforcement.permission_query_conditions(self.agent, "Workspace")
		self.assertIn("`tabWorkspace`.`module` not in (", condition)
		self.assertIn("'Accounts'", condition)
		self.assertNotIn("'Helpdesk'", condition)

	def test_list_condition_fails_closed(self):
		with patch.object(access, "can_reach_app", side_effect=RuntimeError("boom")):
			self.assertEqual(enforcement.permission_query_conditions(self.erp, "Customer"), "1=0")

	def test_a_real_list_query_honours_the_condition(self):
		# Frappe alone would allow this user to list Customers (they hold Sales User): the gate refuses
		frappe.set_user(self.erp_role_only)
		try:
			self.assertEqual(frappe.get_list("Customer", limit=1), [])
		finally:
			frappe.set_user("Administrator")
		frappe.set_user(self.erp)
		try:
			frappe.get_list("Customer", limit=1)  # granted: Frappe's own rules apply, no error from the gate
		finally:
			frappe.set_user("Administrator")

	def test_navigation_lists_hide_other_apps_modules(self):
		frappe.set_user(self.agent)
		try:
			modules = frappe.get_list("Workspace", pluck="module", limit=500)
		finally:
			frappe.set_user("Administrator")
		self.assertNotIn("Accounts", modules)
		self.assertNotIn("Selling", modules)
