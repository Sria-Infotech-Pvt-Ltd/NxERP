"""The NXERP app registry: the one declarative list of apps the platform knows about.

An entry exists only for an app that is really part of NXERP. It is *active* only while that app is
installed on the site. Frappe Framework is not an NXERP application and is never listed: its
DocTypes, methods and routes are the "shared set" that stays governed by Frappe's own permissions
(docs/security/shared-set.md).

Adding an app = one `AppEntry` below + role grants (docs/architecture/adding-an-app.md).

This module only holds strings. It never imports the apps it describes (ADR-005).
"""

from dataclasses import dataclass

import frappe


@dataclass(frozen=True)
class AppEntry:
	key: str  # stable identifier used in grants, logs and URLs
	title: str
	logo: str
	route: str  # where a user with staff access to this app lands
	order: int  # launcher order, ascending
	app: str  # the Frappe app that must be installed for the entry to be active
	owns: tuple  # python app names whose DocTypes, modules and whitelisted methods belong to this app
	access_role: str  # the role an administrator assigns to grant staff access (ADR-003)
	implied_roles: tuple = ()  # existing app roles that also count as staff access (ADR-003 amendment 1)
	path_prefixes: tuple = ()  # URL prefixes only staff of this app may open
	portal_roles: tuple = ()  # roles that may use the app's customer-facing surface (API and records)
	portal_prefixes: tuple = ()  # URL prefixes those portal roles may also open
	portal_route: str | None = None  # where a portal-only user lands
	admin_shell: bool = False  # platform administrators may open the path prefixes to administer
	test_only: bool = False  # declared through site config on a test site only; never a shipped app

	@property
	def grant_roles(self) -> frozenset:
		return frozenset((self.access_role, *self.implied_roles))


APPS: tuple = (
	AppEntry(
		key="erpnext",
		title="ERPNext",
		logo="/assets/erpnext/images/erpnext-logo.svg",
		route="/desk",
		order=10,
		app="erpnext",
		owns=("erpnext", "payments"),
		access_role="NXERP Access: ERPNext",
		path_prefixes=("/desk", "/app"),
		# ERPNext's own customer/supplier website model keeps working for website users
		portal_roles=("Customer", "Supplier"),
		admin_shell=True,
	),
	AppEntry(
		key="helpdesk",
		title="Helpdesk",
		logo="/assets/helpdesk/desk/manifest/manifest-icon-192.maskable.png",
		route="/helpdesk/home",
		order=20,
		app="helpdesk",
		owns=("helpdesk", "telephony"),
		access_role="NXERP Access: Helpdesk",
		implied_roles=("Agent", "Agent Manager"),
		path_prefixes=("/helpdesk",),
		portal_roles=("HD Customer", "HD Customer Manager"),
		portal_prefixes=("/helpdesk",),
		portal_route="/helpdesk/my-tickets",
	),
)


def _test_only_entries() -> tuple:
	"""Entries declared in site config `nxerp_test_apps`, honoured ONLY while `allow_tests` is on.

	This exists so end-to-end tests can exercise a third app (a manager with Helpdesk plus another app)
	against the running site. A production site never sets `allow_tests`, so these entries are inert there;
	they are marked `test_only` and never shown outside a test site.
	"""
	if not frappe.conf.get("allow_tests"):
		return ()
	entries = []
	for raw in frappe.conf.get("nxerp_test_apps") or []:
		try:
			entries.append(
				AppEntry(
					key=raw["key"],
					title=raw["title"],
					logo=raw.get("logo", ""),
					route=raw["route"],
					order=int(raw.get("order", 50)),
					app="frappe",  # "installed" because Frappe always is
					owns=tuple(raw.get("owns", (f"{raw['key']}_test_pkg",))),
					access_role=raw["access_role"],
					test_only=True,
				)
			)
		except (KeyError, TypeError, ValueError):
			continue
	return tuple(entries)


def get_registry() -> tuple:
	"""All declared entries (read at call time so tests can substitute the list)."""
	return (*APPS, *_test_only_entries())


def installed_entries() -> list:
	"""Entries whose app is installed on this site, in launcher order."""
	installed = set(frappe.get_installed_apps())
	return sorted((e for e in get_registry() if e.app in installed), key=lambda e: e.order)


def get_entry(key: str) -> AppEntry | None:
	return next((e for e in installed_entries() if e.key == key), None)


def entry_for_package(package: str) -> AppEntry | None:
	"""The entry owning a python package, e.g. the first segment of a whitelisted method path."""
	return next((e for e in installed_entries() if package in e.owns), None)


def entry_for_path(path: str) -> tuple:
	"""(entry, kind) for a URL path: kind is "staff" or "portal"; (None, None) if no entry claims it."""
	for entry in installed_entries():
		if _under(path, entry.path_prefixes):
			return entry, "staff"
	return None, None


def entry_for_module(module: str | None) -> AppEntry | None:
	if not module:
		return None
	app = frappe.local.module_app.get(frappe.scrub(module))
	return entry_for_package(app) if app else None


def entry_for_doctype(doctype: str | None) -> AppEntry | None:
	"""The entry whose app owns a DocType (DocType -> module -> app). None = shared or custom."""
	if not doctype or not isinstance(doctype, str):
		return None
	module = frappe.get_cached_value("DocType", doctype, "module")
	return entry_for_module(module)


def _under(path: str, prefixes: tuple) -> bool:
	return any(path == p or path.startswith(p + "/") for p in prefixes)


def under(path: str, prefixes: tuple) -> bool:
	return _under(path, prefixes)
