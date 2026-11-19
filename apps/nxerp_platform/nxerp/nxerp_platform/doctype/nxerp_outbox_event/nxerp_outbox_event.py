"""One change to a shared entity, written in the owner's transaction and read in order through the feed API.

System-managed: rows are inserted only by `nxerp.shared.outbox.write_event` and updated only by the relay and the feed
(`nxerp.shared.relay`, `nxerp.shared.feed`). There are no document hooks on this DocType, so writing an event never
produces another event. Nobody creates or edits one by hand; System Manager can read."""

import frappe
from frappe.model.document import Document


class NXERPOutboxEvent(Document):
	pass


def on_doctype_update():
	"""Composite indexes the relay and the feed use (a single-field `unique` on seq is declared in the JSON)."""
	frappe.db.add_index("NXERP Outbox Event", ["status", "creation"], "nxerp_outbox_status_creation")
	frappe.db.add_index("NXERP Outbox Event", ["entity_type", "entity_id"], "nxerp_outbox_entity")
