"""Creates the role "NXERP Command Caller": the one role of the service user another app uses to call the command API. Idempotent."""

import frappe

ROLE = "NXERP Command Caller"


def execute():
	if frappe.db.exists("Role", ROLE):
		return
	frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0, "is_custom": 1}).insert(ignore_permissions=True)
