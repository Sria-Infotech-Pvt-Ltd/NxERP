"""Creates the role "NXERP Provisioner": the one role of the service user that receives grants from the identity site. Idempotent."""

import frappe

ROLE = "NXERP Provisioner"


def execute():
	if frappe.db.exists("Role", ROLE):
		return
	frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0, "is_custom": 1}).insert(
		ignore_permissions=True
	)
