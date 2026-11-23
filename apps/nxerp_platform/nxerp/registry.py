"""The NXERP app registry: the one declarative list of apps the platform knows about.

An entry exists only for an app that is really part of NXERP. It is *active* only while that app is
installed on the site. Frappe Framework is not an NXERP application and is never listed: its
DocTypes, methods and routes are the "shared set" that stays governed by Frappe's own permissions
(docs/security/shared-set.md).

Adding an app = one `AppEntry` below + role grants (docs/architecture/adding-an-app.md).

This module only holds strings. It never imports the apps it describes (ADR-005).

Presentation fields (display name, tagline, summary, features, category) feed the public site and are all
optional. They describe only what the installed app really does. There is deliberately no per-app colour.
"""

from dataclasses import dataclass, replace
from urllib.parse import urlsplit

import frappe

SIGNUP_POLICIES = ("invite_only", "request_access", "open_portal")
DEFAULT_SIGNUP_POLICY = "request_access"
DEFAULT_CATEGORY = "Business apps"

# Copy limits, so a card never overflows (enforced by tests/test_registry.py)
TAGLINE_MAX = 60
SUMMARY_MAX = 180
FEATURES_MAX = 4
FEATURE_WORDS_MAX = 6


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
	# Presentation (public site). `title` stays what the launcher shows; `display_name` is what the public pages call it (ADR-008).
	display_name: str = ""
	tagline: str = ""
	summary: str = ""
	features: tuple = ()
	category: str = DEFAULT_CATEGORY
	signup_policy: str = DEFAULT_SIGNUP_POLICY  # invite_only | request_access | open_portal
	onboarding_steps: tuple = ("basics", "about")
	# Companion apps (python app names) that get their own tile on the Desk apps screen for people who hold this entry's grant,
	# for example India Compliance next to ERPNext. They keep their own title and logo; everything else stays hidden.
	desk_apps: tuple = ()
	# Where the product keeps its own brand name and logo, if it has such settings: (DocType, name field, logo field). Empty = none.
	brand_settings: tuple = ()
	# Wide logo (symbol and name) for the login card, when the product has one. Empty = its name is written as text.
	wordmark: str = ""
	# Where the app lives in a browser, e.g. https://hd.example.test. Empty everywhere except on an identity site, where it is
	# filled from the app's enabled NXERP Peer by `active_entries()` (see docs/architecture/routes.md, "Cross-origin routes").
	origin: str = ""

	@property
	def grant_roles(self) -> frozenset:
		return frozenset((self.access_role, *self.implied_roles))

	@property
	def public_title(self) -> str:
		return self.display_name or self.title


