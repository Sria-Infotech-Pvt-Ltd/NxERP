import frappe

BRAND = "NXERP"
ASSETS = "/assets/helpdesk/nxerp_login/images"
LOGO = f"{ASSETS}/nxerp-wordmark.png"  # wide logo: login, desk, website
MARK = f"{ASSETS}/nxerp-mark.png"  # square mark: the app's small sidebar slot
FAVICON = f"{ASSETS}/nxerp-favicon.png"
HIDE_FROM_HELP_MENU = ("About", "Frappe Support")  # they show another vendor's name


def apply_branding():
    """Set the NXERP name, logos and Help menu in site settings, printing the old values.

    Run by hand: bench --site <site> execute helpdesk.nxerp_branding.apply_branding
    """
    changes = {
        "HD Settings": {"brand_name": BRAND, "brand_logo": MARK, "favicon": FAVICON},
        "Website Settings": {
            "app_name": BRAND,
            "app_logo": LOGO,
            "favicon": FAVICON,
            "splash_image": LOGO,
        },
        "Navbar Settings": {"app_logo": LOGO},
        "System Settings": {"app_name": BRAND},
    }
    for doctype, values in changes.items():
        for fieldname, value in values.items():
            old = frappe.db.get_single_value(doctype, fieldname)
            frappe.db.set_single_value(doctype, fieldname, value)
            print(f"{doctype}.{fieldname}: {old!r} -> {value!r}")
    brand_help_menu()
    frappe.clear_cache()


def brand_help_menu():
    """Hide the Help items that name another vendor and add an "IT Support" entry."""
    from helpdesk.www.login import _support_url

    doc = frappe.get_doc("Navbar Settings")
    for row in doc.help_dropdown:
        if row.item_label in HIDE_FROM_HELP_MENU and not row.hidden:
            row.hidden = 1
            print(f"Navbar Settings help item hidden: {row.item_label!r}")
    if not any(row.item_label == "IT Support" for row in doc.help_dropdown):
        doc.append(
            "help_dropdown",
            {"item_label": "IT Support", "item_type": "Route", "route": _support_url(), "is_standard": 0},
        )
        print("Navbar Settings help item added: 'IT Support'")
    doc.save(ignore_permissions=True)
