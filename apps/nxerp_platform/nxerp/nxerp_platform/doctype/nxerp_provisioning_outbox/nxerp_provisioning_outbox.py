"""One pending, sent or failed call from the identity site to an app site (see nxerp/federation/outbox.py).

Written only by the federation code, in the same transaction as the grant change that caused it. Rows hold ids and a short error kind:
never a token, a secret, a password or a response body.
"""

from frappe.model.document import Document


class NXERPProvisioningOutbox(Document):
	pass
