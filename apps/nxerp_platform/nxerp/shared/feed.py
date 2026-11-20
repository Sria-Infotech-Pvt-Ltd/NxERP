"""The feed API: how the projector reads an owner's changes. Whitelisted, role-limited, read-only except `ack`.

Methods (all under `nxerp.shared.feed.`): `head`, `pull`, `ack`, `digest`, `snapshot`, `snapshot_by_ids`.
The caller is a dedicated service user holding the role `NXERP Shared Feed Reader`, authenticating with Frappe's API key
and secret (`Authorization: token key:secret`). No method takes SQL, a DocType name or a field name from the caller: the
entity type selects an ownership contract, and everything returned is built from that contract's fields only.

The feed is empty unless the site sets `nxerp_shared_publish`.

Errors are structured and carry no stack trace: 403 (no role), 422 (a bad argument, `FeedError`), 500 with a generic
message if a live document cannot be projected, 503 if the relay lock is held (`relay.RelayBusy`). A missing or wrong key
is answered by Frappe itself (403 without a token, 401 with a wrong secret).

`ack` is a POST: Frappe commits only POST, PUT, PATCH and DELETE requests, so an acknowledgement sent as a GET would
return 200 and be rolled back. Reads accept GET.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime, time_diff_in_seconds

from nxerp.shared import digest as projection
from nxerp.shared import outbox, registry

MAX_LIMIT = 1000
DEFAULT_PULL_LIMIT = 1000
DEFAULT_PAGE_LIMIT = 500
MAX_ID_LENGTH = 140


class FeedError(frappe.ValidationError):
	"""A bad argument (HTTP 422)."""

	http_status_code = 422


class FeedProjectionError(frappe.ValidationError):
	"""A live document could not be projected through its contract (HTTP 500, generic message)."""

	http_status_code = 500


def _require_reader() -> None:
	"""Only the feed service role (and Administrator, who holds every role).

	Not `frappe.only_for` alone: Frappe's `only_for` returns immediately while tests run (`flags.in_test`), so a test
	could never see the refusal. This check always applies; `only_for` is kept as the standard guard."""
	frappe.only_for(outbox.FEED_ROLE)
	if frappe.session.user == "Guest" or outbox.FEED_ROLE not in frappe.get_roles():
		raise frappe.PermissionError(_("Not permitted"))


def _int(value, name: str, minimum: int = 0, maximum: int | None = None) -> int:
	if isinstance(value, bool):
		raise FeedError(_("{0} must be an integer").format(name))
	try:
		number = int(value)
	except TypeError, ValueError:
		raise FeedError(_("{0} must be an integer").format(name))
	if number < minimum or (maximum is not None and number > maximum):
		raise FeedError(_("{0} is out of range").format(name))
	return number


def _text(value, name: str, allow_empty: bool = True) -> str:
	if value is None:
		value = ""
	if not isinstance(value, str) or len(value) > MAX_ID_LENGTH or (not allow_empty and not value):
		raise FeedError(_("{0} is not valid").format(name))
	return value


def _datetime(value, name: str):
	if value in (None, ""):
		return None
	try:
		return get_datetime(value)
	except TypeError, ValueError:
		raise FeedError(_("{0} is not a date and time").format(name))


def _stamp(value) -> str:
	return get_datetime(value).strftime(projection.DATETIME_FORMAT)


def _contract_for(entity_type) -> dict:
	"""The active contract this site owns for `entity_type`; anything else is a 422, never a field or table name."""
	if not isinstance(entity_type, str):
		raise FeedError(_("entity_type is not valid"))
	contract = registry.get_contract(entity_type)
	if (
		not contract
		or contract["status"] != "active"
		or contract["owner_app"] not in frappe.get_installed_apps()
	):
		raise FeedError(_("Unknown entity_type"))
	return contract


def _tenant(contract: dict, entity_id: str) -> str:
	tenant = contract["tenant"]
	return tenant["value"] if tenant["mode"] == "constant" else entity_id


def _envelope(row) -> dict:
	"""One outbox row as the event envelope (nxerp/shared/envelope_schema.json)."""
	contract = registry.get_contract(row.entity_type)
	return {
		"event_id": row.name,
		"seq": row.seq,
		"source_app": row.source_app,
		"entity_type": row.entity_type,
		"entity_id": row.entity_id,
		"op": row.op,
		"contract_version": row.contract_version,
		"source_modified": _stamp(row.source_modified),
		"tenant_id": _tenant(contract, row.entity_id) if contract else "",
		"payload": json.loads(row.payload) if row.payload else None,
	}


def _project(contract: dict, name: str) -> tuple:
	doc = frappe.get_doc(contract["source_doctype"], name)
	try:
		return doc, projection.project(contract, doc)
	except (projection.ProjectionError, KeyError, AttributeError, TypeError, ValueError) as exc:
		frappe.logger("nxerp_shared", allow_site=True).warning(
			"feed could not project entity=%s id=%s reason=%s",
			contract["entity_type"],
			name,
			type(exc).__name__,
		)
		raise FeedProjectionError(_("An entity could not be read"))


@frappe.whitelist(methods=["GET"])
def head() -> dict:
	"""Where the feed stands: the highest sequence, how many rows wait for a sequence, how old the oldest unacknowledged row is."""
	_require_reader()
	return feed_head()


def feed_head() -> dict:
	"""The head without the reader check: for the owner's own operator tools (nxerp.cutover)."""
	empty = {"max_seq": 0, "pending_count": 0, "oldest_pending_age_seconds": 0, "acked_through": 0}
	if not outbox.is_enabled():
		return empty
	max_seq, pending, oldest, acked = frappe.db.sql(
		"SELECT COALESCE(MAX(seq), 0), COALESCE(SUM(status = 'pending'), 0), "
		"MIN(CASE WHEN status <> 'acked' THEN creation END), "
		"COALESCE(MAX(CASE WHEN status = 'acked' THEN seq END), 0) "
		"FROM `tabNXERP Outbox Event`"
	)[0]
	return {
		"max_seq": cint(max_seq),
		"pending_count": cint(pending),
		"oldest_pending_age_seconds": int(time_diff_in_seconds(now_datetime(), oldest)) if oldest else 0,
		"acked_through": cint(acked),
	}


