"""The one place for platform names, logo paths and support values (ADR-008).

NXDESK is the umbrella platform. A product's own display name and copy live in its registry entry
(`nxerp.registry`), never here. Technical identifiers (the app `nxerp`, `/nxerp/*`, the access roles) are not
branding and are never read from this module.

Logos: there is no NXDESK logo file yet. While `LOGO_LIGHT_THEME` and `LOGO_DARK_THEME` are empty the public
pages draw the name as a typographic wordmark (see `wordmark()`); set both paths and the pages switch to the
images, light on a light theme, dark on a dark theme. Nothing else needs to change.
"""

from urllib.parse import quote, urlencode

import frappe

PLATFORM_NAME = "NXDESK"
TAGLINE = "One sign-in for your business applications"

# Logo files for the platform, as site-relative paths. Empty = use the typographic wordmark.
LOGO_LIGHT_THEME = ""  # artwork that reads on a light surface
LOGO_DARK_THEME = ""  # artwork that reads on a dark surface

# The tab icon. The owner has supplied no NXDESK icon, so this is the existing platform one (a placeholder).
FAVICON = "/assets/nxerp/nxerp_login/images/nxerp-favicon.png"

# The sign-in page keeps its current NXERP look until the app-branded login phase (it carries NXERP logo images).
LOGIN_NAME = "NXERP"
LOGIN_ASSETS = "/assets/nxerp/nxerp_login"
LOGIN_LOGO = f"{LOGIN_ASSETS}/images/nxerp-wordmark.png"
LOGIN_FAVICON = f"{LOGIN_ASSETS}/images/nxerp-favicon.png"


def wordmark() -> dict:
	"""How to draw the platform name: images when both logo paths are set, otherwise text."""
	images = bool(LOGO_LIGHT_THEME and LOGO_DARK_THEME)
	return {
		"name": PLATFORM_NAME,
		"image": images,
		"light": LOGO_LIGHT_THEME,
		"dark": LOGO_DARK_THEME,
	}


def support_url(subject_name: str | None = None) -> str | None:
	"""The "Contact" link. Nothing is hard-coded: set site config `nxerp_support_url` (any mailto:, https://
	or site-relative link) or `nxerp_support_email` (opens a Gmail compose window). Neither set = no link."""
	custom = (frappe.conf.get("nxerp_support_url") or "").strip()
	if custom.lower().startswith(("mailto:", "https://", "http://", "/")):
		return custom
	email = (frappe.conf.get("nxerp_support_email") or "").strip()
	if not email or "@" not in email:
		return None
	query = urlencode(
		{"view": "cm", "fs": 1, "to": email, "su": f"{subject_name or PLATFORM_NAME} IT Support"},
		quote_via=quote,
	)
	return f"https://mail.google.com/mail/?{query}"
