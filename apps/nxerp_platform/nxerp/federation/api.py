"""The provisioning API of an APP site: the identity site calls it to create, enable and disable users and to list what it provisioned.

Server-side rules (Phase 6, ADR-003 amendment 2), none of which can be skipped by a caller:
  * not `allow_guest`; the caller must hold the role "NXERP Provisioner" (a service user with that one role); every denial is logged
    through `nxerp.audit` (a hashed user reference, no address);
  * a user is created WITHOUT a password and without a welcome email: people sign in through the identity site;
  * only the access role of the app THIS site owns (`NXERP Access: <app>`) is ever added or removed; System Manager is never granted
    and Administrator and Guest are refused;
  * a user is disabled, never deleted;
  * every call is idempotent: the same `idempotency_key` returns the stored answer (kept 7 days), and the operations themselves set a
    desired state, so repeating one changes nothing.
Business roles (Agent, Sales User, ...) are NOT touched: the app's own administrator gives those on this site.
"""

import re
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, validate_email_address

from nxerp import audit, registry

PROVISIONER_ROLE = "NXERP Provisioner"
USER_TYPES = ("System User", "Website User")
RESERVED = ("administrator", "guest")
KEY_PATTERN = re.compile(r"^[A-Za-z0-9:_.|@+-]{8,140}$")
IDEMPOTENCY_SECONDS = 7 * 24 * 3600
MAX_PAGE = 200


def _require_provisioner(method: str):
	user = frappe.session.user
	if registry.site_role() != "app":  # default off: a site that is not an app site has no provisioning API
		audit.log_denial("api_method", None, user, method=method, reason="federation is off on this site")
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if user == "Guest" or PROVISIONER_ROLE not in frappe.get_roles(user):
		audit.log_denial("api_method", None, user, method=method, reason="not a provisioner")
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _clean_email(email) -> str:
	email = (email or "").strip().lower() if isinstance(email, str) else ""
	if not email or email in RESERVED or not validate_email_address(email):
		frappe.throw(_("A valid, non-reserved email address is required"), frappe.ValidationError)
	return email


def _clean_key(key) -> str:
	if not isinstance(key, str) or not KEY_PATTERN.match(key):
		frappe.throw(_("A valid idempotency_key is required"), frappe.ValidationError)
	return key


def _stored(key: str):
	return frappe.cache.get_value(f"nxerp_fed_idem:{key}")


def _store(key: str, result: dict) -> dict:
	frappe.cache.set_value(f"nxerp_fed_idem:{key}", result, expires_in_sec=IDEMPOTENCY_SECONDS)
	return result


@contextmanager
def _provisioning():
	"""While set, `nxerp.guard` lets a non-administrator change THIS site's access roles (and nothing else)."""
	previous = frappe.flags.get("nxerp_provisioning")
	frappe.flags.nxerp_provisioning = True
	try:
		yield
	finally:
		frappe.flags.nxerp_provisioning = previous


def _owned_entry(app_key):
	entry = registry.get_entry(app_key) if isinstance(app_key, str) else None
	if not entry:
		frappe.throw(_("This site does not own that application"), frappe.ValidationError)
	return entry


def _names(full_name: str, email: str) -> tuple:
	full = (full_name or "").strip() if isinstance(full_name, str) else ""
	first, _sep, last = (full or email.split("@")[0]).partition(" ")
	return first[:140], last[:140]


def _apps_of(roles: set) -> list:
	return [e.key for e in registry.installed_entries() if e.access_role in roles]


@frappe.whitelist(methods=["POST"])
def provision_user(
	email, full_name, enabled=1, user_type="System User", app_key=None, grant=1, idempotency_key=None
):
	"""Create the user if needed (no password), set `enabled`, and add (`grant`=1) or remove (`grant`=0) this site's access role."""
	_require_provisioner("provision_user")
	key = _clean_key(idempotency_key)
	if (done := _stored(key)) is not None:
		return done
	email = _clean_email(email)
	entry = _owned_entry(app_key)
	if user_type not in USER_TYPES:
		frappe.throw(_("user_type must be System User or Website User"), frappe.ValidationError)
	if entry.access_role == "System Manager":  # defence in depth: the registry never holds it
		frappe.throw(_("Refused"), frappe.PermissionError)

	created = False
	with _provisioning():
		if frappe.db.exists("User", email):
			doc = frappe.get_doc("User", email)
		else:
			first, last = _names(full_name, email)
			doc = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": first,
					"last_name": last,
					"user_type": user_type,
					"send_welcome_email": 0,
				}
			)
			doc.flags.no_welcome_mail = True
			created = True
		doc.enabled = 1 if cint(enabled) else 0
		held = {row.role for row in doc.get("roles") or []}
		if cint(grant) and entry.access_role not in held:
			doc.append("roles", {"role": entry.access_role})
		elif not cint(grant) and entry.access_role in held:
			doc.roles = [row for row in doc.roles if row.role != entry.access_role]
		doc.flags.ignore_permissions = True
		if created:
			doc.insert()
		else:
			doc.save()

	roles = {row.role for row in frappe.get_doc("User", email).roles}
	audit.log_event(
		"federation_provision",
		entry.key,
		email,
		created=created,
		enabled=bool(cint(enabled)),
		grant=bool(cint(grant)),
	)
	return _store(
		key,
		{
			"user": email,
			"created": created,
			"enabled": bool(cint(enabled)),
			"app_access": entry.access_role in roles,
		},
	)


@frappe.whitelist(methods=["POST"])
def deprovision_user(email, idempotency_key=None):
	"""Disable the user and remove this site's access role(s). Never deletes. An unknown user is a no-op."""
	_require_provisioner("deprovision_user")
	key = _clean_key(idempotency_key)
	if (done := _stored(key)) is not None:
		return done
	email = _clean_email(email)
	if frappe.db.exists("User", email):
		with _provisioning():
			doc = frappe.get_doc("User", email)
			owned = {e.access_role for e in registry.installed_entries()}
			doc.enabled = 0
			doc.roles = [row for row in doc.roles if row.role not in owned]
			doc.flags.ignore_permissions = True
			doc.save()
	audit.log_event("federation_deprovision", None, email)
	return _store(key, {"user": email, "enabled": False})


@frappe.whitelist(methods=["GET"])
def list_provisioned(after="", limit=MAX_PAGE):
	"""Users holding this site's access role(s), in email order: {"users": [{email, enabled, user_type, apps}], "next": cursor or None}."""
	_require_provisioner("list_provisioned")
	limit = max(1, min(cint(limit) or MAX_PAGE, MAX_PAGE))
	after = (after or "").strip().lower() if isinstance(after, str) else ""
	roles = sorted(e.access_role for e in registry.installed_entries())
	if not roles:
		return {"users": [], "next": None}
	holders = sorted(
		{
			name.lower()
			for name in frappe.get_all(
				"Has Role", filters={"role": ("in", roles), "parenttype": "User"}, pluck="parent"
			)
			if name not in ("Administrator", "Guest")
		}
	)
	page = [name for name in holders if name > after][: limit + 1]
	more = len(page) > limit
	page = page[:limit]
	users = []
	for name in page:
		if not frappe.db.exists("User", name):
			continue
		row = frappe.db.get_value("User", name, ["enabled", "user_type"], as_dict=True)
		held = set(frappe.get_all("Has Role", filters={"parent": name, "parenttype": "User"}, pluck="role"))
		users.append(
			{"email": name, "enabled": bool(row.enabled), "user_type": row.user_type, "apps": _apps_of(held)}
		)
	return {"users": users, "next": page[-1] if more and page else None}
