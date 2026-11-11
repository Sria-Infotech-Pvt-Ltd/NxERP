"""/products/<key>: one installed product. An unknown or uninstalled key is the same 404 as any unknown page."""

import frappe
from frappe import _

from nxerp import public_site

no_cache = True


def get_context(context):
	item = public_site.product(frappe.form_dict.get("key"))
	if not item:
		raise frappe.PageDoesNotExistError

	public_site.base_context(
		context,
		title=_("{0} | {1}").format(item["title"], public_site.branding.PLATFORM_NAME),
		description=item["tagline"],
		active="products",
		canonical=frappe.utils.get_url(item["page_href"]),
	)
	context.product = item
