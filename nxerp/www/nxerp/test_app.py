"""/nxerp/test-app: a stand-in page for the TEST-ONLY third app (`nxerp_test_apps` site config).

It exists only so end-to-end tests have somewhere for a third launcher tile to lead. It answers 404 unless
the site has `allow_tests` on (a production site never does), and then still requires the app grant.
"""

import frappe

from nxerp import access, registry

no_cache = True


def get_context(context):
	if not frappe.conf.get("allow_tests"):
		raise frappe.DoesNotExistError

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/nxerp/go"
		raise frappe.Redirect

	entry = next(
		(e for e in registry.installed_entries() if e.test_only and e.route == "/nxerp/test-app"), None
	)
	if not entry or not access.can_access_app(frappe.session.user, entry.key):
		frappe.local.flags.redirect_location = access.NO_ACCESS_ROUTE
		raise frappe.Redirect

	context.no_header = True
	context.title = entry.title
