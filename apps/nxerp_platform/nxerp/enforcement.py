"""Server-side app gate (ADR-003). Defence in depth, three layers, all additive:

1. `auth_hook`  - runs for every request after the session is known and before any dispatch.
   It classifies the request (page prefix, whitelisted method, resource, request arguments) and
   denies when the user has no access to the owning app.
2. `has_permission` (wildcard hook) - document level. Reached by file downloads, print, realtime
   room joins and any `doc.check_permission()` regardless of URL.
3. `permission_query_conditions` (wildcard hook) - list level. Reached by `get_list`, report views
   and website list pages.

None of these can grant anything: they only deny. Frappe's DocType, field and record permissions
still apply on top. Anything not owned by a registered app (the "shared set": Frappe core DocTypes
such as User, File, Comment, ToDo; `frappe.*` methods; custom DocTypes) is left to Frappe alone.

Fail closed: if classification or the resolver errors, a non-Administrator is denied and the error
is logged. Administrator is never evaluated, so a resolver bug cannot lock the superuser out.
"""

import json
from dataclasses import dataclass
from urllib.parse import quote

import frappe
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect as werkzeug_redirect
from werkzeug.wrappers import Response

from nxerp import access, registry
from nxerp.audit import log_denial

# Never gated: authentication, the no-access page itself, static and public files.
EXEMPT_PREFIXES = (
	"/login",
	"/logout",
	"/update-password",
	"/nxerp",
	"/assets",
	"/files",
	"/api/method/login",
	"/api/method/logout",
	"/api/method/ping",
)

# Request arguments that name the DocType a whitelisted method will operate on.
DOCTYPE_ARGS = ("doctype", "dt")
# Request arguments that carry a JSON document or list of documents.
DOC_ARGS = ("doc", "docs")
# Request arguments that name a Report (resolved through the report's module).
REPORT_ARGS = ("report_name", "report")

# Desk loaders whose argument names a Page or Workspace (not a DocType): resolved through its module.
NAV_METHODS = {
	"frappe.desk.desk_page.getpage": ("Page", "name"),
	"frappe.desk.desktop.get_desktop_page": ("Workspace", "page"),
}

# DocTypes that are shared but carry a `module`; their records belong to the module's app.
MODULE_SCOPED = ("Report", "Page", "Workspace", "Dashboard", "Dashboard Chart", "Number Card")

# Methods that bundle a document's assignments, comments, versions and user details. The customer
# portal never calls them, so portal-only users may not use them on owned DocTypes.
PORTAL_DENIED_METHODS = (
	"frappe.desk.form.load.getdoc",
	"frappe.desk.form.load.get_docinfo",
	"frappe.desk.form.load.get_communications",
)

# Internal columns removed from every JSON API response sent to a portal-only user: who a record is
# assigned to, and the comment trail. (Helpdesk's own customer list endpoint returns `_assign`.)
PORTAL_STRIP_KEYS = ("_assign", "_comments")

# v16 surfaces that enumerate every app's methods: platform administrators only.
ADMIN_ONLY_PREFIXES = ("/api/v2/discovery", "/api/v2/mcp")


@dataclass
class Decision:
	allow: bool = True
	app: str | None = None
	surface: str | None = None
	redirect: str | None = None
	reason: str | None = None
	doctype: str | None = None


ALLOW = Decision()


# --- classification ---------------------------------------------------------------------------


def _json_loads(value):
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except Exception:
		return None


def _method_of(path: str, form: dict):
	if path.startswith("/api/method/"):
		return path[len("/api/method/") :]
	if path.startswith("/api/v2/method/"):
		return path[len("/api/v2/method/") :]
	return form.get("cmd")


def doctypes_in_args(form: dict) -> list:
	"""DocTypes a request will act on, taken from the arguments Frappe's generic methods read."""
	found = []
	for key in DOCTYPE_ARGS:
		value = form.get(key)
		if isinstance(value, str):
			found.append(value)
	for key in DOC_ARGS:
		parsed = _json_loads(form.get(key))
		for doc in parsed if isinstance(parsed, list) else [parsed]:
			if isinstance(doc, dict) and isinstance(doc.get("doctype"), str):
				found.append(doc["doctype"])
	return found


