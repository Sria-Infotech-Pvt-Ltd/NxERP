"""The owner-side command API (Phase 7A): the only way another app may ask this site to change a shared entity.

One whitelisted method, `apply`, driven entirely by the ownership contracts (`nxerp/shared/contracts/*.json`). Everything below is enforced on the
server, in ONE transaction, and cannot be skipped by a caller:

  1. authorisation: the calling service user holds the role "NXERP Command Caller", and the app it stands for (the site config key
     `nxerp_command_callers`, {service user: app key}, set by the site owner) is in the command's `callers`. No mapping, no access;
  2. a per-caller rate limit (RATE_LIMIT_PER_MINUTE per minute);
  3. the entity, the command and the fields come from the contract: a DocType or field name that is not in it is never accepted, and a field
     outside the command's `writable_fields` is refused (422);
  4. an idempotency row is written FIRST (unique key): a repeat returns the stored result and changes nothing;
  5. the acting user (a person on THIS site) is applied with `frappe.set_user`, so the owner's own permissions and validations run: it must
     exist, be enabled, hold the command's `needs_role`, and may never be Administrator or Guest. `ignore_permissions` is never used;
  6. an `expected_version` that differs from the document's `modified` is refused (409);
  7. `doc.save()`: the Phase 3 capture hook publishes the change to the outbox in the same transaction. This code never publishes.

Any error rolls back the document change AND the log row (a savepoint) and answers a structured envelope {"error": code, "message": ...}
with the HTTP status in `frappe.local.response.http_status_code`; the envelope is the method's return value (Frappe puts it under
`message`). A retry with the same key after any 5xx is safe because a failed call stores nothing. Field values are never logged.

Off unless a contract declares commands, the caller's service user has the role and the site config maps it to an app.
"""

import json
import re
import time

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime, validate_email_address

from nxerp.shared import payload, registry

CALLER_ROLE = "NXERP Command Caller"
CALLERS_KEY = "nxerp_command_callers"
LOG_DOCTYPE = "NXERP Command Log"
RATE_LIMIT_PER_MINUTE = 600
KEY_PATTERN = re.compile(r"^[A-Za-z0-9:_.|@+-]{8,140}$")
SOURCE_FIELD = re.compile(r"^[a-z_][a-z0-9_]*$")
MAX_VALUE_LENGTH = 500
RETENTION_HOURS = 24
SAVEPOINT = "nxerp_command"
RESERVED_USERS = ("Administrator", "Guest")


class CommandError(Exception):
	def __init__(self, status: int, code: str, message: str):
		super().__init__(message)
		self.status, self.code, self.message = status, code, message


# ---- derived fields: a shared field that is not a plain column of the owner's DocType ---------------------------------------------------


def _set_full_name(doc, value):
	first, _sep, last = " ".join(str(value).split()).partition(" ")
	if not first:
		raise CommandError(422, "validation_failed", "full_name must not be empty")
	doc.first_name, doc.middle_name, doc.last_name = first, "", last


def _set_primary_row(doc, table: str, key_field: str, primary_flag: str, value, check=None):
	value = (str(value) if value is not None else "").strip()
	if not value:
		raise CommandError(422, "validation_failed", f"{key_field} must not be empty")
	if check and not check(value):
		raise CommandError(422, "validation_failed", f"{key_field} is not valid")
	rows = doc.get(table) or []
	row = next((r for r in rows if r.get(primary_flag)), None) or (rows[0] if rows else None)
	if row:
		row.set(key_field, value)
		row.set(primary_flag, 1)
	else:
		doc.append(table, {key_field: value, primary_flag: 1})


def _set_email(doc, value):
	_set_primary_row(doc, "email_ids", "email_id", "is_primary", value, check=validate_email_address)


def _set_phone(doc, value):
	_set_primary_row(doc, "phone_nos", "phone", "is_primary_phone", value)


DERIVED = {
	("contact", "full_name"): _set_full_name,
	("contact", "email"): _set_email,
	("contact", "phone"): _set_phone,
}


# ---- helpers ------------------------------------------------------------------------------------------------------------------------------


def _stamp(value) -> str:
	return get_datetime(value).strftime(payload.DATETIME_FORMAT)


def _fail(status: int, code: str, message: str):
	raise CommandError(status, code, message)


