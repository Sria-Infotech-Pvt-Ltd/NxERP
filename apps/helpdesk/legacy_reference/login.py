import os
import re
from urllib.parse import quote, urlencode

import frappe
from frappe import _
from frappe.www.login import get_context as frappe_login_context

BRAND = "NXERP"
ASSETS = "/assets/helpdesk/nxerp_login"
LOGO = f"{ASSETS}/images/nxerp-wordmark.png"
FAVICON = f"{ASSETS}/images/nxerp-favicon.png"
STOCK_NAMES = {"frappe", "helpdesk", "erpnext"}

# UI switches. Social sign-in (e.g. Microsoft) still works in the backend; flip this to show its button.
SHOW_SOCIAL_LOGIN = False
SUPPORT_EMAIL = (
    "sriainfotech@gmail.com"  # override with site config `nxerp_support_url`
)

no_cache = True


def get_context(context):
    """Build the stock login context (authentication, redirects, social login,
    2FA, sign-up flags - all the framework's own code) and only layer branding
    on top. Nothing is written to the database."""
    context = frappe_login_context(context) or context

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
    context.nx_css_version = _asset_version("css/nxerp-login.css")
    context.nx_theme_version = _asset_version("css/nxerp-theme.css")
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


def _asset_version(relative_path):
    try:
        path = frappe.get_app_path(
            "helpdesk", "public", "nxerp_login", *relative_path.split("/")
        )
        return int(os.path.getmtime(path))
    except Exception:
        return 1


def _language_name(code):
    try:
        name = frappe.db.get_value("Language", code, "language_name") or "English"
        return re.sub(
            r"\s*\(.*\)\s*$", "", name
        )  # "English (United States)" -> "English"
    except Exception:
        return "English"


def _support_url():
    """ "Contact IT Support" opens a Gmail compose window to the support address (works without a
    desktop mail app). Site config `nxerp_support_url` can override it with any safe link.
    """
    custom = (frappe.conf.get("nxerp_support_url") or "").strip()
    if custom.lower().startswith(("mailto:", "https://", "http://", "/")):
        return custom
    query = urlencode(
        {"view": "cm", "fs": 1, "to": SUPPORT_EMAIL, "su": f"{BRAND} IT Support"},
        quote_via=quote,
    )
    return f"https://mail.google.com/mail/?{query}"
