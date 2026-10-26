app_name = "nxerp"
app_title = "NXERP"
app_publisher = "Sria Infotech Pvt Ltd"
app_description = "NXERP platform app: shared enterprise shell for ERPNext, Helpdesk and future apps"
app_email = "devops@example.test"
app_license = "Proprietary"  # placeholder: owner to confirm the licence (see docs/PROGRESS.md)

# Phase 1 is scaffolding plus shared branding assets. This app registers NO behaviour yet: no
# launcher tile, no login override, no redirects, no permission hooks. Each of those arrives
# in its own reviewed change (see docs/PROGRESS.md, Phase 2) and must be listed here with
# its owner.

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

# before_install = "nxerp.install.before_install"
# after_install = "nxerp.install.after_install"

# Request lifecycle
# ------------------

# before_request = ["nxerp.access.before_request"]
# on_session_creation = ["nxerp.access.on_session_creation"]
# website_route_rules = []
