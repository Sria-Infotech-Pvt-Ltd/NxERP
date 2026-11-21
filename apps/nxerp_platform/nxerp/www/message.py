"""/message: Frappe's generic message page ("not permitted", "link expired", "verified"...) in the NXDESK look.

Overrides `frappe/www/message` (an app's www folder wins over Frappe's). The content comes from Frappe's own `get_context`, so every
message, title, status code and button it would show is still shown; only the page around it changes."""

from frappe import _
from frappe.www.message import get_context as frappe_message_context

from nxerp import public_site

no_cache = 1


def get_context(context):
	context.update(frappe_message_context(context) or {})
	title = context.get("title") or _("Message")
	public_site.base_context(context, title=title, description="")
	context.product = public_site.platform_hero()
	context.state_heading = title
	context.state_text = context.get("message") or ""
	context.state_code = context.get("error_code")
	if context.get("primary_action"):
		context.state_href, context.state_label = (
			context.primary_action,
			context.get("primary_label") or _("Home"),
		)
	else:
		context.state_href, context.state_label = "/", _("Home")
	return context
