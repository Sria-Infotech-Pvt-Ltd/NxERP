"""The shared-entity ownership contracts and their lint (scripts/check_contracts.py).

Plain unittest: nothing here needs a Frappe site, so it also runs on a developer's host:

	python -m unittest apps/nxerp_platform/nxerp/tests/test_shared_contracts.py

The JSON Schema test needs the `jsonschema` package and is skipped (not failed) without it; the lint itself is
stdlib only and checks the same structure.
"""

import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PLATFORM = REPO / "apps" / "nxerp_platform"
sys.path.insert(0, str(PLATFORM))

from nxerp.shared import registry

LINT_PATH = REPO / "scripts" / "check_contracts.py"
# the lint lives in the repository's scripts/ folder, which an installed copy of the app (a bench image) does not have:
# load it only when present and skip the tests that need it, as test_architecture does
lint = None
if LINT_PATH.is_file():
	_spec = importlib.util.spec_from_file_location("check_contracts", LINT_PATH)
	lint = importlib.util.module_from_spec(_spec)
	_spec.loader.exec_module(lint)
needs_lint = unittest.skipUnless(
	lint is not None, "scripts/check_contracts.py is not part of this deployment"
)

try:
	import jsonschema
except ImportError:  # the lint covers the same structure; only the schema test is skipped
	jsonschema = None

ENTITIES = {
	"customer",
	"contact",
	"user_ref",
	"org_unit",
	"employee_ref",
	"project_ref",
	"ticket_summary",
}
REGISTERED = lint.registry_keys() if lint else set()


def violations(contract, name="x.json"):
	return lint.check_contract(contract, name, REGISTERED)


class TestContractFiles(unittest.TestCase):
	def test_seven_contracts_exist(self):
		self.assertEqual(set(registry.load_contracts()), ENTITIES)

	@unittest.skipIf(jsonschema is None, "jsonschema is not installed")
	def test_every_contract_is_valid_against_the_schema(self):
		schema = json.loads(registry.SCHEMA_PATH.read_text(encoding="utf-8"))
		jsonschema.Draft202012Validator.check_schema(schema)
		for entity, contract in registry.load_contracts().items():
			with self.subTest(entity=entity):
				jsonschema.validate(contract, schema, cls=jsonschema.Draft202012Validator)

	@needs_lint
	def test_the_lint_passes_on_the_real_contracts(self):
		errors, passed = lint.check_files(lint.collect([lint.CONTRACT_DIR]), REGISTERED)
		self.assertEqual(errors, [])
		self.assertEqual({entity for entity, _ in passed}, ENTITIES)

	@needs_lint
	def test_planned_owners_are_marked_planned(self):
		contracts = registry.load_contracts()
		for entity in ("employee_ref", "project_ref"):
			self.assertEqual(contracts[entity]["status"], "planned", entity)
		for entity, contract in contracts.items():
			if contract["owner_app"] not in REGISTERED:
				self.assertEqual(contract["status"], "planned", entity)

	@needs_lint
	def test_no_contract_shares_class_s3_or_a_denied_name(self):
		for entity, contract in registry.load_contracts().items():
			for field in contract["fields"]:
				self.assertIn(field["class"], {"S0", "S1", "S2"}, f"{entity}.{field['shared']}")
				for part in (field["shared"], field["source"]):
					self.assertIsNone(lint._deny_hit(part), f"{entity}: {part}")

	def test_excluded_sensitive_customer_fields_are_not_shared(self):
		shared = set(registry.shared_fields("customer"))
		for name in (
			"tax_id",
			"credit_limits",
			"payment_terms",
			"default_price_list",
			"email_id",
			"mobile_no",
		):
			self.assertNotIn(name, shared)

	@needs_lint
	def test_planned_apps_are_not_in_the_platform_registry(self):
		self.assertEqual(REGISTERED & lint.PLANNED_APPS, set())


class TestRegistry(unittest.TestCase):
	def test_get_contract_and_owners(self):
		self.assertEqual(registry.get_contract("customer")["owner_app"], "erpnext")
		self.assertIsNone(registry.get_contract("nope"))
		owners = registry.owners()
		self.assertEqual(owners["erpnext"], ["contact", "customer", "org_unit"])
		self.assertEqual(owners["helpdesk"], ["ticket_summary"])

	def test_consumers_of(self):
		self.assertEqual(set(registry.consumers_of("customer")), {"helpdesk"})
		self.assertEqual(registry.consumers_of("nope"), {})

	def test_payload_unlisted(self):
		self.assertEqual(registry.payload_unlisted("customer", {"display_name": "x", "territory": "y"}), [])
		self.assertEqual(
			registry.payload_unlisted("customer", {"display_name": "x", "tax_id": "1"}), ["tax_id"]
		)

	def test_registry_module_imports_no_other_app(self):
		source = Path(registry.__file__).read_text(encoding="utf-8")
		for forbidden in ("import frappe", "from frappe", "erpnext", "helpdesk"):
			self.assertNotIn(forbidden, source.replace("helpdesk.json", ""), forbidden)


