"""Post-login routing and redirect safety (ADR-004).

Three jobs, all server-side:

1. `safe_target`: turn untrusted input (the `redirect-to` parameter) into a normalised same-origin path,
   or nothing. It never returns a URL with a scheme or host, however the input is encoded.
2. `authorised_target`: a safe path is honoured only when the user may use the app that owns it.
3. `route`: the single decision after login. A good `redirect-to` wins; otherwise the user's landing
   (`access.resolve_landing`) decides: no apps -> no-access page, one app -> that app, several -> launcher.

Routing is not security: the enforcement layer (`nxerp.enforcement`) re-checks every request, so a
wrong route can never expose an app the user lacks.
"""

import posixpath
from urllib.parse import quote, unquote, urlsplit

import frappe

from nxerp import access, registry

ROUTER_ROUTE = "/nxerp/go"
MAX_TARGET_LENGTH = 512
DECODE_ROUNDS = 3  # `%252f` style double encoding is decoded this many times before judging

# Paths outside any app that any signed-in user may be sent to.
SHARED_TARGETS = (access.LAUNCHER_ROUTE,)


def safe_target(raw) -> str | None:
	"""A normalised same-origin path (with optional query), or None. Never a scheme, host or `//`."""
	if not isinstance(raw, str):
		return None
	raw = raw.strip()
	if not raw or len(raw) > MAX_TARGET_LENGTH:
		return None

	# judge every decoding of the input, so `%2f%2fevil.com` and `%252f%252fevil.com` fail too
	candidate = raw
	for _ in range(DECODE_ROUNDS + 1):
		if not _clean(candidate):
			return None
		decoded = unquote(candidate)
		if decoded == candidate:
			break
		candidate = decoded
	else:
		return None  # still changing after the allowed rounds: refuse

	parts = urlsplit(candidate)
	if parts.scheme or parts.netloc or not candidate.startswith("/"):
		return None

	path = posixpath.normpath(parts.path)
	if parts.path.endswith("/") and not path.endswith("/"):
		path += "/"
	if not path.startswith("/") or path.startswith("//"):
		return None

	# the query is kept exactly as received (it was judged above in every decoding): re-serialising a decoded
	# query could change what it means
	raw_query = raw.partition("?")[2]
	return path + (f"?{raw_query}" if raw_query else "")


def _clean(text: str) -> bool:
	"""No control characters, backslashes, or header-splitting characters in any decoding."""
	if "\\" in text:
		return False
	if text.startswith("//") or text.startswith("/\\"):
		return False
	return not any(ord(c) < 0x20 or ord(c) == 0x7F for c in text)


def authorised_target(user: str, target: str | None) -> str | None:
	"""`target` if the user may use whatever owns it, else None (the caller then falls back to the router)."""
	if not target:
		return None
	path = urlsplit(target).path

	if path in SHARED_TARGETS:
		return target if user != "Guest" else None

	entry, _ = registry.entry_for_path(path)
	if entry is None:
		return None  # unknown destinations are never honoured
	if access.can_access_app(user, entry.key):
		return target
	if registry.under(path, entry.portal_prefixes) and access.can_use_portal(user, entry.key):
		return target
	return None


def landing_for(user: str) -> dict:
	"""`access.resolve_landing`, plus the first-run rule: an Administrator on a site whose setup wizard has
	not finished goes to Desk, because only Desk's router redirects to the wizard (ADR-004 rule 5)."""
	landing = access.resolve_landing(user)
	if user == "Administrator" and not frappe.is_setup_complete():
		return {**landing, "mode": "direct", "destination": "/desk", "reason": "setup"}
	return landing


def route(user: str, redirect_to=None) -> str:
	"""Where to send `user` now. Always a same-origin path."""
	if not user or user == "Guest":
		return access.LOGIN_ROUTE
	if not access.is_enabled(user):
		return access.LOGIN_ROUTE

	honoured = authorised_target(user, safe_target(redirect_to))
	if honoured:
		return honoured
	return landing_for(user)["destination"]


def login_redirect_param(redirect_to) -> str | None:
	"""The `redirect-to` value the login page should carry so that, after authentication, Frappe's own login
	script sends the browser through the router with the (already validated) target. None = drop it."""
	target = safe_target(redirect_to)
	if not target:
		return None
	if urlsplit(target).path == ROUTER_ROUTE:
		return target
	return f"{ROUTER_ROUTE}?redirect-to={quote(target, safe='')}"


def on_session_creation(login_manager=None):
	"""Registered under `on_session_creation`. Makes Frappe's login response point at the router.

	Frappe has two redirect engines (research part 1). The per-request `home_page` flag is the one override
	that survives both, so a fresh login, and every flow that asks for the home page, lands on the router.
	"""
	frappe.local.flags.home_page = ROUTER_ROUTE
	frappe.local.flags.nxerp_signed_in = True  # lets `after_request` re-point a redirect issued by this login


def after_request(response, request=None):
	"""Registered under `after_request`. A login that ends in a redirect (the emailed login link, social / SSO
	sign-in, any other Frappe flow that calls `redirect_post_login`) is pointed at the router.

	Frappe builds those redirects from its own default path, which would skip the router and let a user land
	somewhere they hold no grant. Only a response that follows a login in THIS request is touched, and the
	original same-origin destination is handed to the router as `redirect-to`, which still decides.
	"""
	if not frappe.local.flags.get("nxerp_signed_in"):
		return
	if response.status_code not in (301, 302, 303, 307, 308):
		return
	original = response.headers.get("Location", "")
	if original.split("?")[0].rstrip("/") == ROUTER_ROUTE:
		return
	host = getattr(request, "host", None) or frappe.local.request.host
	parts = urlsplit(original)
	same_origin = not parts.netloc or parts.netloc == host
	path = (parts.path + (f"?{parts.query}" if parts.query else "")) if same_origin else ""
	response.headers["Location"] = ROUTER_ROUTE + (f"?redirect-to={quote(path, safe='')}" if path else "")
