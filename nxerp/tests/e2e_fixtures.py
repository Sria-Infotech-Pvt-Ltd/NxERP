"""Fixtures for the Playwright suite in /e2e: clearly fake users for every journey and the role of a
test-only third app. Never part of a shipped site; the suite runs on its own fresh site (e2e/site.sh).

Run inside the bench container (e2e/run.sh does this for you):

	NXERP_E2E_PASSWORD=... bench --site nxerp-e2e.localhost execute nxerp.tests.e2e_fixtures.setup
	bench --site nxerp-e2e.localhost execute nxerp.tests.e2e_fixtures.teardown

Refuses to run unless developer_mode and allow_tests are both on, so it cannot touch a real site.
The password comes from the environment and is never printed or stored.
"""

import os

import frappe
from frappe.installer import update_site_config

from nxerp.tests.utils import ERP_ACCESS, PLAIN_DESK_ROLE, delete_users, make_user, purge_test_users

DOMAIN = "example.test"
TEST_APP_ROLE = "NXERP Access: Test Projects"
TEST_APP = {
	"key": "test-projects",
	"title": "Test Projects",
	"route": "/nxerp/test-app",
	"access_role": TEST_APP_ROLE,
	"order": 30,
}

# persona -> (roles, extra make_user arguments)
PERSONAS = {
	"agent": (["Agent"], {}),  # Case 2: one app
	"erp": (["Sales User", ERP_ACCESS], {}),  # one app: ERPNext
	"both": (["Agent Manager", ERP_ACCESS], {}),  # two apps
	"manager": (["Agent Manager", TEST_APP_ROLE], {}),  # Case 3: Helpdesk plus the test-only app
	"none": ([PLAIN_DESK_ROLE], {}),  # signed in, no application
	"customer": (["HD Customer"], {"user_type": "Website User"}),
	"disabled": (["Agent"], {"enabled": 0}),
	"reset": (["Agent"], {}),  # password-reset flow
	"otp": (["Agent"], {}),  # two-factor flow
	"lockout": (["Agent"], {}),  # lockout flow
	"expiry": (["Agent"], {}),  # session expiry flow
}


def email(key: str) -> str:
	return f"nxt-e2e-{key}@{DOMAIN}"


def _guard():
	if not (frappe.conf.get("developer_mode") and frappe.conf.get("allow_tests")):
		frappe.throw("E2E fixtures need developer_mode and allow_tests; refusing to run on this site.")


def setup():
	_guard()
	password = os.environ.get("NXERP_E2E_PASSWORD")
	if not password:
		frappe.throw("Set NXERP_E2E_PASSWORD for the fake users.")

	frappe.set_user("Administrator")
	purge_test_users()

	if not frappe.db.exists("Role", TEST_APP_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": TEST_APP_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)

	for key, (roles, kwargs) in PERSONAS.items():
		make_user(email(key), roles, password=password, first_name=f"E2E {key.title()}", **kwargs)

	frappe.db.commit()
	frappe.clear_cache()

	print("e2e fixtures ready:", ", ".join(email(k) for k in PERSONAS))


def teardown():
	_guard()
	frappe.set_user("Administrator")
	update_site_config("nxerp_test_apps", [])
	update_site_config("nxerp_stock_login", 0)
	delete_users([email(k) for k in (*PERSONAS, "owner")])
	if frappe.db.exists("Role", TEST_APP_ROLE):
		frappe.delete_doc("Role", TEST_APP_ROLE, force=True, ignore_permissions=True)

	frappe.db.commit()
	frappe.clear_cache()
	print("e2e fixtures removed")


# --- helpers the browser tests call between steps ---------------------------------------------------------


def expire_sessions(user: str):
	"""Server-side session expiry: the user's sessions vanish exactly as they do when Frappe expires them."""
	_guard()
	from frappe.sessions import clear_sessions

	clear_sessions(user, force=True)
	frappe.db.commit()


def two_factor(enabled: bool = True):
	"""Turn Frappe's two-factor authentication (OTP by email) on or off for the site."""
	_guard()
	settings = frappe.get_doc("System Settings")
	settings.enable_two_factor_auth = 1 if enabled else 0
	settings.two_factor_method = "Email"
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	frappe.clear_cache()


def use_mail_sink(port: int = 2525):
	"""Point outgoing mail at a local capture server (e2e/lib/mailsink.mjs); nothing leaves the machine."""
	_guard()
	name = "NXERP E2E Sink"
	if frappe.db.exists("Email Account", name):
		frappe.delete_doc("Email Account", name, force=True, ignore_permissions=True)
	frappe.db.sql("update `tabEmail Account` set default_outgoing = 0")
	frappe.get_doc(
		{
			"doctype": "Email Account",
			"email_account_name": name,
			"email_id": "noreply-e2e@example.test",
			"enable_outgoing": 1,
			"default_outgoing": 1,
			"smtp_server": "127.0.0.1",
			"smtp_port": port,
			"use_tls": 0,
			"use_ssl": 0,
			"no_smtp_authentication": 1,
			"always_use_account_email_id_as_sender": 1,
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()


def drop_mail_sink():
	_guard()
	name = "NXERP E2E Sink"
	if frappe.db.exists("Email Account", name):
		frappe.delete_doc("Email Account", name, force=True, ignore_permissions=True)
	frappe.db.sql("delete from `tabEmail Queue` where sender = 'noreply-e2e@example.test'")
	frappe.db.commit()


def flush_mail():
	"""Send whatever is queued now (a worker would do this every minute)."""
	_guard()
	from frappe.email.queue import flush

	flush()
	frappe.db.commit()
	print("queued after flush:", frappe.db.count("Email Queue", {"status": "Not Sent"}))


def setup_state():
	"""Prints SETUP=1 once the setup wizard has finished on this site (it runs in a background job)."""
	_guard()
	print(f"SETUP={1 if frappe.is_setup_complete() else 0}")


def email_link_login(enabled: bool = True):
	"""Frappe's "Login With Email Link" system setting (off by default)."""
	_guard()
	settings = frappe.get_doc("System Settings")
	settings.login_with_email_link = 1 if enabled else 0
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	frappe.clear_cache()


def delete_user(user: str):
	"""Remove a user the tests created through the runbook commands (break-glass administrator)."""
	_guard()
	if user.endswith("@example.test") and frappe.db.exists("User", user):
		frappe.flags.in_patch = True  # the last-administrator guard must not stop cleaning up fixtures
		try:
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
		finally:
			frappe.flags.in_patch = False
		frappe.db.commit()
