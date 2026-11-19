"""Writing to the shared entity tables: one statement shape for upsert, tombstone and owner-truth repair. No frappe.

The version rule (blueprint 2.6.4, verified on MariaDB 11.8 by scripts/check_shared_ddl.sh): an incoming row is applied only if its
stamp `(source_modified, last_seq)` is greater than the stored one, so a replay is a no-op, an older event never overwrites a newer
one and a late older upsert cannot resurrect a deleted row. The business columns and the other stamps are assigned first and
`last_seq` then `source_modified` last, because a column assigned earlier in ON DUPLICATE KEY UPDATE is already changed when a later
assignment reads it.

`force=True` is the repair rule: the owner's snapshot is the truth, so it is applied when its `source_modified` is not older than
the stored one (a tie applies: that is how a change the owner made without an event is copied over). It never goes the other way.

A delete is a tombstone: the business columns are set to NULL (personal data is removed when the owner deletes it) and `deleted_at`
carries the delete's stamp, so views hide it and a late older upsert cannot bring it back.
"""

import json

from nxerp.shared import payload as payload_module
from nxerp.shared_service import sqlutil
from nxerp.shared_service.schema.generate_columns import table_name

_CACHE: dict = {}

NEWER = "(VALUES(`source_modified`), VALUES(`last_seq`)) > (`source_modified`, `last_seq`)"
NEWER_OR_EQUAL_OWNER = "VALUES(`source_modified`) >= `source_modified`"


def field_names(contract: dict) -> list:
	return [field["shared"] for field in contract["fields"]]


def apply_sql(contract: dict, force: bool = False) -> str:
	"""The INSERT ... ON DUPLICATE KEY UPDATE for one entity table (identifiers come from the contract and are validated)."""
	fields = field_names(contract)
	key = (contract["entity_type"], tuple(fields), force)
	if key in _CACHE:
		return _CACHE[key]
	condition = NEWER_OR_EQUAL_OWNER if force else NEWER
	columns = [
		"source_app",
		"entity_id",
		"tenant_id",
		*fields,
		"source_modified",
		"last_seq",
		"contract_version",
		"deleted_at",
	]
	values = ["%s"] * len(columns)
	columns.append("synced_at")
	values.append("NOW(6)")
	assignments = []
	for column in ["tenant_id", *fields, "contract_version", "deleted_at", "synced_at"]:
		quoted = sqlutil.ident(column)
		assignments.append(f"{quoted} = IF({condition}, VALUES({quoted}), {quoted})")
	if force:
		assignments.append(
			f"`last_seq` = IF({condition}, GREATEST(`last_seq`, VALUES(`last_seq`)), `last_seq`)"
		)
	else:
		assignments.append(f"`last_seq` = IF({condition}, VALUES(`last_seq`), `last_seq`)")
	assignments.append(
		f"`source_modified` = IF({condition}, VALUES(`source_modified`), `source_modified`)"
	)  # last: see the module note
	parts = [
		"INSERT INTO ",
		sqlutil.ident(table_name(contract["entity_type"])),
		" (",
		", ".join(sqlutil.ident(c) for c in columns),
		") VALUES (",
		", ".join(values),
		") ON DUPLICATE KEY UPDATE ",
		", ".join(assignments),
	]
	_CACHE[key] = "".join(parts)
	return _CACHE[key]


def apply_row(
	cur,
	contract: dict,
	*,
	source_app: str,
	entity_id: str,
	tenant_id: str,
	payload,
	source_modified: str,
	last_seq: int,
	contract_version: int,
	deleted: bool = False,
	force: bool = False,
) -> int:
	"""Upsert (payload) or tombstone (deleted) one entity. Returns the affected-row count: 1 inserted, 2 changed, 0 no change."""
	values = [None if deleted or payload is None else payload.get(name) for name in field_names(contract)]
	cur.execute(
		apply_sql(contract, force),
		[
			source_app,
			entity_id,
			tenant_id,
			*values,
			source_modified,
			last_seq,
			contract_version,
			source_modified if deleted else None,
		],
	)
	return cur.rowcount


