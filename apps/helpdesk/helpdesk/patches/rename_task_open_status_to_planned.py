import frappe


def execute():
    """HD Task's initial status was renamed from Open to Planned; Select validation
    would otherwise reject every save of an existing task still stored as Open."""
    if not frappe.db.table_exists("HD Task"):
        return
    frappe.db.set_value(
        "HD Task", {"status": "Open"}, "status", "Planned", update_modified=False
    )
