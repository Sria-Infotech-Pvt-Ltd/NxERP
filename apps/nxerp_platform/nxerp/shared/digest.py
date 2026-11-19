"""The projection of a document through its ownership contract, and the hash of the result.

One function, `project`, builds the payload from the contract's allow-listed fields and nothing else. The capture
hooks (`capture.py`) use it to fill the outbox and, in the feed (3C), `digest` and `snapshot` use the same function,
so what is published, what is compared and what is re-read can never differ.

Payload values are JSON-safe: strings, ints, None. Booleans are 0 or 1, dates are `YYYY-MM-DD`, datetimes are
`YYYY-MM-DD HH:MM:SS.ffffff`. Nothing outside the contract's `fields` is ever read into the payload.
"""

import hashlib
import json

import frappe
from frappe.utils import cint, get_datetime, getdate

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
DATE_FORMAT = "%Y-%m-%d"


class ProjectionError(Exception):
	"""The document cannot be projected through its contract (a source field is missing, or a derivation fails).

	This is a contract mismatch, not a database failure: capture turns it into a `resync` event (or raises in strict
	mode). Database errors are never wrapped in it and always propagate."""


def _first_row(doc, table: str, **match):
	for row in doc.get(table) or []:
		if all(row.get(key) == value for key, value in match.items()):
			return row
	return None


def _contact_customer_id(doc):
	row = _first_row(doc, "links", link_doctype="Customer")
	return row.link_name if row else None


def _contact_email(doc):
	row = _first_row(doc, "email_ids", is_primary=1)
	return row.email_id if row else None


def _contact_phone(doc):
	row = _first_row(doc, "phone_nos", is_primary_phone=1)
	return row.phone if row else None


def _ticket_customer_id(doc):
	"""HD Ticket.customer is an HD Customer; the shared id is the ERPNext Customer it is mapped to (may be empty)."""
	if not doc.get("customer"):
		return None
	return frappe.db.get_value("HD Customer", doc.customer, "erpnext_customer") or None


def _combine(date_value, time_value):
	if not date_value:
		return None
	text = f"{getdate(date_value).strftime(DATE_FORMAT)} {time_value or '00:00:00'}"
	return get_datetime(text)


def _ticket_opened_at(doc):
	return _combine(doc.get("opening_date"), doc.get("opening_time"))


def _ticket_resolved_at(doc):
	return _combine(doc.get("resolution_date"), doc.get("resolution_time"))


def _ticket_assignee(doc):
	raw = doc.get("_assign")
	if not raw:
		return None
	try:
		assigned = json.loads(raw)
	except TypeError, ValueError:
		raise ProjectionError("_assign is not valid JSON")
	return assigned[0] if assigned else None


def _employee_active(doc):
	return 1 if doc.get("status") == "Active" else 0


# (entity_type, shared field) -> function(doc) for the fields a contract marks `derived`
DERIVED = {
	("contact", "customer_id"): _contact_customer_id,
	("contact", "email"): _contact_email,
	("contact", "phone"): _contact_phone,
	("ticket_summary", "customer_id"): _ticket_customer_id,
	("ticket_summary", "opened_at"): _ticket_opened_at,
	("ticket_summary", "resolved_at"): _ticket_resolved_at,
	("ticket_summary", "assignee_user_id"): _ticket_assignee,
	("employee_ref", "active"): _employee_active,
}


def _coerce(value, field: dict):
	"""A source value as the contract's type; None stays None."""
	if value is None or value == "":
		return None
	kind = field["type"]
	try:
		if kind == "string":
			return str(value)
		if kind in ("boolean", "integer"):
			return cint(value)
		if kind == "datetime":
			return get_datetime(value).strftime(DATETIME_FORMAT)
		if kind == "date":
			return getdate(value).strftime(DATE_FORMAT)
	except (TypeError, ValueError) as exc:
		raise ProjectionError(f"{field['shared']}: cannot read the value as {kind}") from exc
	raise ProjectionError(f"{field['shared']}: unknown type {kind}")


def project(contract: dict, doc) -> dict:
	"""The contract payload of `doc`: exactly the contract's shared fields, in contract order."""
	meta = frappe.get_meta(doc.doctype)
	payload = {}
	for field in contract["fields"]:
		shared = field["shared"]
		derive = DERIVED.get((contract["entity_type"], shared))
		if field.get("derived"):
			if derive is None:
				raise ProjectionError(f"{shared}: no derivation is defined for this derived field")
			value = derive(doc)
		elif meta.has_field(field["source"]) or field["source"] in ("name", "owner", "creation", "modified"):
			value = doc.get(field["source"])
		elif field.get("verify"):
			value = (
				None  # an unconfirmed source name the DocType does not have: shared as empty, not an error
			)
		else:
			raise ProjectionError(f"{shared}: source field {field['source']} is not in {doc.doctype}")
		payload[shared] = _coerce(value, field)
	return payload


def canonical_json(payload) -> str:
	return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_hash(payload) -> str:
	"""SHA-256 of the canonical JSON of a payload; reconciliation compares these, never values."""
	return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
