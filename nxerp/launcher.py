"""Corrects the app tiles Frappe builds on its own, so every "Apps" menu agrees with the launcher.

Frappe builds tiles from each app's `add_to_apps_screen` hook and, because hooks only append, no app can
hide or rename another's tile. Research part 1 found the resulting problems: ERPNext's tile shows for any
system user, Helpdesk's tile was titled "NXERP", and the Framework/Desk entry leaks into menus. Two
supported extension points fix this without editing any upstream file:

- `override_whitelisted_methods` for `frappe.apps.get_apps` (used by the Helpdesk SPA's "Apps" menu):
  returns the registry's authorised apps with their correct identities.
- `extend_bootinfo` (Desk's own switcher reads `boot.app_data`): authorised registry apps keep a slot with
  the registry's identity; everything else (Frappe, payments, telephony, unauthorised apps) is hidden.
  It also adds `boot.nxerp` and, for multi-app users only, an "All applications" row to Desk's user menu.

Display only. The enforcement layer decides access; hiding a tile is never the control.
"""

import frappe

from nxerp import access, registry

LAUNCHER_LABEL = "All applications"

# Desk's user menu reads `Navbar Settings.settings_dropdown`, which Frappe assigns to the boot AFTER the
# `extend_bootinfo` hooks run, so a hook cannot add a row per user. A standard navbar item can: it is synced
# into that table on migrate and carries a condition Desk evaluates in the browser every time the menu opens.
# The row therefore shows only to a multi-app user (boot.nxerp.launcher is set only for them).
LAUNCHER_NAVBAR_ITEM = {
	"item_label": LAUNCHER_LABEL,
	"item_type": "Route",
	"route": "/nxerp/apps",
	"icon": "layout-grid",
	"is_standard": 1,
	"condition": "frappe.boot.nxerp && frappe.boot.nxerp.launcher",
}


def _tiles(user: str) -> list:
	return [
		{"name": e.key, "title": e.title, "logo": e.logo, "route": e.route, "setup_wizard_text": None}
		for e in access.get_user_apps(user)
	]


@frappe.whitelist()
def get_apps() -> list:
	"""Drop-in for `frappe.apps.get_apps`: the apps the caller may use, with correct identities."""
	return _tiles(frappe.session.user)


def extend_bootinfo(bootinfo):
	"""Registered under `extend_bootinfo`. Runs for every desk and website boot."""
	user = frappe.session.user
	if user == "Guest":
		return

	apps = access.get_user_apps(user)
	by_package = {}
	for entry in registry.installed_entries():
		for package in entry.owns:
			by_package[package] = entry
	allowed = {e.key for e in apps}

	for row in bootinfo.get("app_data") or []:
		entry = by_package.get(row.get("app_name"))
		if entry and entry.key in allowed and row.get("app_name") == entry.app:
			row.update(
				on_apps_screen=True,
				app_title=entry.title,
				app_logo_url=entry.logo,
			)
		else:
			row["on_apps_screen"] = False  # Framework, companions and apps the user does not hold

	bootinfo.nxerp = {
		"apps": [{"key": e.key, "title": e.title, "route": e.route} for e in apps],
		"launcher": "/nxerp/apps" if len(apps) > 1 else None,
	}
