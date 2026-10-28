"""Protections around who may change app grants, and around the last administrator.

Wired as `doc_events` on User. Three rules:

1. Only a platform administrator (Administrator or System Manager) may add or remove an NXERP access
   role on a user. Without this, anyone who can edit a User record (including their own, through a
   mass-assigned form) could grant themselves an app.
2. The last named System Manager can never lose the role, be disabled or be deleted. Administrator is
   the reserved superuser, always present, and is never counted as a named administrator.
3. Administrator cannot be disabled.

All three raise `frappe.PermissionError`; none of them can be skipped by an API caller (they run on
every `User.save()`), only by code that deliberately passes `frappe.flags.in_patch`/`in_install`.
"""

import frappe
from frappe import _

from nxerp import access, registry


def _access_roles() -> set:
	roles = set()
	for entry in registry.get_registry():
		roles.add(entry.access_role)
	return roles


def _roles_of(doc) -> set:
	return {row.role for row in (doc.get("roles") or [])}


def _before_roles(doc) -> set:
	before = doc.get_doc_before_save()
	return _roles_of(before) if before else set()


def _named_admins(exclude: str | None = None) -> list:
	"""Enabled System Users holding System Manager, other than Administrator and `exclude`."""
	users = frappe.get_all(
		"Has Role",
		filters={"role": access.PLATFORM_ADMIN_ROLE, "parenttype": "User"},
		pluck="parent",
	)
	result = []
	for name in set(users):
		if name in ("Administrator", exclude):
			continue
		enabled, user_type = frappe.db.get_value("User", name, ["enabled", "user_type"])
		if enabled and user_type == "System User":
			result.append(name)
	return result


def _skip() -> bool:
	return bool(frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate)


def validate_user(doc, method=None):
	if _skip():
		return

	if doc.name == "Administrator" and not doc.enabled:
		frappe.throw(_("Administrator cannot be disabled"), frappe.PermissionError)

	# rule 1: grant changes need a platform administrator
	grants = _access_roles()
	changed = (_roles_of(doc) ^ _before_roles(doc)) & grants
	if changed and not access.is_platform_admin(frappe.session.user):
		frappe.throw(_("Only a System Manager can change application access"), frappe.PermissionError)

	# rule 2: the last named administrator keeps the role and stays enabled
	before = doc.get_doc_before_save()
	if before and access.PLATFORM_ADMIN_ROLE in _roles_of(before) and before.enabled:
		still_admin = (
			access.PLATFORM_ADMIN_ROLE in _roles_of(doc) and doc.enabled and doc.user_type == "System User"
		)
		if not still_admin and not _named_admins(exclude=doc.name):
			frappe.throw(_("The last System Manager cannot be removed or disabled"), frappe.PermissionError)


def on_trash_user(doc, method=None):
	"""Block deleting the last named System Manager.

	Read the persisted state, not `doc`: Frappe's own `User.on_trash` runs first and sets
	`doc.enabled = 0` in memory, which would make every user look already disabled here.
	"""
	if _skip():
		return
	enabled = frappe.db.get_value("User", doc.name, "enabled")
	roles = frappe.get_all("Has Role", filters={"parent": doc.name, "parenttype": "User"}, pluck="role")
	if enabled and access.PLATFORM_ADMIN_ROLE in roles and not _named_admins(exclude=doc.name):
		frappe.throw(_("The last System Manager cannot be deleted"), frappe.PermissionError)
