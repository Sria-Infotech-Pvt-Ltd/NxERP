import frappe

BRAND = "NXERP"
LOGO = "/assets/nxerp/images/nxerp-wordmark.png"
FAVICON = "/assets/nxerp/images/nxerp-favicon.png"


def apply_branding():
    """Set the NXERP name/logo in site settings. Idempotent and safe to re-run.

    Runs after install; for an existing site use:
        bench --site <site> execute nxerp.branding.apply_branding
    """
    frappe.db.set_single_value("Website Settings", "app_name", BRAND)
    frappe.db.set_default("site_name", BRAND)

    # Same fields Helpdesk's onboarding writes; logos only if nobody set one.
    if frappe.db.exists("DocType", "HD Settings"):
        frappe.db.set_single_value("HD Settings", "brand_name", BRAND)
        if not frappe.db.get_single_value("HD Settings", "brand_logo"):
            frappe.db.set_single_value("HD Settings", "brand_logo", LOGO)
        if not frappe.db.get_single_value("HD Settings", "favicon"):
            frappe.db.set_single_value("HD Settings", "favicon", FAVICON)

    frappe.clear_cache()
