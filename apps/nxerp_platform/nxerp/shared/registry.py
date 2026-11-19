"""The shared-entity contract registry: reads the ownership contracts in `contracts/`.

Pure Python and JSON. It imports neither `frappe` nor any other app (ADR-005), so the same file is read by
the Frappe side (outbox hooks, later phases) and by the frappe-free shared service and the lint.

A contract is the single source of truth for one shared entity: who owns it, which fields leave the owner,
their sensitivity class, who may read them and which commands may change them (docs/architecture/shared-data-contracts.md).
"""

import json
from functools import lru_cache
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent / "contracts"
SCHEMA_PATH = Path(__file__).resolve().parent / "contract_schema.json"
ENVELOPE_SCHEMA_PATH = Path(__file__).resolve().parent / "envelope_schema.json"

# The doc_events the capture hooks implement (nxerp/shared/capture.py). A contract may list only these.
CAPTURE_EVENTS = ("on_change", "on_trash", "after_rename")


@lru_cache(maxsize=1)
def load_contracts() -> dict:
	"""All contracts, keyed by entity_type, in file-name order."""
	contracts = {}
	for path in sorted(CONTRACT_DIR.glob("*.json")):
		contract = json.loads(path.read_text(encoding="utf-8"))
		contracts[contract["entity_type"]] = contract
	return contracts


def get_contract(entity_type: str) -> dict | None:
	return load_contracts().get(entity_type)


def owners() -> dict:
	"""owner_app -> sorted entity types it owns."""
	result: dict = {}
	for entity_type, contract in load_contracts().items():
		result.setdefault(contract["owner_app"], []).append(entity_type)
	return {owner: sorted(types) for owner, types in sorted(result.items())}


def consumers_of(entity_type: str) -> dict:
	"""app key -> the shared fields that app may read (empty if the entity or its consumers are unknown)."""
	contract = get_contract(entity_type)
	return dict(contract["consumers"]) if contract else {}


def contracts_for_doctype(doctype: str) -> list:
	"""Active contracts whose source DocType is `doctype` (planned contracts are never captured)."""
	return [
		contract
		for contract in load_contracts().values()
		if contract["status"] == "active" and contract["source_doctype"] == doctype
	]


def capture_events() -> dict:
	"""{source DocType: sorted capture events} for every active contract: what hooks.py registers."""
	events: dict = {}
	for contract in load_contracts().values():
		if contract["status"] != "active":
			continue
		wanted = events.setdefault(contract["source_doctype"], set())
		wanted.update(event for event in contract["events"] if event in CAPTURE_EVENTS)
	return {doctype: sorted(wanted) for doctype, wanted in sorted(events.items())}


def shared_fields(entity_type: str) -> list:
	"""The allow-listed shared field names of an entity, in contract order."""
	contract = get_contract(entity_type)
	return [field["shared"] for field in contract["fields"]] if contract else []


def payload_unlisted(entity_type: str, payload: dict) -> list:
	"""Payload keys that are not in the entity's allow-list (empty list = payload is allowed)."""
	allowed = set(shared_fields(entity_type))
	return sorted(key for key in payload if key not in allowed)


EVENT_KEYS = (
	"event_id",
	"seq",
	"source_app",
	"entity_type",
	"entity_id",
	"op",
	"contract_version",
	"source_modified",
	"tenant_id",
	"payload",
)


def event_problems(event: dict) -> list:
	"""What is wrong with one feed event, judged against the contracts (empty list = acceptable).

	Stdlib twin of envelope_schema.json plus the per-entity rules a schema cannot hold: a known entity, the
	owner's source_app, the current contract version, and a payload with no field outside the allow-list.
	"""
	problems = [f"missing key '{key}'" for key in EVENT_KEYS if key not in event]
	problems += [f"unknown key '{key}'" for key in event if key not in EVENT_KEYS]
	if problems:
		return problems
	contract = get_contract(event["entity_type"])
	if contract is None:
		return [f"unknown entity_type '{event['entity_type']}'"]
	if event["op"] not in ("upsert", "delete", "resync"):
		problems.append(f"unknown op '{event['op']}'")
	if event["source_app"] != contract["owner_app"]:
		problems.append(f"source_app '{event['source_app']}' is not the owner '{contract['owner_app']}'")
	if event["contract_version"] != contract["contract_version"]:
		problems.append(
			f"contract_version {event['contract_version']} is not the current {contract['contract_version']}"
		)
	payload = event["payload"]
	if event["op"] == "upsert":
		if not isinstance(payload, dict):
			problems.append("an upsert needs a payload object")
		else:
			problems += [
				f"payload field '{key}' is not in the allow-list"
				for key in payload_unlisted(event["entity_type"], payload)
			]
	elif payload is not None:
		problems.append(f"a {event['op']} carries no payload")
	return problems
