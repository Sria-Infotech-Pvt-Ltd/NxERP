"""/nxerp/go: the post-login router. No page of its own: it always redirects.

GET only. `redirect-to` is honoured only if it is a safe same-origin path owned by an app the user may use
(nxerp.routing); anything else falls back to the user's landing. Never renders an error or names an app.
"""

import frappe

from nxerp import routing

no_cache = True


def get_context(context):
	user = frappe.session.user
	location = routing.route(user, frappe.form_dict.get("redirect-to"))
	frappe.local.flags.redirect_location = location
	raise frappe.Redirect
