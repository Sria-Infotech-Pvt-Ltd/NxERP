"""Information pages (/platform, /security, /solutions, /roadmap, /company, /partners, /get-in-touch): static content from
`nxerp.public_catalog`, one template. Read-only and public. The route rule's `defaults` carry the slug."""

import frappe
from frappe import _

from nxerp import public_catalog, public_site

no_cache = True


def get_context(context):
	slug = frappe.form_dict.get("slug")
	page = public_catalog.PAGES.get(slug) if isinstance(slug, str) else None
	if not page:
		raise frappe.PageDoesNotExistError
	public_site.base_context(
		context,
		title=f"{page['title']} | {public_site.branding.PLATFORM_NAME}",
		description=page["lead"],
		active=slug,
	)
	context.page = page
	context.slug = slug
	context.icons = public_catalog.ICONS