def entries_for_request(path: str, form: dict) -> list:
	"""[(entry, surface, doctype)] for every owned thing the request touches (shared things are absent)."""
	hits = []

	method = None
	if path.startswith("/api/method/"):
		method = path[len("/api/method/") :]
	elif path.startswith("/api/v2/method/"):
		method = path[len("/api/v2/method/") :]
	elif form.get("cmd"):
		method = form.get("cmd")
	if isinstance(method, str) and method:
		entry = registry.entry_for_package(method.split(".")[0])
		if entry:
			hits.append((entry, "api_method", None))

	for base in ("/api/resource/", "/api/v2/document/", "/api/v2/doctype/"):
		if path.startswith(base):
			doctype = path[len(base) :].split("/")[0]
			entry = registry.entry_for_doctype(_unquote(doctype))
			if entry:
				hits.append((entry, "api_resource", _unquote(doctype)))

	for doctype in doctypes_in_args(form):
		entry = registry.entry_for_doctype(doctype)
		if entry:
			hits.append((entry, "api_method" if method else "api_resource", doctype))

	for key in REPORT_ARGS:
		name = form.get(key)
		if isinstance(name, str):
			module = frappe.get_cached_value("Report", name, "module")
			entry = registry.entry_for_module(module)
			if entry:
				hits.append((entry, "report", None))

	if method in NAV_METHODS:
		nav_doctype, arg = NAV_METHODS[method]
		value = form.get(arg)
		if arg == "page":  # get_desktop_page takes a JSON object {"name": ..., "public": ...}
			parsed = _json_loads(value)
			value = parsed.get("name") if isinstance(parsed, dict) else value
		if isinstance(value, str):
			entry = registry.entry_for_module(frappe.get_cached_value(nav_doctype, value, "module"))
			if entry:
				hits.append((entry, "nav", None))

	return hits


def _unquote(value: str) -> str:
	from urllib.parse import unquote

	return unquote(value)


def evaluate_request(user: str, path: str, method: str, form: dict) -> Decision:
	"""Decide one request. Pure apart from reading Frappe state; unit-testable."""
	if user == "Administrator":
		return ALLOW
	if registry.under(path, EXEMPT_PREFIXES):
		return ALLOW

	is_guest = user == "Guest"

	# 0. a disabled account reaches nothing. Frappe only checks `enabled` when a session starts, and
	# only force-logs-out when the change happens inside a login-manager request, so a session that
	# outlives a scripted disable would otherwise still answer shared endpoints.
	if not is_guest and not access.is_enabled(user):
		return Decision(
			False, None, "session", redirect=None if _wants_json(path, form) else "/login", reason="disabled"
		)

	# 1. pages: /desk, /app, /helpdesk
	entry, _ = registry.entry_for_path(path)
	if entry:
		if is_guest:
			return Decision(
				False,
				entry.key,
				"page",
				redirect=f"/login?redirect-to={quote(path, safe='/')}",
				reason="guest",
			)
		if access.can_access_app(user, entry.key):
			return ALLOW
		if registry.under(path, entry.portal_prefixes) and access.can_use_portal(user, entry.key):
			return ALLOW
		if entry.admin_shell and access.is_platform_admin(user):
			return ALLOW  # administer users and grants without holding the app
		return Decision(
			False, entry.key, "page", redirect=f"{access.NO_ACCESS_ROUTE}?app={entry.key}", reason="no_access"
		)

	# guests only ever reach what Frappe's own allow_guest permits
	if is_guest:
		return ALLOW

	# 2. surfaces that list every app's API
	if any(path.startswith(p) for p in ADMIN_ONLY_PREFIXES) and not access.is_platform_admin(user):
		return Decision(False, None, "discovery", reason="admin_only")

	# 3. API: owned method roots, resources, and DocTypes named in the arguments
	hits = entries_for_request(path, form)
	for owner, surface, doctype in hits:
		if not access.can_reach_app(user, owner.key):
			# a browser page (/printview, /list?doctype=...) gets the denial page, an API call gets JSON
			page = None if _wants_json(path, form) else f"{access.NO_ACCESS_ROUTE}?app={owner.key}"
			return Decision(False, owner.key, surface, redirect=page, reason="no_access", doctype=doctype)

	# 4. portal-only users: no document-info bundles on owned DocTypes
	if any(doctype for _, _, doctype in hits) and _method_of(path, form) in PORTAL_DENIED_METHODS:
		if access.is_portal_only(user):
			owner, surface, doctype = next(h for h in hits if h[2])
			return Decision(False, owner.key, surface, reason="portal_method", doctype=doctype)

	return ALLOW


# --- the request hook -------------------------------------------------------------------------


def _deny_response(decision: Decision):
	if decision.redirect:
		return werkzeug_redirect(decision.redirect, code=302)
	message = frappe._("You do not have access to this application")
	body = {
		"exc_type": "PermissionError",
		"message": message,
		"_server_messages": json.dumps(
			[json.dumps({"message": message, "title": "Not Permitted", "indicator": "red"})]
		),
	}
	return Response(json.dumps(body), status=403, mimetype="application/json")


