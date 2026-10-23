app_name = "nxerp"
app_title = "NXERP"
app_publisher = "NXERP"
app_description = "NXERP"
app_license = "mit"

# Brand logo used by Frappe wherever it asks for the app logo (login page, navbar).
app_logo_url = "/assets/nxerp/images/nxerp-wordmark.png"

# Website context: browser tab icon and splash image.
website_context = {
    "favicon": "/assets/nxerp/images/nxerp-favicon.png",
    "splash_image": "/assets/nxerp/images/nxerp-mark.png",
}

# Frappe's required-app installer ensures the NXERP app (and its /login route)
# is registered only after ERPNext and Helpdesk.
required_apps = ["erpnext", "helpdesk"]

# Brings Frappe Desk (/app) onto the NXERP palette. Generated from the helpdesk
# design tokens: run "yarn theme:build" in helpdesk/desk to refresh it.
app_include_css = ["/assets/nxerp/css/nxerp-desk-theme.css"]

# Applies the NXERP name on a fresh install. For an existing site run:
#   bench --site <site> execute nxerp.branding.apply_branding
after_install = "nxerp.branding.apply_branding"

# The /login page is overridden by nxerp/www/login.html (+ login.py).
# Frappe serves the www page of the app installed last, so nxerp must be
# installed after frappe (and after helpdesk) - the normal order.
