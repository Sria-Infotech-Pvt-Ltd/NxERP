"""Public account creation for a product's "Get started" flow.

Wraps Frappe's own `sign_up` (which creates a Website User and emails the set-password link) and adds what the
platform needs: the product must be an installed registry app, the post-login destination goes through
`routing.safe_target`, the answer is the same whether or not the email is already registered, and a self-signed
account never keeps a portal role it did not ask for (Portal Settings' default role would otherwise hand every
signup the Helpdesk customer role). Nothing here grants staff access.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import validate_email_address

from nxerp import registry, routing

MAX_NAME_LENGTH = 80
SIGNUP_LIMIT_PER_HOUR = 10
NEUTRAL_MESSAGE = "If the address can be used, a message with the next step is on its way."


def signup_available() -> bool:
	"""Signup is open only when the operator switched it on (site config) and Frappe's own setting agrees."""
	return bool(
		frappe.utils.cint(frappe.conf.get("nxerp_enable_signup"))
		and not frappe.utils.cint(frappe.get_website_settings("disable_signup"))
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=SIGNUP_LIMIT_PER_HOUR, seconds=60 * 60)
def sign_up(email: str, full_name: str, app: str) -> dict:
	return create_account(email, full_name, app)


def create_account(email: str, full_name: str, app: str) -> dict:
	if not signup_available():
		frappe.throw(_("Signup is not available"), frappe.PermissionError)
	entry = registry.public_entry(app)
	if not entry:
		frappe.throw(_("Unknown or uninstalled application"), frappe.DoesNotExistError)

	email = (email or "").strip().lower()
	full_name = " ".join((full_name or "").split())
	if not full_name or len(full_name) > MAX_NAME_LENGTH:
		frappe.throw(_("Enter your full name"), frappe.ValidationError)
	if not validate_email_address(email):
		frappe.throw(_("Enter a valid email address"), frappe.ValidationError)

	redirect_to = routing.safe_target(routing.WELCOME_ROUTE.format(key=entry.key)) or ""
	existed = bool(frappe.db.exists("User", email))

	from frappe.core.doctype.user.user import sign_up as frappe_sign_up

	frappe_sign_up(email=email, full_name=full_name, redirect_to=redirect_to)

	if not existed:
		_drop_default_portal_role(email)
	return {"message": _(NEUTRAL_MESSAGE)}


def _drop_default_portal_role(user: str):
	"""Frappe adds Portal Settings' default role to every signup. If that is a product's portal role, remove it:
	portal access comes from the product's own policy (`open_portal`), not from creating an account."""
	role = frappe.db.get_single_value("Portal Settings", "default_role")
	portal_roles = {r for e in registry.installed_entries() for r in e.portal_roles}
	if role and role in portal_roles:
		frappe.db.delete("Has Role", {"parent": user, "parenttype": "User", "role": role})
		frappe.clear_cache(user=user)