APPS: tuple = (
	AppEntry(
		key="erpnext",
		title="ERPNext",
		logo="/assets/erpnext/images/erpnext-logo.svg",
		route="/desk/home",  # ERPNext's own app_home; bare /desk is not a destination (routing.desk_root_redirect)
		order=10,
		app="erpnext",
		owns=("erpnext", "payments", "india_compliance"),
		desk_apps=("india_compliance",),
		access_role="NXERP Access: ERPNext",
		path_prefixes=("/desk", "/app"),
		# ERPNext's own customer/supplier website model keeps working for website users
		portal_roles=("Customer", "Supplier"),
		admin_shell=True,
		display_name="NXERP",
		tagline="Accounts, sales, stock and projects in one place",
		summary="Run accounting, selling, buying, stock, manufacturing and projects in one system, with access that follows each person's role.",
		features=(
			"Accounts and invoicing",
			"Sales, buying and stock",
			"Manufacturing and projects",
			"Assets and maintenance",
		),
	),
	AppEntry(
		key="helpdesk",
		title="Helpdesk",
		logo="/assets/nxerp/nxerp_login/images/sria-helpdesk-mark.png",
		wordmark="/assets/nxerp/nxerp_login/images/sria-helpdesk-logo.png",
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
		display_name="Sria Helpdesk",
		brand_settings=("HD Settings", "brand_name", "brand_logo"),
		tagline="Support tickets and a shared knowledge base",
		summary="Handle customer requests as tickets, share answers in a knowledge base and track service levels, with a portal where customers follow their own requests.",
		features=(
			"Tickets with teams and assignment",
			"Knowledge base articles",
			"Service level agreements",
			"Customer portal for requests",
		),
		category="Support",
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
		except KeyError, TypeError, ValueError:
			continue
	return tuple(entries)


def get_registry() -> tuple:
	"""All declared entries (read at call time so tests can substitute the list)."""
	return (*APPS, *_test_only_entries())


def installed_entries() -> list:
	"""Entries whose app is installed on this site, in launcher order."""
	installed = set(frappe.get_installed_apps())
	return sorted((e for e in get_registry() if e.app in installed), key=lambda e: e.order)


SITE_ROLES = ("identity", "app")


def site_role() -> str:
	"""`nxerp_site_role` from site config: "identity", "app", or "" (unset or anything else = today's behaviour)."""
	value = frappe.conf.get("nxerp_site_role")
	return value if value in SITE_ROLES else ""


def normalise_origin(value) -> str:
	"""`scheme://host[:port]` in lower case for an https URL (http only under developer_mode), else "". Strict: no userinfo, path,
	query, fragment, percent-encoding, trailing dot or non-ASCII host, because the result is compared for exact equality."""
	if not isinstance(value, str) or not value.strip() or value != value.strip():
		return ""
	if any(c in value for c in ("\\", "@", "%")) or any(ord(c) < 0x21 or ord(c) > 0x7E for c in value):
		return ""
	parts = urlsplit(value)
	scheme = parts.scheme.lower()
	allowed = ("https", "http") if frappe.conf.get("developer_mode") else ("https",)
	if (
		scheme not in allowed
		or not parts.netloc
		or parts.path not in ("", "/")
		or parts.query
		or parts.fragment
	):
		return ""
	host = (parts.hostname or "").lower()
	if not host or host.endswith(".") or parts.username is not None or parts.password is not None:
		return ""
	try:
		port = parts.port
	except ValueError:
		return ""
	return f"{scheme}://{host}" + (f":{port}" if port else "")


def _peers() -> list:
	"""Enabled NXERP Peer rows as dicts (app_key, origin). Empty when the DocType is not migrated yet."""
	try:
		return frappe.get_all("NXERP Peer", filters={"enabled": 1}, fields=["app_key", "origin"])
	except Exception:  # the DocType does not exist yet (before migrate): behave as if there were no peers
		return []


def allowed_origins() -> frozenset:
	"""Exact origins of the enabled NXERP Peer records. Empty unless this site has a site role, so a site that never
	set `nxerp_site_role` can never be sent to another origin."""
	if not site_role():
		return frozenset()
	return frozenset(o for o in (normalise_origin(p.origin) for p in _peers()) if o)


def active_entries() -> list:
	"""The entries this site offers. On an app site, or with no site role, exactly `installed_entries()`.

	On an identity site the apps are not installed: every registry entry that has an enabled NXERP Peer is active, carrying
	the peer's origin, in launcher order."""
	if site_role() != "identity":
		return installed_entries()
	origins = {p.app_key: normalise_origin(p.origin) for p in _peers()}
	return sorted(
		(replace(e, origin=origins[e.key]) for e in get_registry() if origins.get(e.key)),
		key=lambda e: e.order,
	)


def active_entry(key: str) -> AppEntry | None:
	return next((e for e in active_entries() if e.key == key), None)


def entry_for_origin(origin: str) -> AppEntry | None:
	"""The active entry living at an exact origin (identity site), else None."""
	return next((e for e in active_entries() if e.origin and e.origin == origin), None)


def get_entry(key: str) -> AppEntry | None:
	return next((e for e in installed_entries() if e.key == key), None)


def public_entries() -> list:
	"""The products the public site may show: installed, and never a test-only stand-in."""
	return [e for e in installed_entries() if not e.test_only]


def public_entry(key) -> AppEntry | None:
	return next((e for e in public_entries() if e.key == key), None)


def catalogue_entries() -> list:
	"""The products the public pages may LIST. On an app site, or with no site role, exactly `public_entries()`. On an identity site the apps
	are not installed, so the enabled peers' apps are listed, each carrying its origin: the tiles link to that app's own site, where
	sign-up and sign-in work. Display only: sign-up and access requests still resolve an app through `public_entry` (installed here)."""
	return [e for e in active_entries() if not e.test_only]


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
