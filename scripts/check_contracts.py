"""Lint the shared-entity ownership contracts. Stdlib only.

Run with `python3 -I scripts/check_contracts.py` (on a Windows host without a `python3` shim: `python -I ...`).
With no argument it checks every contract in apps/nxerp_platform/nxerp/shared/contracts/. Pass one or more
files or folders to check those instead (used by the negative tests and by "Check 2.1" in the Phase 2 prompt).

Rules (every violation is one line on stderr; the exit code is 1 if there is any):

  C1  structure: the keys and types the schema requires (the full JSON Schema is also checked by the unit tests);
  C2  one contract per entity_type, and the file is named <entity_type>.json;
  C3  one owner_app per entity: a key in nxerp/registry.py APPS, or a planned owner (below) while status is "planned";
  C4  classes are S0, S1 or S2 only: S3 (finance, tax, payroll, credentials, health) never enters the shared layer;
  C5  deny-list: no field name (shared or source) contains password, secret, token, key, tax, salary, iban,
      bank, ssn or health. A reviewed exception needs a `deny_list_exception` note on the field AND a line in
      EXCEPTIONS below, never silently;
  C6  consumers are registered or planned apps and list only shared fields of this entity;
  C7  the id field is never a shared field, and writable_fields of a command are shared fields other than the id;
  C8  no module path of erpnext, helpdesk, telephony or payments appears in any contract value.

This file never imports the apps it checks, nor `frappe`: it parses nxerp/registry.py with `ast`.
"""

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORM = ROOT / "apps" / "nxerp_platform" / "nxerp"
CONTRACT_DIR = PLATFORM / "shared" / "contracts"
REGISTRY = PLATFORM / "registry.py"

# Owners that are not installed yet. Allowed ONLY while a contract's status is "planned". They are deliberately
# not added to nxerp/registry.py: a registry entry would make the app look installed (CLAUDE.md).
PLANNED_APPS = {"identity", "hrms", "project_management", "budget_management"}

CLASSES = {"S0", "S1", "S2"}
DENY_FRAGMENTS = ("password", "secret", "token", "key", "tax", "salary", "iban", "bank", "ssn", "health")
# (entity_type, shared field name) pairs the owner reviewed and accepted despite the deny-list. Empty on purpose.
EXCEPTIONS: set = set()
FORBIDDEN_MODULE_PATH = re.compile(r"\b(erpnext|helpdesk|telephony|payments)\.[A-Za-z_]")

REQUIRED = (
	"entity_type",
	"contract_version",
	"owner_app",
	"source_doctype",
	"id_field",
	"tenant",
	"fields",
	"excluded_by_design",
	"events",
	"consumers",
	"commands",
	"status",
)
ALLOWED_TOP = {*REQUIRED, "note"}
FIELD_REQUIRED = ("shared", "source", "class", "type")
FIELD_ALLOWED = {*FIELD_REQUIRED, "max_length", "derived", "verify", "note"}
FIELD_TYPES = {"string", "integer", "boolean", "datetime", "date"}
EVENTS = {"after_insert", "on_update", "on_change", "on_trash", "after_rename"}


def registry_keys(path: Path = REGISTRY) -> set:
	"""The `key=` of every AppEntry(...) in nxerp/registry.py, read with ast (no import, no frappe)."""
	keys = set()
	for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
		if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "AppEntry":
			for kw in node.keywords:
				if kw.arg == "key" and isinstance(kw.value, ast.Constant):
					keys.add(kw.value.value)
	return keys


def _strings(value):
	"""Every string inside a JSON value (keys of objects excluded)."""
	if isinstance(value, str):
		yield value
	elif isinstance(value, list):
		for item in value:
			yield from _strings(item)
	elif isinstance(value, dict):
		for item in value.values():
			yield from _strings(item)


def _deny_hit(name: str) -> str | None:
	lowered = name.lower()
	return next((fragment for fragment in DENY_FRAGMENTS if fragment in lowered), None)


