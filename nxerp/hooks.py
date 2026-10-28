app_name = "nxerp"
app_title = "NXERP"
app_publisher = "Sria Infotech Pvt Ltd"
app_description = "NXERP platform app: shared enterprise shell for ERPNext, Helpdesk and future apps"
app_email = "devops@example.test"
app_license = "Proprietary"  # placeholder: owner to confirm the licence (see docs/PROGRESS.md)

# Phase 2: the access layer (registry, resolver, server-side enforcement).
# Phase 3: the unified experience: the one /login (www/login), the post-login router (www/nxerp/go),
# the launcher (www/nxerp/apps) and the corrected app tiles (launcher.py). All routes are documented in
# docs/architecture/routes.md.

# Apps
# ------------------

# Deliberately empty (ADR-005): the platform must not require ERPNext, Helpdesk or any
# future app. Install order is owned by deploy/apps.json, not by this app.
required_apps = []

# add_to_apps_screen = []

# Platform branding for Desk and website pages (login splash, favicon). nxerp installs last, so these win
# over any app's own value; Helpdesk keeps its own identity inside its SPA.
app_logo_url = "/assets/nxerp/nxerp_login/images/nxerp-wordmark.png"
website_context = {
	"favicon": "/assets/nxerp/nxerp_login/images/nxerp-favicon.png",
	"splash_image": "/assets/nxerp/nxerp_login/images/nxerp-wordmark.png",
}

# Includes in <head>
# ------------------

# Palette for Frappe Desk (ERPNext, Framework). Generated from the token source in the Helpdesk
# repo (desk/src/theme, `yarn theme:build`); never edit the CSS by hand.
app_include_css = "/assets/nxerp/css/nxerp-desk-theme.css"
# app_include_js = "/assets/nxerp/js/nxerp.js"

# Installation
# ------------

after_install = "nxerp.install.after_install"
after_migrate = "nxerp.install.after_migrate"

# Access layer (ADR-003): an app-level gate that only ever DENIES, on top of Frappe's permissions.
# ------------------------------------------------------------------------------------------

# every request, after the session is known and before dispatch
auth_hooks = ["nxerp.enforcement.auth_hook"]

# remove assignment and comment metadata from API responses to portal-only users (customers)
after_request = ["nxerp.enforcement.after_request", "nxerp.routing.after_request"]

# document level (files, print, realtime rooms, check_permission) and list level (get_list, reports)
has_permission = {"*": ["nxerp.enforcement.has_permission"]}
permission_query_conditions = {"*": ["nxerp.enforcement.permission_query_conditions"]}

# Unified experience (ADR-004): one login, one router, one launcher.
# ------------------------------------------------------------------

# every login response and every "home page" lookup points at the post-login router
on_session_creation = ["nxerp.routing.on_session_creation"]

# every "Apps" menu shows the same authorised apps with their correct identities
override_whitelisted_methods = {"frappe.apps.get_apps": "nxerp.launcher.get_apps"}
extend_bootinfo = ["nxerp.launcher.extend_bootinfo"]
# the "All applications" row of Desk's user menu (shown only to multi-app users, see nxerp/launcher.py)
standard_navbar_items = [
	{
		"item_label": "All applications",
		"item_type": "Route",
		"route": "/nxerp/apps",
		"icon": "layout-grid",
		"is_standard": 1,
		"condition": "frappe.boot.nxerp && frappe.boot.nxerp.launcher",
	}
]

# /login/<anything> (a client-side redirect quirk) is just /login
website_redirects = [{"source": "/login/.+", "target": "/login"}]

# who may change grants, and the last-administrator guard
doc_events = {
	"User": {
		"validate": "nxerp.guard.validate_user",
		"on_trash": "nxerp.guard.on_trash_user",
	}
}
