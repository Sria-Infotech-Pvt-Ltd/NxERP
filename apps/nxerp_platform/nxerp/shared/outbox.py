"""Write one event to the outbox, inside the caller's database transaction.

This is the only place that inserts an NXERP Outbox Event. It never commits, never enqueues and never calls out:
the row is committed or rolled back together with the business change that caused it (the transactional outbox),
so a committed change cannot be lost and a rolled-back change cannot be published.

Everything is off unless the site config key `nxerp_shared_publish` is set. `nxerp_shared_publish_strict` makes a
capture mistake (a contract that cannot project its document) raise instead of writing a `resync` event; it is meant
for tests and CI.
"""

import uuid

import frappe

from nxerp.shared import digest

DOCTYPE = "NXERP Outbox Event"
FEED_ROLE = "NXERP Shared Feed Reader"  # the service role that may call the feed API (nxerp/shared/feed.py)
OPS = ("upsert", "delete", "resync")


def is_enabled() -> bool:
	return bool(frappe.conf.get("nxerp_shared_publish"))


def is_strict() -> bool:
	return bool(frappe.conf.get("nxerp_shared_publish_strict"))


def write_event(
	entity_type: str,
	entity_id: str,
	op: str,
	source_modified,
	payload: dict | None,
	contract_version: int,
	source_app: str,
) -> str:
	"""Insert one pending event in the current transaction and return its id.

	`upsert` carries the payload; `delete` and `resync` carry none. The insert is a plain database insert
	(`db_insert`), not `doc.insert()`: no validation, version, search or document hooks run for a system row, and
	a database error propagates so that the business change fails with it ("both or neither")."""
	if op not in OPS:
		raise ValueError(f"unknown outbox op {op!r}")
	if (op == "upsert") != (payload is not None):
		raise ValueError("an upsert needs a payload; a delete or resync carries none")

	event = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"name": str(uuid.uuid7()),
			"source_app": source_app,
			"entity_type": entity_type,
			"entity_id": str(entity_id),
			"op": op,
			"contract_version": contract_version,
			"source_modified": source_modified,
			"payload": digest.canonical_json(payload) if payload is not None else None,
			"payload_hash": digest.payload_hash(payload) if payload is not None else None,
			"status": "pending",
		}
	)
	event.set_user_and_timestamp()
	event.db_insert()
	return event.name
