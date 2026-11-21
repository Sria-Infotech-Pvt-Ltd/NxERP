"""Creates the access roles named in the registry. Idempotent; safe to run on every migrate."""

import frappe

from nxerp import registry


def ensure_access_roles():
	"""One role per installed registry app. desk_access is off: holding an access role must not turn a
	website user into a system user, and must not change anyone's user type."""
	# an identity site holds the access role of EVERY app it can grant (the apps are not installed there); an app site only its own
	entries = (
		[e for e in registry.get_registry() if not e.test_only]
		if registry.site_role() == "identity"
		else registry.installed_entries()
	)
	for entry in entries:
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


def ensure_feed_role():
	"""The service role the shared-entity feed API requires (nxerp/shared/feed.py). No desk access: it is held by a
	service user that authenticates with an API key and secret, never by a person. Idempotent."""
	from nxerp.shared.outbox import FEED_ROLE

	if frappe.db.exists("Role", FEED_ROLE):
		return
	frappe.get_doc({"doctype": "Role", "role_name": FEED_ROLE, "desk_access": 0, "is_custom": 1}).insert(
		ignore_permissions=True
	)


def ensure_platform_settings():
	"""Own the post-login landing. Helpdesk's install sets `Portal Settings.default_portal_home` to
	/helpdesk, which sent every user without a role home page to Helpdesk. Point it at the router unless an
	administrator chose something else."""
	current = frappe.db.get_single_value("Portal Settings", "default_portal_home")
	if current in (None, "", "/helpdesk", "helpdesk"):
		frappe.db.set_single_value("Portal Settings", "default_portal_home", "/nxerp/go")


def open_signup():
	"""Self-signup is open to anyone: make sure Frappe's own Website Settings `disable_signup` is 0. Run once on install and once on existing
	sites (patch `open_signup_for_everyone`), never on every migrate, so an administrator who ticks "Disable Customer Signup" later is not
	overruled. Idempotent. The old operator switch is gone: docs/features/signup-gate.md."""
	if frappe.utils.cint(frappe.db.get_single_value("Website Settings", "disable_signup")):
		frappe.db.set_single_value("Website Settings", "disable_signup", 0)


def ensure_navbar_items():
	"""Sync the standard navbar items (the "All applications" row) now; Frappe otherwise does it only on migrate."""
	from frappe.core.doctype.navbar_settings.navbar_settings import sync_standard_items

	sync_standard_items()


def after_install():
	ensure_access_roles()
	ensure_feed_role()
	ensure_platform_settings()
	ensure_navbar_items()
	open_signup()


def after_migrate():
	ensure_access_roles()
	ensure_feed_role()
	ensure_platform_settings()