@frappe.whitelist(methods=["GET"])
def pull(after_seq=0, limit=DEFAULT_PULL_LIMIT) -> dict:
	"""Events with `seq` greater than `after_seq`, in sequence order, as envelopes. Resumable: ask again from `next_seq`."""
	_require_reader()
	after = _int(after_seq, "after_seq")
	limit = _int(limit, "limit", minimum=1, maximum=MAX_LIMIT)
	if not outbox.is_enabled():
		return {"events": [], "next_seq": after}
	rows = frappe.db.sql(
		"SELECT name, seq, source_app, entity_type, entity_id, op, contract_version, source_modified, payload "
		"FROM `tabNXERP Outbox Event` WHERE seq > %s ORDER BY seq LIMIT %s",
		(after, limit),
		as_dict=True,
	)
	events = [_envelope(row) for row in rows]
	return {"events": events, "next_seq": events[-1]["seq"] if events else after}


@frappe.whitelist(methods=["POST"])
def ack(through_seq) -> dict:
	"""Mark every sequenced event up to `through_seq` acknowledged. Idempotent; never lowers; never deletes."""
	_require_reader()
	through = _int(through_seq, "through_seq")
	if not outbox.is_enabled():
		return {"acked_through": 0, "acked": 0}
	head_seq = cint(frappe.db.sql("SELECT COALESCE(MAX(seq), 0) FROM `tabNXERP Outbox Event`")[0][0])
	if through > head_seq:
		raise FeedError(_("through_seq is beyond the head of the feed"))
	frappe.db.sql(
		"UPDATE `tabNXERP Outbox Event` SET status = 'acked', acked_at = %s "
		"WHERE seq IS NOT NULL AND seq <= %s AND status = 'claimed'",
		(now_datetime(), through),
	)
	changed = cint(frappe.db.sql("SELECT ROW_COUNT()")[0][0])
	acked = cint(
		frappe.db.sql("SELECT COALESCE(MAX(seq), 0) FROM `tabNXERP Outbox Event` WHERE status = 'acked'")[0][
			0
		]
	)
	return {"acked_through": acked, "acked": changed}


