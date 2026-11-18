"""/get-started?product=<key>: where "Get started" leads. A guest sees the page; everyone else is sent on by
`routing.get_started_target`. Unknown or uninstalled product: the same 404 as any page."""

import frappe
from frappe import _

from nxerp import access, onboarding, public_site, registry, routing

no_cache = True


def get_context(context):
	key = frappe.form_dict.get("product")
	if not key:
		public_site.redirect(public_site.PRODUCTS_ROUTE)
	entry = registry.public_entry(key) if isinstance(key, str) else None
	if not entry:
		raise frappe.PageDoesNotExistError

	user = frappe.session.user
	_view, location = routing.get_started_target(
		user,
		entry,
		has_app=user != "Guest" and access.can_reach_app(user, entry.key),
		has_pending=user != "Guest" and bool(onboarding.open_request(user, entry.key)),
	)
	if location:
		public_site.redirect(location)

	product = public_site.present(entry)
	public_site.base_context(
		context,
		title=_("Get started with {0} | {1}").format(product["title"], public_site.branding.PLATFORM_NAME),
		description=product["tagline"],
		active="products",
	)
	context.product = product
