app_name = "nxerp"
app_title = "NXERP"
app_publisher = "Sria Infotech Pvt Ltd"
app_description = "NXERP platform app: shared enterprise shell for ERPNext, Helpdesk and future apps"
app_email = "devops@example.test"
app_license = "Proprietary"  # placeholder: owner to confirm the licence (see docs/PROGRESS.md)

# Phase 2 adds the access layer (registry, resolver, server-side enforcement). There is still no
# launcher tile, login override or post-login redirect: those are Phase 3 and are listed here when
# they arrive, with their owner.

# Apps
# ------------------

# Deliberately empty (ADR-005): the platform must not require ERPNext, Helpdesk or any
# future app. Install order is owned by deploy/apps.json, not by this app.
required_apps = []

# add_to_apps_screen = []

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
after_request = ["nxerp.enforcement.after_request"]

# document level (files, print, realtime rooms, check_permission) and list level (get_list, reports)
has_permission = {"*": ["nxerp.enforcement.has_permission"]}
permission_query_conditions = {"*": ["nxerp.enforcement.permission_query_conditions"]}

# who may change grants, and the last-administrator guard
doc_events = {
	"User": {
		"validate": "nxerp.guard.validate_user",
		"on_trash": "nxerp.guard.on_trash_user",
	}
}
