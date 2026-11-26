"""The public site: Home, Products and a page per installed product (Phase 1 of the NXDESK plan).

Everything here is read-only presentation. It creates no account and grants nothing: access is still
decided by `nxerp.access` and enforced by `nxerp.enforcement`, which this module only asks ("does this
signed-in user hold the product?") to choose between "Open application" and "Learn more".

What may appear on a public page: the installed, non-test products and their registry copy. Never a role
name, an uninstalled app, another user's data, or a stack trace.
"""

import os

import frappe
from frappe import _

from nxerp import access, branding, public_catalog, registry

HOME_ROUTE = "/nxerp/home"  # the page; guests also get it at "/"
PRODUCTS_ROUTE = "/products"
GET_STARTED_ROUTE = "/get-started"
SIGNUP_ROUTE = "/signup"
WELCOME_ROUTE = "/welcome/{key}"
LOGIN_ROUTE = access.LOGIN_ROUTE
ROUTER_ROUTE = "/nxerp/go"

HOME_PAGE_PATH = HOME_ROUTE.strip("/")

# the small icon beside a product in the header menu (anything else gets the generic grid)
PRODUCT_ICONS = {"erpnext": "chart", "helpdesk": "headset", "aira-hrms": "users"}


def website_user_home_page(user: str):
	"""Hook `get_website_user_home_page`: a guest who opens "/" sees the public Home.

	Only guests are answered. Everyone else gets None, so Frappe falls through to its own rules and a signed-in
	login still ends at the router (`nxerp.routing.on_session_creation` sets the home page flag, which wins).
	Site config `nxerp_keep_login_home` restores the old behaviour (a guest at "/" lands on /login).
	"""
	if user == "Guest" and not frappe.conf.get("nxerp_keep_login_home"):
		return HOME_PAGE_PATH
	return None


def _version(*relative_path) -> int:
	try:
		return int(os.path.getmtime(frappe.get_app_path("nxerp", "public", *relative_path)))
	except Exception:
		return 1


def base_context(context, *, title: str, description: str, active: str = "", canonical: str = "") -> dict:
	"""Fields every public page and its header, footer and head partials read."""
	user = frappe.session.user
	guest = user == "Guest"
	full_name = "" if guest else frappe.utils.get_fullname(user)

	context.no_header = True
	context.show_sidebar = False
	context.title = title
	context.nx = frappe._dict(
		name=branding.PLATFORM_NAME,
		tagline=branding.TAGLINE,
		wordmark=branding.wordmark(),
		favicon=branding.FAVICON,
		support_url=branding.support_url(),
		guest=guest,
		full_name=full_name,
		home_href="/" if guest else HOME_ROUTE,
		nav=nav(),
		icons=public_catalog.ICONS,
		contact=public_catalog.CONTACT,
		footer_products=[{"title": p["title"], "href": p["page_href"]} for p in products()],
		products_href=PRODUCTS_ROUTE,
		login_href=LOGIN_ROUTE,
		get_started_href=GET_STARTED_ROUTE,
		open_apps_href=ROUTER_ROUTE,
		active=active,
		description=description,
		canonical=canonical,
		year=frappe.utils.now_datetime().year,
		lang=frappe.local.lang or "en",
		css_theme=_version("css", "nxerp-theme.css"),
		css_platform=_version("css", "nxerp-platform.css"),
		css_site=_version("css", "nxerp-site.css"),
		css_login=_version("nxerp_login", "css", "nxerp-login.css"),
		css_onboarding=_version("css", "nxerp-onboarding.css"),
		lang_name=_language_name(frappe.local.lang or "en"),
	)
	return context


def _language_name(code: str) -> str:
	try:
		name = frappe.db.get_value("Language", code, "language_name") or "English"
	except Exception:
		return "English"
	return name.split(" (")[0]


