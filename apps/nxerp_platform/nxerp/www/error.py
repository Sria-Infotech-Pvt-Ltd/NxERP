"""/error: the server-error page in the NXDESK look. Overrides `frappe/www/error`; Frappe's own `get_context` decides the message and
whether a traceback may be shown (only where Frappe allows it, never to a normal visitor)."""

import frappe
from frappe import _
from frappe.www.error import get_context as frappe_error_context

from nxerp import public_site

no_cache = 1


def get_context(context):
	extra = frappe_error_context(context) or {}
	context.update(extra)
	title = context.get("title") or _("Server Error")
	public_site.base_context(context, title=title, description="")
	context.product = public_site.platform_hero()
	context.state_heading = title
	context.state_text = context.get("message") or _("There was an error building this page")
	context.state_code = context.get("http_status_code")
	context.state_details = context.get("error") or ""
	context.state_href, context.state_label = "/", _("Back to Home")
	return context
