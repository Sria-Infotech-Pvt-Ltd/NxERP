"""The NXERP login: the one /login for every app.

Authentication is Frappe's. `frappe.www.login.get_context` builds the stock context (forms, 2FA, social
login, sign-up flags, password reset) and the template extends Frappe's own login template, so no
credential is handled here. This module only layers branding, and decides where an already-signed-in
visitor goes and which `redirect-to` is allowed to survive.

Kill-switch: set site config `nxerp_stock_login` to 1 and /login serves the unmodified Frappe login
(docs/runbooks/login-recovery.md).
"""

import os
import re
from urllib.parse import quote, urlencode

import frappe
from frappe import _
from frappe.www.login import get_context as frappe_login_context

from nxerp import routing

BRAND = "NXERP"
ASSETS = "/assets/nxerp/nxerp_login"
LOGO = f"{ASSETS}/images/nxerp-wordmark.png"
FAVICON = f"{ASSETS}/images/nxerp-favicon.png"
STOCK_NAMES = {"frappe", "helpdesk", "erpnext"}

# UI switch. Social sign-in (e.g. Microsoft) still works in the backend; flip this to show its button.
SHOW_SOCIAL_LOGIN = False

no_cache = True


def stock_login_enabled() -> bool:
	return bool(frappe.conf.get("nxerp_stock_login"))


def get_context(context):
	"""Stock context first (the framework's own authentication code), branding on top."""
	if not stock_login_enabled():
		_normalise_return_target()

	context = frappe_login_context(context) or context
	context.nx_stock = stock_login_enabled()
	if context.nx_stock:
		return context

	name = (context.get("app_name") or "").strip()
	if not name or name.lower() in STOCK_NAMES:
		context.app_name = BRAND

	logo = context.get("logo") or ""
	if not logo or logo.startswith("/assets/frappe/") or "nxerp" in logo.lower():
		context.logo = LOGO
	context.favicon = FAVICON

	if not context.get("login_name_placeholder"):
		label = (context.get("login_label") or _("Email")).strip().lower()
		context.login_name_placeholder = _("Enter your {0}").format(label)

	# Drop the vendor-cloud shortcut button that stock Frappe may add.
	context.login_with_frappe_cloud_url = None

	context.nx_year = frappe.utils.now_datetime().year
	context.nx_css_version = _asset_version("nxerp_login", "css", "nxerp-login.css")
	context.nx_theme_version = _asset_version("css", "nxerp-theme.css")
	context.nx_lang_code = frappe.local.lang or "en"
	context.nx_lang_name = _language_name(context.nx_lang_code)
	context.nx_support_url = _support_url()
	context.nx_show_social = SHOW_SOCIAL_LOGIN
	# The email-link option is not offered; the social block only renders when switched on.
	context.login_with_email_link = 0
	if not SHOW_SOCIAL_LOGIN:
		context.social_login = False
		context.provider_logins = []
	return context


def _normalise_return_target():
	"""Validate `redirect-to` before the page (or Frappe's script) can use it.

	- a signed-in visitor goes straight through the router;
	- an unsafe target is dropped (the visitor sees a plain /login);
	- a safe target is rewritten to travel through the router, so after authentication the router, not the
	  browser, decides whether the user may go there.
	"""
	form = frappe.local.form_dict
	raw = form.get("redirect-to")

	if frappe.session.user != "Guest":
		_go(routing.ROUTER_ROUTE + (f"?redirect-to={quote(raw, safe='')}" if raw else ""))

	if raw is None:
		return
	wanted = routing.login_redirect_param(raw)
	if wanted == raw:
		return
	_go("/login" + (f"?redirect-to={quote(wanted, safe='/')}" if wanted else ""))


def _go(location: str):
	frappe.local.flags.redirect_location = location
	raise frappe.Redirect


def _asset_version(*relative_path):
	try:
		path = frappe.get_app_path("nxerp", "public", *relative_path)
		return int(os.path.getmtime(path))
	except Exception:
		return 1


def _language_name(code):
	try:
		name = frappe.db.get_value("Language", code, "language_name") or "English"
		return re.sub(r"\s*\(.*\)\s*$", "", name)  # "English (United States)" -> "English"
	except Exception:
		return "English"


def _support_url():
	"""The "Contact IT Support" link. Nothing is hard-coded: set site config `nxerp_support_url` (any
	mailto:, https:// or site-relative link) or `nxerp_support_email` (opens a Gmail compose window).
	Neither set = no link."""
	custom = (frappe.conf.get("nxerp_support_url") or "").strip()
	if custom.lower().startswith(("mailto:", "https://", "http://", "/")):
		return custom
	email = (frappe.conf.get("nxerp_support_email") or "").strip()
	if not email or "@" not in email:
		return None
	query = urlencode({"view": "cm", "fs": 1, "to": email, "su": f"{BRAND} IT Support"}, quote_via=quote)
	return f"https://mail.google.com/mail/?{query}"