@needs_lint
class TestLintRejectsBadContracts(unittest.TestCase):
	def customer(self):
		return copy.deepcopy(registry.get_contract("customer"))

	def assertViolation(self, errors, code, text):
		self.assertTrue(
			any(code in e and text in e for e in errors), f"no {code} line naming {text!r} in {errors}"
		)

	def test_a_field_named_tax_id_is_refused(self):
		contract = self.customer()
		contract["fields"].append({"shared": "tax_id", "source": "tax_id", "class": "S1", "type": "string"})
		self.assertViolation(violations(contract), "C5", "tax_id")

	def test_a_deny_listed_source_is_refused_even_under_an_innocent_name(self):
		contract = self.customer()
		contract["fields"].append(
			{"shared": "reference", "source": "api_secret", "class": "S1", "type": "string"}
		)
		self.assertViolation(violations(contract), "C5", "api_secret")

	def test_class_s3_is_refused(self):
		contract = self.customer()
		contract["fields"][1]["class"] = "S3"
		self.assertViolation(violations(contract), "C4", "S3")

	def test_an_unknown_class_is_refused(self):
		contract = self.customer()
		contract["fields"][1]["class"] = "S9"
		self.assertViolation(violations(contract), "C4", "S9")

	def test_a_second_contract_for_the_same_entity_with_another_owner_is_refused(self):
		first = self.customer()
		second = self.customer()
		second["owner_app"] = "helpdesk"
		with tempfile.TemporaryDirectory() as tmp:
			for name, contract in (("customer.json", first), ("customer_2.json", second)):
				Path(tmp, name).write_text(json.dumps(contract), encoding="utf-8")
			errors, _ = lint.check_files(lint.collect([tmp]), REGISTERED)
		self.assertViolation(errors, "C2", "second contract for entity 'customer'")

	def test_an_owner_that_is_not_in_the_registry_is_refused(self):
		contract = self.customer()
		contract["owner_app"] = "crm_pro"
		self.assertViolation(violations(contract), "C3", "crm_pro")

	def test_a_planned_owner_must_be_marked_planned(self):
		contract = self.customer()
		contract["owner_app"] = "hrms"
		contract["status"] = "active"
		self.assertViolation(violations(contract), "C3", "planned")

	def test_a_consumer_cannot_list_a_field_the_entity_does_not_share(self):
		contract = self.customer()
		contract["consumers"]["helpdesk"].append("credit_limit")
		self.assertViolation(violations(contract), "C6", "credit_limit")

	def test_an_unknown_consumer_app_is_refused(self):
		contract = self.customer()
		contract["consumers"]["mystery"] = ["display_name"]
		self.assertViolation(violations(contract), "C6", "mystery")

	def test_a_command_cannot_write_an_unshared_field(self):
		contract = self.customer()
		contract["commands"][0]["writable_fields"] = ["credit_limit"]
		self.assertViolation(violations(contract), "C7", "credit_limit")

	def test_the_id_field_cannot_be_a_shared_field(self):
		contract = self.customer()
		contract["fields"].append(
			{"shared": "customer_id", "source": "name", "class": "S1", "type": "string"}
		)
		self.assertViolation(violations(contract), "C7", "customer_id")

	def test_a_module_path_of_another_app_is_refused(self):
		contract = self.customer()
		contract["source_doctype"] = "erpnext.selling.doctype.customer.customer"
		self.assertViolation(violations(contract), "C8", "erpnext.selling")

	def test_a_missing_key_and_an_unknown_key_are_refused(self):
		contract = self.customer()
		del contract["consumers"]
		contract["surprise"] = 1
		errors = violations(contract)
		self.assertViolation(errors, "C1", "consumers")
		self.assertViolation(errors, "C1", "surprise")

	def test_a_field_may_not_clash_with_a_system_column(self):
		contract = self.customer()
		contract["fields"].append(
			{"shared": "synced_at", "source": "modified", "class": "S1", "type": "datetime"}
		)
		self.assertViolation(violations(contract), "C1", "synced_at")


@needs_lint
class TestLintCommandLine(unittest.TestCase):
	def run_lint(self, *args):
		"""Run the lint's own main() in-process (as the architecture tests do) and capture what it prints."""
		out, err = io.StringIO(), io.StringIO()
		with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
			code = lint.main(["check_contracts.py", *args])
		return code, out.getvalue(), err.getvalue()

	def test_default_run_passes_for_seven(self):
		code, out, err = self.run_lint()
		self.assertEqual(code, 0, err)
		self.assertEqual(out.count("PASS "), 8)  # seven entities and the summary line

	def test_check_2_1_a_copy_with_tax_id_fails_with_one_line_naming_it(self):
		contract = copy.deepcopy(registry.get_contract("customer"))
		contract["fields"].append({"shared": "tax_id", "source": "tax_id", "class": "S1", "type": "string"})
		with tempfile.TemporaryDirectory() as tmp:
			path = Path(tmp, "customer.copy.json")
			path.write_text(json.dumps(contract), encoding="utf-8")
			code, _, err = self.run_lint(str(path))
		self.assertNotEqual(code, 0)
		named = [line for line in err.splitlines() if "tax_id" in line]
		self.assertEqual(len(named), 1, err)


if __name__ == "__main__":
	unittest.main()
