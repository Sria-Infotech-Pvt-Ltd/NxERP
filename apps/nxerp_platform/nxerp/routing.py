"""Post-login routing and redirect safety (ADR-004).

Three jobs, all server-side:

1. `safe_target`: turn untrusted input (the `redirect-to` parameter) into a normalised same-origin path,
   or nothing. It never returns a URL with a scheme or host, however the input is encoded, EXCEPT an absolute URL
   whose origin is exactly that of an enabled NXERP Peer (identity sites only; docs/architecture/routes.md).
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
DESK_ROOT_PATHS = ("/desk", "/desk/")
MAX_TARGET_LENGTH = 512
DECODE_ROUNDS = 3  # `%252f` style double encoding is decoded this many times before judging

# On an identity site only: Frappe's OAuth authorize endpoint (the single sign-on continuation, see authorised_target).
OAUTH_AUTHORIZE_PATH = "/api/method/frappe.integrations.oauth2.authorize"

# Paths outside any app that any signed-in user may be sent to.
SHARED_TARGETS = (access.LAUNCHER_ROUTE,)

# /welcome/<key>: the first-run wizard of an installed product. Any signed-in user may be sent there (that is how a
# person without the grant asks for it); it grants nothing, and the API behind it re-checks the session.
WELCOME_PREFIX = "/welcome/"
WELCOME_ROUTE = "/welcome/{key}"
GET_STARTED_ROUTE = "/get-started"


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
	if parts.scheme or parts.netloc:
		return _cross_origin_target(raw, parts)
	if not candidate.startswith("/"):
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


def _cross_origin_target(raw: str, parts) -> str | None:
	"""An absolute URL is honoured ONLY when its origin is EXACTLY the origin of an enabled NXERP Peer (`registry.allowed_origins`),
	which is empty on a site with no `nxerp_site_role`. Returned normalised: lower-case scheme and host, a cleaned path, the query as received.

	Refused: any other scheme or host, userinfo (`https://evil.test@id.example.test`), a host that only starts or ends like a peer
	(`id.example.test.evil.test`, a trailing dot), another port, percent-encoding or non-ASCII characters in the authority, and
	http unless the site is in developer_mode."""
	raw_parts = urlsplit(raw)
	if raw_parts.netloc != parts.netloc:  # decoding changed the authority: something was hidden in it
		return None
	own = _own_authorize_target(raw, raw_parts)
	if own:
		return own
	origin = registry.normalise_origin(f"{raw_parts.scheme}://{raw_parts.netloc}")
	if not origin or origin not in registry.allowed_origins():
		return None
	path = posixpath.normpath(parts.path or "/")
	if parts.path.endswith("/") and not path.endswith("/"):
		path += "/"
	if not path.startswith("/") or path.startswith("//"):
		return None
	raw_query = raw.partition("?")[2]
	return origin + path + (f"?{raw_query}" if raw_query else "")


def _own_hosts() -> set:
	"""Host names (no port, lower case) this site answers to: the request's own host and the host of its configured URL."""
	hosts = set()
	request = getattr(frappe.local, "request", None)
	if request is not None and getattr(request, "host", None):
		hosts.add(request.host.split(":")[0].lower())
	try:
		configured = urlsplit(frappe.utils.get_url()).hostname
	except Exception:
		configured = None
	if configured:
		hosts.add(configured.lower())
	return hosts


