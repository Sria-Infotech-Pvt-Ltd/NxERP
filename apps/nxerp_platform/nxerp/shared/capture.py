"""Capture hooks: every committed change to a shared entity also lands in the outbox, in the same transaction.

`hooks.py` registers these three handlers, generated from the active ownership contracts (`registry.capture_events`),
on each contract's source DocType. Each handler returns at its first line unless the site config key
`nxerp_shared_publish` is set, so a site that has not switched the feature on behaves exactly as before.

What fires (measured on Frappe 16.53.0, docs/architecture-isolation/spike-publication.md):
- `on_change` fires for insert, save, submit and `doc.db_set`; it also fires during a delete, with `flags.in_delete`
  set, and is ignored then (the delete is published from `on_trash`);
- `on_trash` fires first on `frappe.delete_doc`;
- `after_rename` fires on `frappe.rename_doc`, which fires no `on_change`: a rename is published as a delete of the
  old id plus an upsert of the new one;
- `frappe.db.set_value`, `frappe.db.delete`, raw SQL and `bulk_insert` fire nothing (a known gap, covered by the
  Phase 4 reconciler, see docs/architecture-isolation/capture-notes.md).

Rules the handlers keep: no commit, no enqueue, no external call; the payload is the contract's fields only; a
database error always propagates (the business change fails with it); a payload that cannot be built becomes a
`resync` event (entity id only) and a log line, or raises when `nxerp_shared_publish_strict` is set. Log lines carry
entity ids and error class names, never field values.
"""

import frappe
from frappe.utils import now_datetime

from nxerp.shared import digest, outbox, registry

# what a projection mistake looks like; anything else (notably a database error) propagates untouched
PROJECTION_ERRORS = (digest.ProjectionError, KeyError, AttributeError, TypeError, ValueError)


def _contracts_for(doc) -> list:
	"""Active contracts this document is captured for, on this site: the owner app must be installed here."""
	if not outbox.is_enabled() or frappe.flags.in_install:
		return []
	installed = set(frappe.get_installed_apps())
	return [c for c in registry.contracts_for_doctype(doc.doctype) if c["owner_app"] in installed]


def _log(contract: dict, entity_id: str, exc: Exception) -> None:
	frappe.logger("nxerp_shared", allow_site=True).warning(
		"capture could not project entity=%s id=%s reason=%s",
		contract["entity_type"],
		entity_id,
		type(exc).__name__,
	)


def _publish_upsert(contract: dict, doc, entity_id: str, source_modified) -> None:
	try:
		payload = digest.project(contract, doc)
	except PROJECTION_ERRORS as exc:
		if outbox.is_strict():
			raise
		_log(contract, entity_id, exc)
		outbox.write_event(
			contract["entity_type"],
			entity_id,
			"resync",
			source_modified,
			None,
			contract["contract_version"],
			contract["owner_app"],
		)
		return
	outbox.write_event(
		contract["entity_type"],
		entity_id,
		"upsert",
		source_modified,
		payload,
		contract["contract_version"],
		contract["owner_app"],
	)


def _publish_delete(contract: dict, entity_id: str) -> None:
	outbox.write_event(
		contract["entity_type"],
		entity_id,
		"delete",
		now_datetime(),
		None,
		contract["contract_version"],
		contract["owner_app"],
	)


def on_change(doc, method=None):
	if not outbox.is_enabled() or doc.flags.get("in_delete"):
		return
	for contract in _contracts_for(doc):
		_publish_upsert(contract, doc, doc.name, doc.modified)


def on_trash(doc, method=None):
	if not outbox.is_enabled():
		return
	for contract in _contracts_for(doc):
		_publish_delete(contract, doc.name)


def after_rename(doc, method=None, old=None, new=None, merge=False):
	if not outbox.is_enabled():
		return
	for contract in _contracts_for(doc):
		_publish_delete(contract, old)
		_publish_upsert(contract, doc, new, now_datetime())
