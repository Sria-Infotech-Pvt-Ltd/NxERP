"""/signup?app=<key>: create an account (split shell). Public. Creates nothing by itself: the form posts to
`nxerp.api.account.sign_up`, which is open to anyone (an administrator can close it with Frappe's own Disable Customer Signup; docs/features/signup-gate.md)."""

from frappe import PageDoesNotExistError, _, form_dict, session

from nxerp import public_site, registry
from nxerp.api.account import signup_available

no_cache = True


def get_context(context):
	key = form_dict.get("app")
	if not key:
		public_site.redirect(public_site.PRODUCTS_ROUTE)
	entry = registry.public_entry(key) if isinstance(key, str) else None
	if not entry:
		raise PageDoesNotExistError
	if session.user != "Guest":
		public_site.redirect(f"{public_site.GET_STARTED_ROUTE}?product={entry.key}")

	product = public_site.present(entry)
	public_site.base_context(
		context, title=_("Create your account | {0}").format(product["title"]), description=product["tagline"]
	)
	context.product = product
	context.available = signup_available()
