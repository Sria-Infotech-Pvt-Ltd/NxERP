"""Whitelisted first-run API. Thin: the logic is in `nxerp.onboarding`.

Every method needs a session and works on `frappe.session.user` only. The user is never a parameter, so one user
cannot read or change another's state. `app` is validated against the registry inside `nxerp.onboarding`.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from nxerp import onboarding


def _user() -> str:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please sign in"), frappe.PermissionError)
	return user


@frappe.whitelist()
def get_state(app: str) -> dict:
	return onboarding.get_state(_user(), app)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60 * 60)
def save_step(app: str, step: str, data=None) -> dict:
	if isinstance(data, str):
		data = frappe.parse_json(data)
	return onboarding.save_step(_user(), app, step, data or {})


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def submit(app: str) -> dict:
	return onboarding.submit(_user(), app)
