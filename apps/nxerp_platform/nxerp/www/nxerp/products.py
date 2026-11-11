"""/products: the installed products, grouped by category. Read-only and public."""

import frappe
from frappe import _

from nxerp import public_site

no_cache = True  # "Open application" replaces "Learn more" for a product the signed-in visitor holds


def get_context(context):
	public_site.base_context(
		context,
		title=_("Products | {0}").format(public_site.branding.PLATFORM_NAME),
		description=_("The applications available on {0}, all behind one sign-in.").format(
			public_site.branding.PLATFORM_NAME
		),
		active="products",
		canonical=frappe.utils.get_url(public_site.PRODUCTS_ROUTE),
	)
	context.categories = public_site.products_by_category()
