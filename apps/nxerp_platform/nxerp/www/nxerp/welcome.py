"""/welcome/<key>: the first-run wizard and the pending view (split shell). Signed-in only. The page renders the
saved state; every change goes through `nxerp.api.onboarding`, which works on the session user alone."""

import frappe
from frappe import _

from nxerp import onboarding, public_site, registry

no_cache = True


def get_context(context):
	key = frappe.form_dict.get("key")
	entry = registry.public_entry(key) if isinstance(key, str) else None
	if not entry:
		raise frappe.PageDoesNotExistError
	user = frappe.session.user
	if user == "Guest":
		public_site.redirect(
			f"{public_site.LOGIN_ROUTE}?redirect-to={frappe.utils.quote(f'/welcome/{entry.key}', safe='/')}"
		)

	state = onboarding.get_state(user, entry.key)
	if state["status"] == "granted":
		public_site.redirect(
			f"{public_site.ROUTER_ROUTE}?redirect-to={frappe.utils.quote(entry.route, safe='/')}"
		)

	product = public_site.present(entry)
	public_site.base_context(
		context, title=_("Welcome | {0}").format(product["title"]), description=product["tagline"]
	)
	context.product = product
	context.state = state
	context.options = onboarding.options()
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.step_labels = {
		"basics": _("Language and time zone"),
		"about": _("About your work"),
		"request": _("Review and send"),
	}
