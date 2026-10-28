"""/nxerp/apps: the launcher. Lists ONLY the apps the signed-in user may use.

Guests go to /login. A user with fewer than two apps has no use for a launcher and is sent where the
router would send them. The list comes from `nxerp.routing.landing_for` (which wraps
`nxerp.access.resolve_landing`), the same source as the router and the gate, so what is shown always
matches what is enforced.
"""

import frappe
from frappe import _

from nxerp import routing

no_cache = True


def get_context(context):
	user = frappe.session.user
	if user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + routing.ROUTER_ROUTE
		raise frappe.Redirect

	landing = routing.landing_for(user)
	if landing["mode"] != "launcher":
		frappe.local.flags.redirect_location = landing["destination"]
		raise frappe.Redirect

	context.no_header = True
	context.show_sidebar = False
	context.title = _("Applications")
	context.apps = landing["apps"]
	context.full_name = frappe.utils.get_fullname(user)
