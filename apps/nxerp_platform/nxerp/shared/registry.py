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


def shared_fields(entity_type: str) -> list:
	"""The allow-listed shared field names of an entity, in contract order."""
	contract = get_contract(entity_type)
	return [field["shared"] for field in contract["fields"]] if contract else []


def payload_unlisted(entity_type: str, payload: dict) -> list:
	"""Payload keys that are not in the entity's allow-list (empty list = payload is allowed)."""
	allowed = set(shared_fields(entity_type))
	return sorted(key for key in payload if key not in allowed)
