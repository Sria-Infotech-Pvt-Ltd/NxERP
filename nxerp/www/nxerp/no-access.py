import frappe

no_cache = True


def get_context(context):
	"""Plain denial page. It names no application the user lacks and shows no data."""
	context.no_header = True
	context.show_sidebar = False
	context.title = frappe._("No access")
	context.is_guest = frappe.session.user == "Guest"