def _rate_limit(caller: str) -> None:
	"""At most RATE_LIMIT_PER_MINUTE calls a minute per service user. A cache that cannot answer does not block work (it is logged)."""
	try:
		key = frappe.cache.make_key(f"nxerp_command_rate:{caller}:{int(time.time() // 60)}")
		count = frappe.cache.incrby(key, 1)
		if count == 1:
			frappe.cache.expire(key, 120)
	except Exception as exc:
		frappe.logger("nxerp_shared", allow_site=True).warning(
			"command rate limit unavailable reason=%s", type(exc).__name__
		)
		return
	if count > RATE_LIMIT_PER_MINUTE:
		_fail(429, "rate_limited", f"At most {RATE_LIMIT_PER_MINUTE} commands a minute per caller")


def _caller_app(caller: str) -> str | None:
	mapping = frappe.conf.get(CALLERS_KEY) or {}
	return mapping.get(caller) if isinstance(mapping, dict) else None


def _parse_fields(raw, command: dict) -> dict:
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			_fail(422, "bad_request", "fields must be a JSON object")
	if not isinstance(raw, dict) or not raw:
		_fail(422, "bad_request", "fields must be a non-empty object")
	for name, value in raw.items():
		if name not in command["writable_fields"]:
			_fail(422, "field_not_writable", f"'{name}' is not a writable field of {command['name']}")
		if not (
			value is None
			or isinstance(value, bool | int | float)
			or (isinstance(value, str) and len(value) <= MAX_VALUE_LENGTH)
		):
			_fail(
				422,
				"bad_request",
				f"the value of '{name}' must be text of at most {MAX_VALUE_LENGTH} characters, a number or a boolean",
			)
	return raw


def _stored_result(key: str, caller_app: str, entity_type: str, entity_id: str, command: str):
	row = frappe.db.get_value(
		LOG_DOCTYPE,
		{"idempotency_key": key},
		["caller_app", "entity_type", "entity_id", "command", "result"],
		as_dict=True,
	)
	if not row:
		return None
	if (row.caller_app, row.entity_type, row.entity_id, row.command) != (
		caller_app,
		entity_type,
		entity_id,
		command,
	):
		_fail(409, "idempotency_key_reused", "This idempotency key was used for a different request")
	return json.loads(row.result) if row.result else {"ok": True}


def _check_acting_user(user, command: dict) -> str:
	if not isinstance(user, str) or not user or user in RESERVED_USERS:
		_fail(403, "acting_user_invalid", "A person on this site must be named as the acting user")
	row = frappe.db.get_value("User", user, ["enabled", "name"], as_dict=True)
	if not row or not row.enabled:
		_fail(403, "acting_user_invalid", "The acting user does not exist or is disabled on this site")
	if command["needs_role"] not in frappe.get_roles(user):
		_fail(403, "acting_user_forbidden", "The acting user may not use this command")
	return user


def _apply_fields(doc, contract: dict, fields: dict) -> None:
	for shared_name, value in fields.items():
		handler = DERIVED.get((contract["entity_type"], shared_name))
		if handler:
			handler(doc, value)
			continue
		source = next((f["source"] for f in contract["fields"] if f["shared"] == shared_name), None)
		if not source or not SOURCE_FIELD.match(source):
			_fail(422, "field_not_writable", f"'{shared_name}' cannot be written by a command")
		doc.set(source, value)


def _envelope(error: CommandError) -> dict:
	frappe.local.response["http_status_code"] = error.status
	return {"error": error.code, "message": error.message}