def _own_authorize_target(raw: str, raw_parts) -> str | None:
	"""Frappe attaches the single sign-on continuation to the identity site's login as an ABSOLUTE URL of this same site
	(`https://<this site>/api/method/frappe.integrations.oauth2.authorize?...`). On an identity site that one URL, and only when its host is
	this site's own (no user-info, no other host), is returned as a plain same-site path: the browser never leaves this origin."""
	if registry.site_role() != "identity" or raw_parts.path != OAUTH_AUTHORIZE_PATH:
		return None
	if (
		raw_parts.scheme.lower() not in ("http", "https")
		or "@" in raw_parts.netloc
		or "%" in raw_parts.netloc
	):
		return None
	if (raw_parts.hostname or "").lower() not in _own_hosts():
		return None
	return OAUTH_AUTHORIZE_PATH + (f"?{raw_parts.query}" if raw_parts.query else "")


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
	parts = urlsplit(target)
	path = parts.path

	if (
		parts.scheme
	):  # an absolute target only comes out of safe_target for a registered peer origin (identity site)
		entry = registry.entry_for_origin(f"{parts.scheme}://{parts.netloc}")
		if entry is None or user == "Guest" or not access.can_access_app(user, entry.key):
			return None
		if registry.under(path, entry.path_prefixes) or registry.under(path, entry.portal_prefixes):
			return target
		return None

	if path == OAUTH_AUTHORIZE_PATH:
		# An identity site: a person who is not signed in yet is sent to /login with "continue to the app" attached. Frappe's own
		# authorize endpoint is that continuation; dropping it would leave them on the app's login page again. Safe to honour: it is the
		# same site's endpoint, and it only answers for a registered OAuth client and a user holding that client's allowed role.
		return target if user != "Guest" and registry.site_role() == "identity" else None

	if path in SHARED_TARGETS:
		return target if user != "Guest" else None

	if path.startswith(WELCOME_PREFIX):
		key = path[len(WELCOME_PREFIX) :]
		if user != "Guest" and "/" not in key and registry.get_entry(key):
			return target
		return None

	entry, _ = registry.entry_for_path(path)
	if entry is None:
		return None  # unknown destinations are never honoured
	if access.can_access_app(user, entry.key):
		return target
	if registry.under(path, entry.portal_prefixes) and access.can_use_portal(user, entry.key):
		return target
	return None


def get_started_target(user: str, entry, *, has_app: bool, has_pending: bool) -> tuple:
	"""Where /get-started?product=<key> sends a visitor: (view, location). Pure: the caller supplies the facts.

	guest -> ("guest", None): show the page. Holds the app -> ("open", router URL carrying the app's route).
	A pending request -> ("pending", /welcome/<key>), which renders the pending view. Otherwise
	("welcome", /welcome/<key>): the wizard resumes where the person left it."""
	if not user or user == "Guest":
		return "guest", None
	welcome = WELCOME_ROUTE.format(key=entry.key)
	if has_app:
		return "open", f"{ROUTER_ROUTE}?redirect-to={quote(entry.route, safe='')}"
	if has_pending:
		return "pending", welcome
	return "welcome", welcome


def landing_for(user: str) -> dict:
	"""`access.resolve_landing`, plus the first-run rule: an Administrator on a site whose setup wizard has
	not finished goes to Desk, because only Desk's router redirects to the wizard (ADR-004 rule 5)."""
	landing = access.resolve_landing(user)
	if user == "Administrator" and not frappe.is_setup_complete():
		return {**landing, "mode": "direct", "destination": "/desk", "reason": "setup"}
	return landing


def route(user: str, redirect_to=None) -> str:
	"""Where to send `user` now: a same-origin path, or (identity site only) the registered origin of an app plus its route."""
	if not user or user == "Guest":
		return access.LOGIN_ROUTE
	if not access.is_enabled(user):
		return access.LOGIN_ROUTE

	honoured = authorised_target(user, safe_target(redirect_to))
	if honoured:
		return honoured
	return landing_for(user)["destination"]


def desk_root_redirect(user: str, path: str, method: str = "GET") -> str | None:
	"""Where a signed-in user who opened the bare Desk root (`/desk`) is sent instead, or None to leave it alone.

	`/nxerp/apps` is the one gateway, so Desk's own root screen is not a second one. Only the exact root path is
	moved; `/desk/*` stays ERPNext's home and is untouched. Left alone: an unfinished setup (the wizard redirect
	lives in Desk's client router, so Administrator keeps the bare root until it is done), a platform administrator without the ERPNext grant
	(keeps the Desk shell to grant access), anyone the gate refuses, and a site that set `nxerp_keep_desk_root`.
	"""
	if method != "GET" or path not in DESK_ROOT_PATHS or user == "Guest":
		return None
	if frappe.conf.get("nxerp_keep_desk_root") or not frappe.is_setup_complete():
		return None
	entry, _ = registry.entry_for_path(path)
	if entry is None or not access.can_access_app(user, entry.key):
		return None
	destination = route(user)
	return None if destination in DESK_ROOT_PATHS else destination  # never a redirect loop


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
