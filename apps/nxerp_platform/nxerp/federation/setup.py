"""Idempotent helpers that configure the login flow (Phase 6D). For tests and development; production uses the Desk screens (runbook steps 6.5 and 6.6).

    configure_identity_site()   one OAuth Client per enabled NXERP Peer, with the values proved in docs/architecture-isolation/spike-federation.md
    configure_app_site()        the Social Login Key "frappe" that points at the identity site, with Sign ups = Deny

Rules: secrets come ONLY from environment variables (never from arguments) and are never printed or logged; the result holds names and
client ids, never a secret; running a function twice changes nothing the second time; `disable_user_pass_login` is never set (a person does
that, after single sign-on is proved and the break-glass administrator is recorded: docs/runbooks/login-recovery.md).

Environment (identity site): NXERP_SSO_SECRET_<APP> for each peer, <APP> = the app key upper-cased with other characters as `_`
(for example NXERP_SSO_SECRET_HELPDESK): at least 32 characters.
Environment (app site): NXERP_IDENTITY_ORIGIN, NXERP_SSO_CLIENT_ID (the id the identity site printed), NXERP_SSO_CLIENT_SECRET (the same secret).
"""

import os
import re

import frappe
from frappe.utils.password import get_decrypted_password

from nxerp import registry

MIN_SECRET_LENGTH = 32
REDIRECT_PATH = "/api/method/frappe.integrations.oauth2_logins.login_via_frappe"
PROVIDER_KEY = "frappe"
SOCIAL_FIELDS = {
	"social_login_provider": "Frappe",
	"provider_name": "Frappe",
	"authorize_url": "/api/method/frappe.integrations.oauth2.authorize",
	"access_token_url": "/api/method/frappe.integrations.oauth2.get_token",  # nosec B105  (a URL path, not a password)
	"redirect_url": REDIRECT_PATH,
	"api_endpoint": "/api/method/frappe.integrations.oauth2.openid_profile",
	"auth_url_data": '{"response_type": "code", "scope": "openid"}',
	"enable_social_login": 1,
	"sign_ups": "Deny",
}


def secret_env_name(app_key: str) -> str:
	return "NXERP_SSO_SECRET_" + re.sub(r"[^A-Z0-9]", "_", app_key.upper())


def _secret(name: str) -> str:
	value = os.environ.get(name, "")
	if len(value) < MIN_SECRET_LENGTH:
		raise ValueError(
			f"set {name} in the environment to a secret of at least {MIN_SECRET_LENGTH} characters"
		)
	return value


def _set(doc, values: dict) -> bool:
	"""Apply `values` to `doc`; True when something differed."""
	changed = False
	for field, value in values.items():
		if (doc.get(field) or "") != value and not (value in (0, 1) and int(doc.get(field) or 0) == value):
			doc.set(field, value)
			changed = True
	return changed


def configure_identity_site() -> dict:
	"""Create or update the OAuth Client of every enabled peer. Returns {app_key: {"client_id", "changed"}}."""
	result = {}
	for entry in registry.active_entries():
		origin = entry.origin
		redirect = f"{origin}{REDIRECT_PATH}"
		secret = _secret(secret_env_name(entry.key))
		values = {
			"app_name": f"NXERP {entry.title}",
			"scopes": "all openid",
			"grant_type": "Authorization Code",
			"response_type": "Code",
			"skip_authorization": 1,
			"redirect_uris": redirect,
			"default_redirect_uri": redirect,
			"client_secret": secret,
		}
		name = frappe.db.get_value("OAuth Client", {"app_name": values["app_name"]}, "name")
		if name:
			doc = frappe.get_doc("OAuth Client", name)
			changed = _set(doc, values)
		else:
			doc = frappe.get_doc({"doctype": "OAuth Client", **values})
			changed = True
		# the gate: only people holding the app's access role may sign in to it (spike item a2: an empty list allows nobody)
		wanted = {entry.access_role}
		if {row.role for row in doc.get("allowed_roles") or []} != wanted:
			doc.set("allowed_roles", [{"role": role} for role in sorted(wanted)])
			changed = True
		if changed:
			doc.flags.ignore_permissions = True
			doc.save() if name else doc.insert()
		result[entry.key] = {"client_id": doc.name, "changed": changed}
	return result


def configure_app_site() -> dict:
	"""Create or update the Social Login Key "frappe" (Sign ups = Deny). Returns {"changed", "base_url"}; never a secret."""
	origin = registry.normalise_origin(os.environ.get("NXERP_IDENTITY_ORIGIN", ""))
	client_id = os.environ.get("NXERP_SSO_CLIENT_ID", "").strip()
	if not origin or not client_id:
		raise ValueError(
			"set NXERP_IDENTITY_ORIGIN (https://host) and NXERP_SSO_CLIENT_ID in the environment"
		)
	secret = _secret("NXERP_SSO_CLIENT_SECRET")
	values = {**SOCIAL_FIELDS, "client_id": client_id, "base_url": origin}
	exists = frappe.db.exists("Social Login Key", PROVIDER_KEY)
	doc = (
		frappe.get_doc("Social Login Key", PROVIDER_KEY)
		if exists
		else frappe.get_doc({"doctype": "Social Login Key"})
	)
	changed = _set(doc, values) if exists else True
	if not exists:
		doc.update(values)
	if (
		not exists
		or (
			get_decrypted_password("Social Login Key", PROVIDER_KEY, "client_secret", raise_exception=False)
			or ""
		)
		!= secret
	):
		doc.client_secret = secret
		changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save() if exists else doc.insert()
	return {"changed": changed, "base_url": origin}
