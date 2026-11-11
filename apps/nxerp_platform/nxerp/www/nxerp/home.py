"""The public Home page: "/" for a guest (see `nxerp.public_site.website_user_home_page`) and /nxerp/home for anyone.

Read-only. Lists the installed products from the registry; creates nothing and grants nothing.
"""

import frappe
from frappe import _

from nxerp import public_site

no_cache = True  # the header and the product buttons differ for a signed-in visitor


def get_context(context):
	public_site.base_context(
		context,
		title=_("{0}: one sign-in for your business applications").format(public_site.branding.PLATFORM_NAME),
		description=_("One sign-in and one place for the business applications your team uses."),
		active="home",
		canonical=frappe.utils.get_url("/"),
	)
	context.products = public_site.products()
