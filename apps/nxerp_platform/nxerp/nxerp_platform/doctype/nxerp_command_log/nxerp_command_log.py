"""One applied command (nxerp/shared/command.py). The unique `idempotency_key` makes a repeat return the stored result instead of applying
again. Rows hold ids, the command name and the answer: never a field value. A daily job removes rows older than 24 hours."""

from frappe.model.document import Document


class NXERPCommandLog(Document):
	pass
