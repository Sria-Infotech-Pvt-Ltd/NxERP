import os

import frappe

from nxerp import access, registry

no_cache = True


def get_context(context):
	"""Plain denial page. It names no application the user lacks and shows no data."""
	context.no_header = True
	context.show_sidebar = False
	context.title = frappe._("No access")
	context.is_guest = frappe.session.user == "Guest"
	# A platform administrator who lands here (typically the person who just finished the setup wizard) is told
	# where access is granted. Everyone else sees nothing about administration.
	context.can_administer = not context.is_guest and access.is_platform_admin(frappe.session.user)

	# "Request access" only for a signed-in person, and only for the one application the gate named in `?app=`. The
	# link carries that key and nothing else: no list of other applications, no role name.
	key = frappe.form_dict.get("app")
	entry = registry.get_entry(key) if isinstance(key, str) else None
	context.request_href = f"/welcome/{entry.key}" if entry and not context.is_guest else None
	try:
		context.site_css_version = int(
			os.path.getmtime(frappe.get_app_path("nxerp", "public", "css", "nxerp-site.css"))
		)
	except OSError:
		context.site_css_version = 1
