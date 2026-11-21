"""/404: "page not found" in the NXDESK look. Overrides `frappe/www/404`; the status code stays 404."""

from frappe import _

from nxerp import public_site

no_cache = 1


def get_context(context):
	context.http_status_code = 404
	public_site.base_context(context, title=_("Page not found"), description="")
	context.product = public_site.platform_hero()
	context.state_heading = _("Page not found")
	context.state_text = _("The page you are looking for does not exist or has moved.")
	context.state_href, context.state_label = "/", _("Back to Home")
	return context
