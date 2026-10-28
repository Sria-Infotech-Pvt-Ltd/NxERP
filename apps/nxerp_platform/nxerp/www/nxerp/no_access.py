import frappe

from nxerp import access

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