def payload_from_row(contract: dict, row: dict) -> dict:
	"""The owner-form payload of a shared row (what `nxerp/shared/digest.py` would produce for the same data), for hashing."""
	payload = {}
	for field in contract["fields"]:
		value = row.get(field["shared"])
		if value is None or value == "":
			payload[field["shared"]] = None
			continue
		kind = field["type"]
		if kind == "string":
			payload[field["shared"]] = str(value)
		elif kind in ("boolean", "integer"):
			payload[field["shared"]] = int(value)
		elif kind == "datetime":
			payload[field["shared"]] = (
				value.strftime(payload_module.DATETIME_FORMAT) if hasattr(value, "strftime") else str(value)
			)
		elif kind == "date":
			payload[field["shared"]] = (
				value.strftime(payload_module.DATE_FORMAT) if hasattr(value, "strftime") else str(value)
			)
	return payload


def row_hash(contract: dict, row: dict) -> str:
	return payload_module.payload_hash(payload_from_row(contract, row))


# ---- cursor and dead letters ---------------------------------------------------------------------------------


def get_cursor(cur, source: str) -> dict:
	cur.execute(
		"SELECT last_seq, last_event_id, snapshot_seq, state FROM sync_cursor WHERE source_app = %s",
		(source,),
	)
	row = cur.fetchone()
	return row or {"last_seq": 0, "last_event_id": None, "snapshot_seq": None, "state": "live"}


def set_cursor(
	cur, source: str, last_seq: int, last_event_id: str | None = None, state: str = "live", snapshot_seq=None
) -> None:
	cur.execute(
		"INSERT INTO sync_cursor (source_app, last_seq, last_event_id, snapshot_seq, state, updated_at) "
		"VALUES (%s, %s, %s, %s, %s, NOW(6)) ON DUPLICATE KEY UPDATE last_seq = VALUES(last_seq), "
		"last_event_id = VALUES(last_event_id), snapshot_seq = VALUES(snapshot_seq), state = VALUES(state), updated_at = NOW(6)",
		(source, last_seq, last_event_id, snapshot_seq, state),
	)


def set_state(cur, source: str, state: str) -> None:
	cur.execute(
		"INSERT INTO sync_cursor (source_app, last_seq, state, updated_at) VALUES (%s, 0, %s, NOW(6)) "
		"ON DUPLICATE KEY UPDATE state = VALUES(state), updated_at = NOW(6)",
		(source, state),
	)


def _short(value, size: int) -> str:
	text = "-" if value is None or value == "" else str(value)
	return text[:size]


def dead_letter(cur, source: str, event: dict, reason: str, attempts: int = 1) -> None:
	"""Store an event that cannot be applied, with the reason, WITHOUT its payload values: only the payload's field names are kept,
	so an invalid event cannot smuggle a field outside the contract (a tax id, say) into the shared database."""
	envelope = {k: v for k, v in event.items() if k != "payload"} if isinstance(event, dict) else {}
	payload = event.get("payload") if isinstance(event, dict) else None
	envelope["payload_fields"] = sorted(payload) if isinstance(payload, dict) else None
	seq = event.get("seq") if isinstance(event, dict) else None
	cur.execute(
		"INSERT INTO sync_dead_letter (event_id, source_app, entity_type, entity_id, seq, event_json, error_text, attempts, created_at) "
		"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(6)) ON DUPLICATE KEY UPDATE attempts = attempts + 1, error_text = VALUES(error_text)",
		(
			_short(event.get("event_id") if isinstance(event, dict) else None, 64)
			if isinstance(event, dict) and event.get("event_id")
			else _short(f"{source}-seq-{seq}", 64),
			source,
			_short(event.get("entity_type") if isinstance(event, dict) else None, 40),
			_short(event.get("entity_id") if isinstance(event, dict) else None, 140),
			seq if isinstance(seq, int) and not isinstance(seq, bool) else None,
			json.dumps(envelope, default=str, sort_keys=True),
			str(reason)[:2000],
			attempts,
		),
	)
