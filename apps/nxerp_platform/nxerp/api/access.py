"""Whitelisted access-management API. System Manager only, except `get_my_access`.

Grants are Frappe roles (ADR-003), so these methods only add or remove the app's access role through
a normal `User.save()`. That keeps one audit trail (Frappe's Version log on User, `track_changes`),
runs the lockout guard in `nxerp.guard`, and clears Frappe's role cache so revocation is immediate.

The methods accept only (user, app_key, grant): nothing else about a user can be set through them,
so there is nothing to mass-assign.
"""

import frappe
from frappe import _

from nxerp import access, registry


def _require_platform_admin():
	if not access.is_platform_admin(frappe.session.user):
		frappe.throw(_("Only a System Manager can manage application access"), frappe.PermissionError)


def _target_user(user: str):
	if not isinstance(user, str) or not frappe.db.exists("User", user):
		frappe.throw(_("User not found"), frappe.DoesNotExistError)
	if user in ("Administrator", "Guest"):
		frappe.throw(_("Administrator always has access; Guest never does"), frappe.ValidationError)
	return frappe.get_doc("User", user)


def _entry(app_key: str):
	entry = registry.get_entry(app_key) if isinstance(app_key, str) else None
	if not entry:
		frappe.throw(_("Unknown or uninstalled application"), frappe.ValidationError)
	return entry


@frappe.whitelist()
def get_my_access() -> dict:
	"""The caller's own landing and apps. Used by the launcher (Phase 3)."""
	return access.resolve_landing(frappe.session.user)


@frappe.whitelist()
def get_user_access(user: str) -> dict:
	_require_platform_admin()
	return {
		"user": user,
		"apps": [e.key for e in access.get_user_apps(user)],
		"portal": [e.key for e in registry.installed_entries() if access.can_use_portal(user, e.key)],
	}


@frappe.whitelist(methods=["POST"])
def set_app_access(user: str, app_key: str, grant: int = 1) -> dict:
	"""Grant (`grant`=1) or revoke (`grant`=0) staff access to an app. Returns the user's new apps."""
	_require_platform_admin()
	entry = _entry(app_key)
	doc = _target_user(user)
	grant = frappe.utils.cint(grant)

	held = {row.role: row for row in doc.roles}
	if grant and entry.access_role not in held:
		doc.append("roles", {"role": entry.access_role})
	elif not grant:
		# revoke every role that confers this app, not only the explicit one
		doc.roles = [row for row in doc.roles if row.role not in entry.grant_roles]

	# always write the audit trail: Frappe skips Version records when `in_test` unless asked
	doc.save(ignore_version=False)
	return get_user_access(user)
