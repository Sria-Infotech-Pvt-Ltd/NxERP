"""The event envelope (nxerp/shared/envelope_schema.json) against the contracts. No Frappe, no database.

	python -m unittest apps/nxerp_platform/nxerp/shared_service/tests/test_envelope.py

The JSON Schema checks need the `jsonschema` package and are skipped without it; the stdlib twin
`registry.event_problems` always runs and holds the per-entity allow-list rule.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared import registry

try:
	import jsonschema
except ImportError:
	jsonschema = None

SAMPLES = {
	"string": "Example",
	"integer": 1,
	"boolean": 0,
	"datetime": "2026-11-18 10:21:04.512311",
	"date": "2026-11-18",
}


def sample_event(entity_type: str, op: str = "upsert") -> dict:
	contract = registry.get_contract(entity_type)
	payload = {field["shared"]: SAMPLES[field["type"]] for field in contract["fields"]}
	return {
		"event_id": f"evt-{entity_type}-0001",
		"seq": 18432,
		"source_app": contract["owner_app"],
		"entity_type": entity_type,
		"entity_id": "EX-0001",
		"op": op,
		"contract_version": contract["contract_version"],
		"source_modified": "2026-11-18 10:21:04.512311",
		"tenant_id": "ORG-001",
		"payload": payload if op == "upsert" else None,
	}


def schema():
	return json.loads(registry.ENVELOPE_SCHEMA_PATH.read_text(encoding="utf-8"))


class TestEnvelope(unittest.TestCase):
	def test_the_schema_entity_list_equals_the_contracts(self):
		self.assertEqual(set(schema()["properties"]["entity_type"]["enum"]), set(registry.load_contracts()))

	def test_a_sample_event_for_every_contract_is_accepted(self):
		for entity in registry.load_contracts():
			for op in ("upsert", "delete", "resync"):
				with self.subTest(entity=entity, op=op):
					self.assertEqual(registry.event_problems(sample_event(entity, op)), [])

	@unittest.skipIf(jsonschema is None, "jsonschema is not installed")
	def test_the_json_schema_accepts_the_samples(self):
		jsonschema.Draft202012Validator.check_schema(schema())
		for entity in registry.load_contracts():
			for op in ("upsert", "delete", "resync"):
				with self.subTest(entity=entity, op=op):
					jsonschema.validate(
						sample_event(entity, op), schema(), cls=jsonschema.Draft202012Validator
					)

	def test_a_payload_with_an_unlisted_field_is_rejected_for_every_entity(self):
		for entity in registry.load_contracts():
			with self.subTest(entity=entity):
				event = sample_event(entity)
				event["payload"]["tax_id"] = "0000"
				problems = registry.event_problems(event)
				self.assertEqual(problems, ["payload field 'tax_id' is not in the allow-list"])

	def test_the_customer_fields_that_must_stay_out_are_rejected(self):
		for field in ("credit_limits", "payment_terms", "default_price_list", "email_id", "mobile_no"):
			event = sample_event("customer")
			event["payload"][field] = "x"
			self.assertTrue(registry.event_problems(event), field)

	def test_a_delete_or_resync_must_not_carry_a_payload(self):
		for op in ("delete", "resync"):
			event = sample_event("customer", op)
			event["payload"] = {"display_name": "Example"}
			self.assertEqual(registry.event_problems(event), [f"a {op} carries no payload"])

	def test_an_upsert_needs_a_payload(self):
		event = sample_event("customer")
		event["payload"] = None
		self.assertEqual(registry.event_problems(event), ["an upsert needs a payload object"])

	def test_only_the_owner_may_publish_an_entity(self):
		event = sample_event("customer")
		event["source_app"] = "helpdesk"
		self.assertEqual(len(registry.event_problems(event)), 1)

	def test_a_stale_contract_version_and_an_unknown_entity_are_rejected(self):
		event = sample_event("customer")
		event["contract_version"] = 9
		self.assertIn("is not the current", registry.event_problems(event)[0])
		event = sample_event("customer")
		event["entity_type"] = "invoice"
		self.assertEqual(registry.event_problems(event), ["unknown entity_type 'invoice'"])

	def test_missing_and_unknown_envelope_keys_are_rejected(self):
		event = sample_event("customer")
		del event["tenant_id"]
		event["surprise"] = 1
		problems = registry.event_problems(event)
		self.assertIn("missing key 'tenant_id'", problems)
		self.assertIn("unknown key 'surprise'", problems)

	@unittest.skipIf(jsonschema is None, "jsonschema is not installed")
	def test_the_json_schema_rejects_bad_envelopes(self):
		validator = jsonschema.Draft202012Validator(schema())
		bad = []
		event = sample_event("customer")
		event["op"] = "merge"
		bad.append(event)
		event = sample_event("customer", "delete")
		event["payload"] = {"display_name": "x"}
		bad.append(event)
		event = sample_event("customer")
		event["source_modified"] = "yesterday"
		bad.append(event)
		event = sample_event("customer")
		event["extra"] = 1
		bad.append(event)
		event = copy.deepcopy(sample_event("customer"))
		event["entity_type"] = "invoice"
		bad.append(event)
		for index, event in enumerate(bad):
			self.assertFalse(validator.is_valid(event), f"bad envelope #{index} was accepted: {event}")


if __name__ == "__main__":
	unittest.main()