def auth_hook():
	"""Registered under `auth_hooks`. Raises an HTTP response (redirect or JSON 403), never a traceback."""
	user = frappe.session.user
	if user == "Administrator" or not getattr(frappe.local, "request", None):
		return

	request = frappe.local.request
	path = request.path or ""

	try:
		decision = evaluate_request(user, path, request.method, frappe.local.form_dict or {})
	except Exception:
		# fail closed, loudly, without leaking why
		frappe.logger("nxerp.access", allow_site=True).error("resolver_error", exc_info=True)
		decision = Decision(
			False,
			None,
			"resolver_error",
			redirect=None if _wants_json(path, frappe.local.form_dict) else access.NO_ACCESS_ROUTE,
			reason="error",
		)

	if decision.allow:
		return

	if decision.reason != "guest":
		log_denial(
			decision.surface,
			decision.app,
			user,
			reason=decision.reason,
			doctype=decision.doctype,
			http_method=request.method,
		)

	raise HTTPException(response=_deny_response(decision))


def _wants_json(path: str, form) -> bool:
	"""API and RPC-style (`?cmd=`) requests get JSON; browser page loads get a redirect."""
	return path.startswith("/api/") or bool((form or {}).get("cmd"))


# --- response minimisation for portal-only users ----------------------------------------------


def strip_keys(value, keys=PORTAL_STRIP_KEYS):
	"""Recursively drop `keys` from parsed JSON."""
	if isinstance(value, dict):
		return {k: strip_keys(v, keys) for k, v in value.items() if k not in keys}
	if isinstance(value, list):
		return [strip_keys(v, keys) for v in value]
	return value


def after_request(response=None, request=None):
	"""Registered under `after_request`. Removes assignment and comment metadata from API responses to
	portal-only users. Fails closed: if it cannot sanitise, the response is replaced by a refusal."""
	try:
		user = frappe.session.user if getattr(frappe.local, "session", None) else "Guest"
		if response is None or request is None or user in ("Guest", "Administrator"):
			return
		if not (request.path.startswith("/api/") or (frappe.local.form_dict or {}).get("cmd")):
			return
		if "json" not in (response.mimetype or ""):
			return
		if not access.is_portal_only(user):
			return
	except Exception:
		return  # not initialised (e.g. a failed request): nothing to sanitise

	try:
		raw = response.get_data(as_text=True)
		if not raw or not any(key in raw for key in PORTAL_STRIP_KEYS):
			return
		response.set_data(json.dumps(strip_keys(json.loads(raw)), default=str))
	except Exception:
		frappe.logger("nxerp.access", allow_site=True).error("sanitiser_error", exc_info=True)
		response.set_data(_deny_response(Decision(False)).get_data(as_text=True))
		response.status_code = 403


# --- document level and list level (wildcard hooks) ------------------------------------------


def _owner_of_doc(doc):
	"""The registry entry owning a document: its DocType's app, or its module's app for scoped DocTypes."""
	doctype = doc.doctype
	if doctype in MODULE_SCOPED:
		return registry.entry_for_module(doc.get("module"))
	return registry.entry_for_doctype(doctype)


def has_permission(doc, ptype=None, user=None, debug=False):
	"""Registered under `has_permission` for "*". Deny-only: returns False to deny, True to defer."""
	user = user or frappe.session.user
	if user in ("Administrator", "Guest"):
		return True
	try:
		entry = _owner_of_doc(doc)
		if entry is None or access.can_reach_app(user, entry.key):
			return True
		log_denial("doc", entry.key, user, doctype=doc.doctype, ptype=ptype)
		return False
	except Exception:
		frappe.logger("nxerp.access", allow_site=True).error("resolver_error", exc_info=True)
		return False


def permission_query_conditions(user=None, doctype=None):
	"""Registered under `permission_query_conditions` for "*". Hides owned lists from users without the app."""
	user = user or frappe.session.user
	if user in ("Administrator", "Guest") or not doctype:
		return ""
	try:
		if doctype in MODULE_SCOPED:
			return _module_scoped_condition(user, doctype)
		entry = registry.entry_for_doctype(doctype)
		if entry is None or access.can_reach_app(user, entry.key):
			return ""
		log_denial("query", entry.key, user, doctype=doctype)
		return "1=0"
	except Exception:
		frappe.logger("nxerp.access", allow_site=True).error("resolver_error", exc_info=True)
		return "1=0"


def _module_scoped_condition(user: str, doctype: str) -> str:
	"""Navigation records (Workspace, Report, ...) of modules whose app the user cannot reach are hidden."""
	hidden = []
	for entry in registry.installed_entries():
		if not access.can_reach_app(user, entry.key):
			hidden += frappe.get_all(
				"Module Def", filters={"app_name": ["in", list(entry.owns)]}, pluck="name"
			)
	if not hidden:
		return ""
	quoted = ", ".join(frappe.db.escape(name) for name in hidden)
	return f"`tab{doctype}`.`module` not in ({quoted})"