def _live_names(contract: dict, after_id: str, limit: int, modified_since=None) -> list:
	filters = []
	if after_id:
		filters.append(["name", ">", after_id])
	if modified_since:
		filters.append(["modified", ">=", modified_since])
	return frappe.get_all(
		contract["source_doctype"],
		filters=filters,
		pluck="name",
		order_by="name asc",
		limit_page_length=limit,
	)


@frappe.whitelist(methods=["GET"])
def digest(entity_type, modified_since=None, after_id="", limit=DEFAULT_PAGE_LIMIT) -> dict:
	"""(entity_id, source_modified, deleted, payload_hash) for live documents, by name, optionally only those modified since.

	`deleted` is always 0 here: a digest is built from live documents, so a deletion is found by comparing id sets
	(the nightly full compare), not listed."""
	_require_reader()
	since = _datetime(modified_since, "modified_since")
	after = _text(after_id, "after_id")
	limit = _int(limit, "limit", minimum=1, maximum=MAX_LIMIT)
	if not outbox.is_enabled():
		_contract_for_disabled_ok(entity_type)
		return {"items": [], "next_after_id": None}
	contract = _contract_for(entity_type)
	items = []
	for name in _live_names(contract, after, limit, since):
		doc, payload = _project(contract, name)
		items.append(
			{
				"entity_id": name,
				"source_modified": _stamp(doc.modified),
				"deleted": 0,
				"payload_hash": projection.payload_hash(payload),
			}
		)
	return {"items": items, "next_after_id": items[-1]["entity_id"] if len(items) == limit else None}


def _contract_for_disabled_ok(entity_type) -> None:
	"""With the feed off the answer is empty, but a malformed argument is still a 422."""
	if not isinstance(entity_type, str):
		raise FeedError(_("entity_type is not valid"))


@frappe.whitelist(methods=["GET"])
def snapshot(entity_type, after_id="", limit=DEFAULT_PAGE_LIMIT) -> dict:
	"""The contract payload of live documents, by name, a page at a time."""
	_require_reader()
	after = _text(after_id, "after_id")
	limit = _int(limit, "limit", minimum=1, maximum=MAX_LIMIT)
	if not outbox.is_enabled():
		_contract_for_disabled_ok(entity_type)
		return {"items": [], "next_after_id": None}
	contract = _contract_for(entity_type)
	items = []
	for name in _live_names(contract, after, limit):
		doc, payload = _project(contract, name)
		items.append({"entity_id": name, "source_modified": _stamp(doc.modified), "payload": payload})
	return {"items": items, "next_after_id": items[-1]["entity_id"] if len(items) == limit else None}


@frappe.whitelist(methods=["GET", "POST"])
def snapshot_by_ids(entity_type, ids) -> dict:
	"""The contract payload of the listed documents that exist, and the ids that do not (at most 1000 ids)."""
	_require_reader()
	if isinstance(ids, str):
		try:
			ids = json.loads(ids)
		except ValueError:
			raise FeedError(_("ids must be a list"))
	if not isinstance(ids, list) or len(ids) > MAX_LIMIT:
		raise FeedError(_("ids must be a list of at most {0}").format(MAX_LIMIT))
	ids = [_text(value, "an id", allow_empty=False) for value in ids]
	if not outbox.is_enabled():
		_contract_for_disabled_ok(entity_type)
		return {"items": [], "missing": []}
	contract = _contract_for(entity_type)
	existing = set(
		frappe.get_all(contract["source_doctype"], filters={"name": ["in", ids]}, pluck="name") if ids else []
	)
	items, missing = [], []
	for name in ids:
		if name not in existing:
			missing.append(name)
			continue
		doc, payload = _project(contract, name)
		items.append({"entity_id": name, "source_modified": _stamp(doc.modified), "payload": payload})
	return {"items": items, "missing": missing}
