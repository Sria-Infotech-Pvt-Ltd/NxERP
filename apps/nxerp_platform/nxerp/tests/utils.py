"""Fixtures shared by the access-layer tests: personas, demo data, an HTTP client."""

import json
import os
import secrets
import uuid

import frappe

DENIED_MESSAGE = "You do not have access to this application"

# a harmless core role that makes its holder a System User without conferring any NXERP app
PLAIN_DESK_ROLE = "Website Manager"

ERP_ROLES = ("Sales User", "Accounts User", "Item Manager")
ERP_ACCESS = "NXERP Access: ERPNext"
HD_ACCESS = "NXERP Access: Helpdesk"


def unique_email(prefix: str) -> str:
	return f"nxt-{prefix}-{uuid.uuid4().hex[:8]}@example.test"


def allow_many_test_users():
	"""Frappe throttles user creation (`throttle_user_limit`, default 60 per hour). Test runs create
	many throwaway users, so lift the limit for this process only; nothing is written to site config."""
	frappe.local.conf["throttle_user_limit"] = 100000


def purge_test_users():
	"""Delete users left behind by an aborted run (test users are committed so rollbacks keep them)."""
	frappe.set_user("Administrator")
	allow_many_test_users()
	for name in frappe.get_all("User", filters={"name": ["like", "nxt-%@example.test"]}, pluck="name"):
		frappe.flags.in_patch = True  # the last-administrator guard must not stop cleaning up fixtures
		try:
			frappe.delete_doc("User", name, force=True, ignore_permissions=True)
		finally:
			frappe.flags.in_patch = False
	frappe.db.commit()


def make_user(email, roles=(), user_type="System User", enabled=1, password=None, first_name="NXT"):
	"""Create a fake user. Unknown roles are skipped so tests run on any site."""
	allow_many_test_users()
	roles = [r for r in roles if frappe.db.exists("Role", r)]
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"user_type": user_type,
			"enabled": 1,
			"send_welcome_email": 0,
			"new_password": password or secrets.token_urlsafe(14),
			"roles": [{"role": r} for r in roles],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	if not enabled:
		doc.enabled = 0
		doc.flags.ignore_permissions = True
		doc.save()
	return doc


def delete_users(emails):
	for email in emails:
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)


def as_user(user):
	"""Context-free helper: run the next calls as `user`; callers restore Administrator in tearDown."""
	frappe.set_user(user)


# --- HTTP ---------------------------------------------------------------------------------------


def base_url() -> str:
	return os.environ.get("NXERP_TEST_BASE", "http://localhost:8000")


class Client:
	"""A logged-in HTTP session against the running site (real auth_hooks, real redirects)."""

	def __init__(self, email=None, password=None):
		import requests

		self.s = requests.Session()
		self.email = email
		if email:
			r = self.s.post(
				base_url() + "/api/method/login", data={"usr": email, "pwd": password}, allow_redirects=False
			)
			if r.status_code != 200:
				raise AssertionError(f"login failed for a test user: HTTP {r.status_code}")

	def get(self, path, **kw):
		return self.s.get(base_url() + path, allow_redirects=False, timeout=60, **kw)

	def post(self, path, data=None, json_body=None, **kw):
		if json_body is not None:
			kw["json"] = json_body
		return self.s.post(base_url() + path, data=data, allow_redirects=False, timeout=60, **kw)


def denied_by_gate(resp) -> bool:
	"""True when NXERP's gate (not Frappe's own permission system) produced the denial."""
	if resp.status_code == 302:
		return "/nxerp/no-access" in resp.headers.get("Location", "")
	if resp.status_code != 403:
		return False
	try:
		return resp.json().get("message") == DENIED_MESSAGE
	except Exception:
		return False


def redirected_to_login(resp) -> bool:
	return resp.status_code == 302 and "/login" in resp.headers.get("Location", "")


def blocked(resp) -> bool:
	"""Any refusal: gate, Frappe permission error, hidden record, or a redirect away."""
	return resp.status_code in (302, 401, 403, 404)


def body(resp) -> str:
	try:
		return json.dumps(resp.json())
	except Exception:
		return resp.text or ""
