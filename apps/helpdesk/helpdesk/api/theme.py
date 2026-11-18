import frappe
from frappe import _

DESK_THEMES = ("Light", "Dark", "Automatic")


@frappe.whitelist(methods=["POST"])
def set_desk_theme(theme: str):
    if theme not in DESK_THEMES:
        frappe.throw(_("Theme must be one of: {0}").format(", ".join(DESK_THEMES)))

    if frappe.session.user == "Guest":
        return

    frappe.db.set_value(
        "User", frappe.session.user, "desk_theme", theme, update_modified=False
    )
    frappe.clear_cache(user=frappe.session.user)
