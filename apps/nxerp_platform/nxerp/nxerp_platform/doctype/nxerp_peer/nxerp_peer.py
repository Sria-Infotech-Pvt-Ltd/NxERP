"""Where another NXERP site lives and the key to call it (ADR-003 amendment 2, Phase 6).

One record per app site, kept on the identity site. `origin` is the only address people may be redirected to
(nxerp.routing); `internal_url`, `site_name` and the credentials are what the identity site uses to call the
app site's provisioning API (nxerp.federation). The two secrets are Password fields: read them only with
`get_decrypted_password` (`secret()` below), never from the document and never into a log.
Nothing here is used unless the site config key `nxerp_site_role` is set.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password

from nxerp import registry


class NXERPPeer(Document):
	def validate(self):
		self.app_key = (self.app_key or "").strip()
		if not any(entry.key == self.app_key for entry in registry.get_registry()):
			frappe.throw(_("{0} is not an application known to the NXERP registry").format(self.app_key))

		origin = registry.normalise_origin((self.origin or "").strip())
		if not origin:
			frappe.throw(
				_(
					"Origin must be https://host (no path, no user name, no trailing dot); http is accepted only on a developer site"
				)
			)
		self.origin = origin

		if self.internal_url:
			self.internal_url = self.internal_url.strip().rstrip("/")
			if not self.internal_url.startswith(("http://", "https://")) or " " in self.internal_url:
				frappe.throw(_("Internal URL must start with http:// or https://"))
		self.site_name = (self.site_name or "").strip()
		self.api_key = (self.api_key or "").strip()
		if self.enabled and not (self.internal_url and self.site_name and self.api_key):
			frappe.throw(_("An enabled peer needs Internal URL, Site Name and API Key"))


def secret(app_key: str, fieldname: str = "api_secret") -> str:
	"""The decrypted `api_secret` or `webhook_secret` of a peer. The one place the platform reads them."""
	if fieldname not in ("api_secret", "webhook_secret"):
		frappe.throw(_("Not a secret field"))
	return get_decrypted_password("NXERP Peer", app_key, fieldname, raise_exception=False) or ""