# ---- the method ----------------------------------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def apply(
	entity_type=None,
	entity_id=None,
	command=None,
	fields=None,
	expected_version=None,
	idempotency_key=None,
	acting_user=None,
):
	"""Apply one contract command as the acting user. See the module text and docs/architecture/command-api-v1.md."""
	caller = frappe.session.user
	frappe.db.savepoint(SAVEPOINT)
	try:
		return _apply(
			caller, entity_type, entity_id, command, fields, expected_version, idempotency_key, acting_user
		)
	except CommandError as error:
		frappe.db.rollback(save_point=SAVEPOINT)
		return _envelope(error)
	except frappe.PermissionError:
		frappe.db.rollback(save_point=SAVEPOINT)
		return _envelope(CommandError(403, "forbidden", "The acting user may not change this record"))
	except frappe.DoesNotExistError:
		frappe.db.rollback(save_point=SAVEPOINT)
		return _envelope(CommandError(404, "not_found", "No such record"))
	except frappe.ValidationError as exc:
		frappe.db.rollback(save_point=SAVEPOINT)
		# the owner's own validation message (it never contains the submitted values by design of the owner; trimmed anyway)
		return _envelope(CommandError(422, "validation_failed", frappe.utils.strip_html(str(exc))[:300]))
	except Exception as exc:
		frappe.db.rollback(save_point=SAVEPOINT)
		frappe.logger("nxerp_shared", allow_site=True).error(
			"command failed entity=%s command=%s reason=%s", entity_type, command, type(exc).__name__
		)
		return _envelope(
			CommandError(
				503, "unavailable", "The command could not be applied; retry with the same idempotency key"
			)
		)
	finally:
		frappe.set_user(caller)


def _apply(caller, entity_type, entity_id, command_name, fields, expected_version, key, acting_user):
	# 1. authorisation
	if caller == "Guest" or CALLER_ROLE not in frappe.get_roles(caller):
		_fail(403, "forbidden", "This service user may not call commands")
	_rate_limit(caller)
	if not all(isinstance(x, str) and x for x in (entity_type, entity_id, command_name)):
		_fail(422, "bad_request", "entity_type, entity_id and command are required")
	if len(entity_id) > 140:
		_fail(422, "bad_request", "entity_id is too long")
	command = registry.command_for(entity_type, command_name)
	contract = registry.get_contract(entity_type)
	if command is None or contract is None:
		_fail(404, "unknown_command", "No such entity or command")
	if contract["owner_app"] not in frappe.get_installed_apps():
		_fail(404, "unknown_command", "This site does not own that entity")
	app = _caller_app(caller)
	if not app or app not in command["callers"]:
		_fail(403, "forbidden", "This caller may not use this command")
	if not isinstance(key, str) or not KEY_PATTERN.match(key):
		_fail(422, "bad_idempotency_key", "A valid idempotency key is required")
	values = _parse_fields(fields, command)

	# 2. a repeat returns the first answer and changes nothing; otherwise the row is written first (unique), in this transaction
	stored = _stored_result(key, app, entity_type, entity_id, command["name"])
	if stored is not None:
		return stored
	log = frappe.get_doc(
		{
			"doctype": LOG_DOCTYPE,
			"idempotency_key": key,
			"caller_app": app,
			"caller_user": caller,
			"entity_type": entity_type,
			"entity_id": entity_id,
			"command": command["name"],
		}
	)
	try:
		log.insert(ignore_permissions=True)
	except (
		frappe.DuplicateEntryError,
		frappe.UniqueValidationError,
	):  # a concurrent identical request committed first
		frappe.db.rollback(save_point=SAVEPOINT)
		frappe.db.savepoint(SAVEPOINT)
		stored = _stored_result(key, app, entity_type, entity_id, command["name"])
		if stored is not None:
			return stored
		_fail(409, "in_progress", "An identical request is being processed; retry")

	# 3. the acting user is applied: the owner's permissions and validations run as that person
	user = _check_acting_user(acting_user, command)
	frappe.set_user(user)
	doc = frappe.get_doc(contract["source_doctype"], entity_id)
	doc.check_permission("write")
	if expected_version not in (None, "") and _stamp(expected_version) != _stamp(doc.modified):
		_fail(409, "version_conflict", "The record changed since it was read")
	_apply_fields(doc, contract, values)
	doc.save()  # never ignore_permissions; the capture hook publishes the change in this transaction

	result = {"ok": True, "source_modified": _stamp(doc.modified)}
	frappe.db.set_value(LOG_DOCTYPE, log.name, "result", json.dumps(result), update_modified=False)
	return result


def prune_log() -> int:
	"""Daily (scheduler cron): remove log rows older than RETENTION_HOURS. A retry later than that is a new command."""
	cutoff = add_to_date(now_datetime(), hours=-RETENTION_HOURS)
	count = frappe.db.count(LOG_DOCTYPE, {"creation": ("<", cutoff)})
	if count:
		frappe.db.delete(LOG_DOCTYPE, {"creation": ("<", cutoff)})
	return count