def present(entry, user: str | None = None) -> dict:
	"""One product as the public templates read it. `href` and `cta` depend on whether the viewer holds it."""
	user = user or frappe.session.user
	destination = _held_destination(entry, user)
	base = (
		entry.origin or ""
	)  # an app listed on the identity site lives on another origin: every link goes there

	def at(path):
		return f"{base}{path}" if path else None

	return {
		"key": entry.key,
		"title": entry.public_title,
		"tagline": entry.tagline,
		"summary": entry.summary,
		"features": list(entry.features),
		"category": entry.category,
		"logo": entry.logo,
		"signup_policy": entry.signup_policy,
		"held": bool(destination),
		"open_href": at(destination),
		"page_href": at(f"{PRODUCTS_ROUTE}/{entry.key}"),
		"get_started_href": at(f"{GET_STARTED_ROUTE}?product={entry.key}"),
		"signup_href": at(f"{SIGNUP_ROUTE}?app={entry.key}"),
		"welcome_href": at(WELCOME_ROUTE.format(key=entry.key)),
		"login_href": at(f"{LOGIN_ROUTE}?app={entry.key}"),
		"href": at(destination or f"{PRODUCTS_ROUTE}/{entry.key}"),
		"cta": _("Open application") if destination else _("Learn more"),
	}


def _held_destination(entry, user: str) -> str | None:
	"""Where "Open application" goes, or None when the viewer does not hold the product (guests never do)."""
	if not user or user == "Guest":
		return None
	if access.can_access_app(user, entry.key):
		return entry.route
	if entry.portal_route and access.can_use_portal(user, entry.key):
		return entry.portal_route
	return None


def present_upcoming(item) -> dict:
	"""An announced product that is not installed: a page and a tile, never a sign-up, a sign-in or an application link."""
	return {
		"key": item.key,
		"title": item.title,
		"tagline": item.tagline,
		"summary": item.summary,
		"features": list(item.features),
		"category": item.category,
		"logo": item.logo,
		"mark": item.mark,
		"upcoming": True,
		"held": False,
		"open_href": None,
		"page_href": f"{PRODUCTS_ROUTE}/{item.key}",
		"href": f"{PRODUCTS_ROUTE}/{item.key}",
		"cta": _("Coming soon"),
	}


def installed_keys() -> tuple:
	return tuple(e.key for e in registry.installed_entries())


def listed_keys() -> tuple:
	"""The products the public pages list (installed here, or on an identity site the peers' apps): an announced product that is listed as live is no longer "coming soon"."""
	return tuple(e.key for e in registry.catalogue_entries())


def products() -> list:
	"""The products the public site shows, in launcher order, then the announced ones (clearly marked)."""
	user = frappe.session.user
	shown = [present(entry, user) for entry in registry.catalogue_entries()]
	shown += [present_upcoming(u) for u in public_catalog.upcoming(listed_keys())]
	return shown


def nav() -> list:
	"""The header menus: Products from the registry (and the announced ones), the rest from `public_catalog`."""
	items = [
		{
			"title": p["title"],
			"desc": p["tagline"],
			"href": p["page_href"],
			"soon": bool(p.get("upcoming")),
			"icon": PRODUCT_ICONS.get(p["key"], "grid"),
		}
		for p in products()
	]
	items.append(
		{
			"title": _("All products"),
			"desc": _("Everything in one list"),
			"href": PRODUCTS_ROUTE,
			"soon": False,
			"icon": "list",
		}
	)
	menus = [{"label": _("Products"), "children": items}]
	menus += [dict(m) for m in public_catalog.NAV_STATIC]
	return menus


def products_by_category() -> list:
	"""[(category, [product, ...]), ...] in first-seen order, announced products last in their category."""
	groups: dict = {}
	for product in products():
		groups.setdefault(product["category"], []).append(product)
	return list(groups.items())


def product(key) -> dict | None:
	"""An installed product, or an announced one (marked `upcoming`). Anything else is None (a 404)."""
	if not isinstance(key, str):
		return None
	# the products the site LISTS: installed here, or on an identity site the apps of the enabled peers (so a listed product never 404s)
	entry = next((e for e in registry.catalogue_entries() if e.key == key), None)
	if entry:
		return present(entry)
	item = public_catalog.upcoming_entry(key, installed_keys())
	return present_upcoming(item) if item else None


def redirect(location: str):
	frappe.local.flags.redirect_location = location
	raise frappe.Redirect


def platform_hero() -> dict:
	"""The hero for pages that belong to no product (set password, messages, errors): the platform's own tagline and three promises."""
	return frappe._dict(
		key="",
		title=branding.PLATFORM_NAME,
		tagline=branding.TAGLINE,
		summary="",
		features=[_("One sign-in"), _("Access by role"), _("Checked on the server")],
		logo=branding.FAVICON,
	)