def check_contract(contract, label: str, registered: set) -> list:
	"""Violations of one contract, as `label: message` lines."""
	errors: list = []

	def err(message: str) -> None:
		errors.append(f"{label}: {message}")

	if not isinstance(contract, dict):
		return [f"{label}: C1 a contract must be a JSON object"]
	for key in REQUIRED:
		if key not in contract:
			err(f"C1 missing required key '{key}'")
	for key in contract:
		if key not in ALLOWED_TOP:
			err(f"C1 unknown key '{key}'")
	if errors:
		return errors

	entity = contract["entity_type"]
	if not isinstance(entity, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", entity):
		err("C1 entity_type must be lower_snake_case")
		entity = str(entity)
	if (
		not isinstance(contract["contract_version"], int)
		or isinstance(contract["contract_version"], bool)
		or contract["contract_version"] < 1
	):
		err("C1 contract_version must be an integer >= 1")
	if contract["status"] not in ("active", "planned"):
		err("C1 status must be 'active' or 'planned'")
	tenant = contract["tenant"]
	if not isinstance(tenant, dict) or tenant.get("mode") not in ("constant", "self"):
		err("C1 tenant.mode must be 'constant' or 'self'")
	elif tenant["mode"] == "constant" and not tenant.get("value"):
		err("C1 tenant.mode 'constant' needs a value")
	for key in ("excluded_by_design", "events"):
		if not isinstance(contract[key], list):
			err(f"C1 {key} must be a list")
	for event in contract["events"] if isinstance(contract["events"], list) else []:
		if event not in EVENTS:
			err(f"C1 unknown event '{event}'")
	if not isinstance(contract["consumers"], dict):
		err("C1 consumers must be an object")
	if not isinstance(contract["commands"], list):
		err("C1 commands must be a list")
	if not isinstance(contract["fields"], list) or not contract["fields"]:
		return [*errors, f"{label}: C1 fields must be a non-empty list"]

	# C3 owner
	owner = contract["owner_app"]
	if owner in registered:
		pass
	elif owner in PLANNED_APPS:
		if contract["status"] != "planned":
			err(f"C3 owner_app '{owner}' is not installed, so status must be 'planned'")
	else:
		err(f"C3 owner_app '{owner}' is not an app in nxerp/registry.py or a known planned owner")

	# fields: C1, C4, C5
	shared_names: list = []
	for index, field in enumerate(contract["fields"]):
		if not isinstance(field, dict):
			err(f"C1 fields[{index}] must be an object")
			continue
		for key in FIELD_REQUIRED:
			if key not in field:
				err(f"C1 fields[{index}] missing '{key}'")
		for key in field:
			if key not in FIELD_ALLOWED:
				err(f"C1 fields[{index}] unknown key '{key}'")
		name = field.get("shared", f"<fields[{index}]>")
		shared_names.append(name)
		if field.get("class") == "S3":
			err(f"C4 field '{name}' is class S3 (restricted data never enters the shared layer)")
		elif field.get("class") not in CLASSES:
			err(f"C4 field '{name}' has class {field.get('class')!r}; only S0, S1, S2 are allowed")
		if field.get("type") not in FIELD_TYPES:
			err(f"C1 field '{name}' has unknown type {field.get('type')!r}")
		hits = []
		for part in ("shared", "source"):
			value = field.get(part)
			hit = _deny_hit(value) if isinstance(value, str) else None
			if hit:
				hits.append(f"{part} name '{value}' contains '{hit}'")
		if hits and (entity, name) not in EXCEPTIONS:
			err(f"C5 field '{name}' is deny-listed: " + "; ".join(hits))
	if len(set(shared_names)) != len(shared_names):
		err("C1 duplicate shared field names")
	id_field = contract["id_field"]
	for field in contract["fields"]:
		if isinstance(field, dict) and (
			field.get("source") == id_field or field.get("shared") == "entity_id"
		):
			err(
				f"C7 field '{field.get('shared')}' exposes the id field '{id_field}' (it is entity_id, never a shared field)"
			)
	system_names = {
		"source_app",
		"entity_id",
		"tenant_id",
		"source_modified",
		"last_seq",
		"contract_version",
		"deleted_at",
		"synced_at",
	}
	for name in shared_names:
		if name in system_names:
			err(f"C1 shared field '{name}' clashes with a system column")

	# C6 consumers
	allowed_consumers = registered | PLANNED_APPS
	if isinstance(contract["consumers"], dict):
		for app, fields in contract["consumers"].items():
			if app not in allowed_consumers:
				err(f"C6 consumer '{app}' is not a registered or planned app")
			if not isinstance(fields, list) or not fields:
				err(f"C6 consumer '{app}' must list at least one field")
				continue
			for name in fields:
				if name not in shared_names:
					err(f"C6 consumer '{app}' lists '{name}', which is not a shared field of {entity}")

	# C7 commands
	if isinstance(contract["commands"], list):
		for command in contract["commands"]:
			if not isinstance(command, dict) or not {"name", "writable_fields", "needs_role"} <= set(command):
				err("C1 every command needs name, writable_fields and needs_role")
				continue
			for name in command["writable_fields"]:
				if name not in shared_names:
					err(
						f"C7 command '{command['name']}' writes '{name}', which is not a shared field of {entity}"
					)
				source = next(
					(
						f.get("source")
						for f in contract["fields"]
						if isinstance(f, dict) and f.get("shared") == name
					),
					None,
				)
				if name == "entity_id" or source == id_field:
					err(f"C7 command '{command['name']}' may not write the id field")

	# C8 module paths
	for text in _strings(contract):
		if FORBIDDEN_MODULE_PATH.search(text):
			err(f"C8 a module path of another app appears in a value: {text!r}")

	return errors


def collect(paths: list) -> list:
	files: list = []
	for raw in paths:
		path = Path(raw)
		files.extend(sorted(path.glob("*.json")) if path.is_dir() else [path])
	return files


def check_files(files: list, registered: set) -> tuple:
	"""(violations, [(entity_type, status)] for the contracts that passed on their own)."""
	errors: list = []
	seen: dict = {}
	passed: list = []
	for path in files:
		label = path.name
		try:
			contract = json.loads(path.read_text(encoding="utf-8"))
		except (OSError, ValueError) as exc:
			errors.append(f"{label}: C1 cannot read as JSON: {exc}")
			continue
		found = check_contract(contract, label, registered)
		if isinstance(contract, dict) and isinstance(contract.get("entity_type"), str):
			entity = contract["entity_type"]
			if entity in seen:
				errors.append(
					f"{label}: C2 a second contract for entity '{entity}' (first in {seen[entity]}); "
					"one contract and one owner per entity"
				)
			else:
				seen[entity] = label
			if (
				path.name != f"{entity}.json"
				and not path.name.endswith(".copy.json")
				and "entity_type" in contract
			):
				if path.parent == CONTRACT_DIR:
					found.append(f"{label}: C2 file name must be {entity}.json")
		errors.extend(found)
		if not found:
			passed.append((contract["entity_type"], contract["status"]))
	return errors, passed


def main(argv: list) -> int:
	files = collect(argv[1:] or [CONTRACT_DIR])
	if not files:
		print("check_contracts: no contract files found", file=sys.stderr)
		return 1
	registered = registry_keys()
	errors, passed = check_files(files, registered)
	for entity, status in passed:
		print(f"PASS {entity} ({status})")
	for line in errors:
		print(f"FAIL {line}", file=sys.stderr)
	if errors:
		print(
			f"check_contracts: {len(errors)} violation(s), {len(passed)} of {len(files)} contract(s) clean",
			file=sys.stderr,
		)
		return 1
	print(f"check_contracts: PASS for {len(passed)} contract(s)")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
