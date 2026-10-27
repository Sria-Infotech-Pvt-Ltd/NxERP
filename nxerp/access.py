"""The access resolver: the single source of truth for "which apps may this user use".

Model (ADR-003, amendment 1): grants are Frappe roles. A user has staff access to an app when they
hold the app's access role (or one of its implied roles). Nothing is stored here and nothing is
cached here: every answer is derived from `frappe.get_roles`, which Frappe caches per user and
clears on every User save. So a revocation takes effect on the next request, with no re-login
(proved in tests/test_access_resolver.py). If roles are changed by raw SQL, the delay is bounded by
Frappe's own role cache until `frappe.clear_cache(user=...)`.

What this does NOT decide: DocType, field and record permissions. Those stay Frappe's. This layer
only adds an app-level gate and never relaxes anything.
"""

import frappe

from nxerp import registry

NO_ACCESS_ROUTE = "/nxerp/no-access"
LAUNCHER_ROUTE = "/nxerp/apps"
LOGIN_ROUTE = "/login"

PLATFORM_ADMIN_ROLE = "System Manager"


def _user_state(user: str) -> tuple:
	"""(enabled, user_type) for a real user; (False, None) otherwise."""
	if not user or user == "Guest":
		return False, None
	row = frappe.get_cached_value("User", user, ["enabled", "user_type"], as_dict=True)
	if not row:
		return False, None
	return bool(row.enabled), row.user_type


def is_enabled(user: str | None = None) -> bool:
	"""True for a real, enabled account. Administrator is always enabled; Guest is not an account."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return _user_state(user)[0]


def _roles(user: str) -> set:
	return set(frappe.get_roles(user))


def is_platform_admin(user: str | None = None) -> bool:
	"""Administrator, or an enabled System User holding System Manager. Never locked out by grants."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	enabled, user_type = _user_state(user)
	return enabled and user_type == "System User" and PLATFORM_ADMIN_ROLE in _roles(user)


def get_user_apps(user: str | None = None) -> list:
	"""Entries of installed apps the user has STAFF access to, in launcher order."""
	user = user or frappe.session.user
	entries = registry.installed_entries()

	if user == "Administrator":
		return entries

	enabled, user_type = _user_state(user)
	# customers and other website users never hold staff access, whatever roles they carry
	if not enabled or user_type != "System User":
		return []

	roles = _roles(user)
	return [e for e in entries if e.grant_roles & roles]


def can_access_app(user: str | None, app_key: str) -> bool:
	"""True when the user has staff access to the app. Unknown or uninstalled apps are False."""
	user = user or frappe.session.user
	return any(e.key == app_key for e in get_user_apps(user))


def can_use_portal(user: str | None, app_key: str) -> bool:
	"""True when the user may use the app's customer-facing surface (portal roles).

	Portal use is not staff access: it never appears in the launcher and never opens Desk.
	Frappe's DocType and record permissions still decide what the portal user can read.
	"""
	user = user or frappe.session.user
	entry = registry.get_entry(app_key)
	if not entry or not entry.portal_roles:
		return False
	enabled, _ = _user_state(user)
	if not enabled:
		return False
	return bool(set(entry.portal_roles) & _roles(user))


def is_portal_only(user: str | None = None) -> bool:
	"""An enabled user with no staff app who holds a portal role, e.g. a customer.

	Such users get the app's customer-facing surface and nothing else, so extra data minimisation applies
	to them (nxerp.enforcement: no document-info endpoints, assignment metadata stripped from responses).
	"""
	user = user or frappe.session.user
	if user in ("Guest", "Administrator") or not is_enabled(user) or is_platform_admin(user):
		return False
	if get_user_apps(user):
		return False
	return any(can_use_portal(user, e.key) for e in registry.installed_entries())


def can_reach_app(user: str | None, app_key: str) -> bool:
	"""Staff access or portal use. This is what the data gate checks for owned DocTypes and methods."""
	user = user or frappe.session.user
	return can_access_app(user, app_key) or can_use_portal(user, app_key)


def resolve_landing(user: str | None = None) -> dict:
	"""Where the user should go after login: {mode: none | direct | launcher, destination, apps}.

	Routing only. It is never the security boundary: the enforcement layer re-checks on the server.
	"""
	user = user or frappe.session.user

	if not user or user == "Guest":
		return {"mode": "none", "destination": LOGIN_ROUTE, "apps": []}

	apps = get_user_apps(user)
	summary = [{"key": e.key, "title": e.title, "route": e.route, "logo": e.logo} for e in apps]

	if len(apps) > 1:
		return {"mode": "launcher", "destination": LAUNCHER_ROUTE, "apps": summary}
	if len(apps) == 1:
		return {"mode": "direct", "destination": apps[0].route, "apps": summary}

	# no staff apps: a portal-only user (customer) goes straight to the customer-facing surface
	for entry in registry.installed_entries():
		if entry.portal_route and can_use_portal(user, entry.key):
			return {"mode": "direct", "destination": entry.portal_route, "apps": []}

	return {"mode": "none", "destination": NO_ACCESS_ROUTE, "apps": []}
