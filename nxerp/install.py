"""Creates the access roles named in the registry. Idempotent; safe to run on every migrate."""

import frappe

from nxerp import registry


def ensure_access_roles():
	"""One role per installed registry app. desk_access is off: holding an access role must not turn a
	website user into a system user, and must not change anyone's user type."""
	for entry in registry.installed_entries():
		if frappe.db.exists("Role", entry.access_role):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": entry.access_role,
				"desk_access": 0,
				"is_custom": 1,
			}
		).insert(ignore_permissions=True)


def ensure_platform_settings():
	"""Own the post-login landing. Helpdesk's install sets `Portal Settings.default_portal_home` to
	/helpdesk, which sent every user without a role home page to Helpdesk. Point it at the router unless an
	administrator chose something else."""
	current = frappe.db.get_single_value("Portal Settings", "default_portal_home")
	if current in (None, "", "/helpdesk", "helpdesk"):
		frappe.db.set_single_value("Portal Settings", "default_portal_home", "/nxerp/go")


def after_install():
	ensure_access_roles()
	ensure_platform_settings()


def after_migrate():
	ensure_access_roles()
	ensure_platform_settings()
