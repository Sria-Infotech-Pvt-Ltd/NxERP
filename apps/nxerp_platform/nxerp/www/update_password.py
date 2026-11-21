"""/update-password?key=...: set or change a password, in the NXDESK look.

Overrides `frappe/www/update-password`. Nothing about passwords is decided here: the page calls Frappe's own
`update_password` (key from the emailed link, or the old password of a signed-in user) and `test_password_strength`."""

import frappe
from frappe import _

from nxerp import public_site

no_cache = 1


def get_context(context):
	public_site.base_context(context, title=_("Set Password"), description="")
	context.product = public_site.platform_hero()
	context.csrf_token = frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else ""
	context.expired = bool(frappe.form_dict.get("password_expired"))
	return context
