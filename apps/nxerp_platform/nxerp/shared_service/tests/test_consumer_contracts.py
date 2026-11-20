"""Consumer-driven contract tests (Phase 7C): what each ownership contract PROMISES a consumer, checked against the real code.

For every `consumers` entry of every active contract: the Read API, on a real MariaDB with the generated views, returns exactly the granted fields
(plus the version columns) and refuses every other contract field and every non-contract field with 403; an app that is not a consumer is refused.
For every `commands` entry: a valid request is accepted by the command API's input rules and an out-of-contract field is refused with 422.

The Read API part needs a reachable MariaDB (skipped without one: `deploy/scripts/shared.sh test -p "test_consumer_contracts*"`); each class uses its
own throwaway database. The command part imports the command module, which needs Frappe on the path (the image has it; a bare host skips).
"""

import json
import sys
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared import registry
from nxerp.shared_service import credentials
from nxerp.shared_service.tests.support import SharedDbTestCase

try:
	from werkzeug.test import Client

	from nxerp.shared_service.readapi import ReadApi
except ImportError:  # the image has Werkzeug and PyMySQL; a bare host skips
	Client = ReadApi = None

try:
	from nxerp.shared import command
except ImportError:  # no Frappe on this host
	command = None

SYSTEM = {"entity_id", "tenant_id", "source_modified", "synced_at"}
STAMP = "2026-11-20 10:00:00.000000"


def active_contracts() -> list:
	return [c for c in registry.load_contracts().values() if c["status"] == "active"]


def sample_value(field: dict):
	kind = field["type"]
	if kind == "boolean":
		return 1
	if kind == "integer":
		return 7
	if kind == "datetime":
		return STAMP
	return f"sample-{field['shared']}"


def tenant_for(contract: dict) -> str:
	tenant = contract["tenant"]
	return tenant["value"] if tenant["mode"] == "constant" else "ORG-001"


class TestReadApiPromises(SharedDbTestCase):
	"""Each consumer sees exactly its granted fields of each entity, and nothing else."""

	@classmethod
	def setUpClass(cls):
		if Client is None:
			raise unittest.SkipTest("Werkzeug is not installed")
		super().setUpClass()
		cls.consumers = {
			(c["entity_type"], app): fields
			for c in active_contracts()
			for app, fields in c["consumers"].items()
		}
		cls.apps = sorted({app for _entity, app in cls.consumers})
		conn = cls.connect("migrate")
		try:
			cls.tokens = {app: credentials.issue(conn, app)["token"] for app in cls.apps}
		finally:
			conn.close()
		proj = cls.connect("projector")
		with proj.cursor() as cur:
			for contract in active_contracts():
				if not contract["consumers"]:
					continue
				fields = contract["fields"]
				columns = ["source_app", "entity_id", "tenant_id", *[f["shared"] for f in fields]]
				columns += ["source_modified", "last_seq", "contract_version", "synced_at"]
				values = [
					contract["owner_app"],
					f"{contract['entity_type'].upper()}-1",
					tenant_for(contract),
					*[sample_value(f) for f in fields],
				]
				cur.execute(
					f"INSERT INTO entity_{contract['entity_type']} ({', '.join(f'`{c}`' for c in columns)}) "  # nosec B608  (names come from the contract files)
					f"VALUES ({', '.join(['%s'] * len(values))}, %s, 1, %s, NOW(6))",
					(*values, STAMP, contract["contract_version"]),
				)
		proj.commit()
		proj.close()

	def setUp(self):
		self.api = ReadApi(
			connect=lambda: self.connect("readapi", autocommit=True),
			cache_seconds=0,
			audit_background=False,
			rate_per_minute=100000,
		)
		self.client = Client(self.api)

	def get(self, app: str, path: str):
		return self.client.get(path, headers={"Authorization": f"Bearer {self.tokens[app]}"})

	def test_every_consumer_gets_exactly_its_granted_fields(self):
		self.assertTrue(self.consumers, "the contracts name at least one consumer")
		for (entity, app), granted in sorted(self.consumers.items()):
			response = self.get(app, f"/v1/{entity}/{entity.upper()}-1")
			self.assertEqual(response.status_code, 200, (entity, app, response.get_data(as_text=True)))
			self.assertEqual(set(response.get_json()["data"]), SYSTEM | set(granted), (entity, app))

	def test_every_other_contract_field_and_every_field_outside_the_contract_is_refused(self):
		for (entity, app), granted in sorted(self.consumers.items()):
			contract = registry.get_contract(entity)
			not_granted = {f["shared"] for f in contract["fields"]} - set(granted)
			for name in (*sorted(not_granted), "tax_id", "credit_limits", "password", "no_such_field"):
				response = self.get(app, f"/v1/{entity}/{entity.upper()}-1?fields={name}")
				self.assertEqual(response.status_code, 403, (entity, app, name))
				self.assertEqual(
					response.get_json()["error"]["code"], "field_not_granted", (entity, app, name)
				)

	def test_an_app_that_is_not_a_consumer_of_an_entity_is_refused(self):
		for (entity, _app), _granted in sorted(self.consumers.items()):
			for app in self.apps:
				if (entity, app) in self.consumers:
					continue
				response = self.get(app, f"/v1/{entity}/{entity.upper()}-1")
				self.assertEqual(response.status_code, 403, (entity, app))
				self.assertEqual(response.get_json()["error"]["code"], "not_granted", (entity, app))

	def test_the_response_never_holds_a_field_outside_the_contract(self):
		for (entity, app), _granted in sorted(self.consumers.items()):
			contract = registry.get_contract(entity)
			allowed = SYSTEM | {f["shared"] for f in contract["fields"]}
			body = self.get(app, f"/v1/{entity}?limit=5").get_json()
			for row in body["data"]:
				self.assertLessEqual(set(row), allowed, (entity, app))


@unittest.skipIf(command is None, "Frappe is not importable on this host")
class TestCommandPromises(unittest.TestCase):
	"""Each command accepts its writable fields and refuses anything else with 422 (input rules only: the database part is test_commands.py)."""

	def commands(self):
		return [(c["entity_type"], item) for c in active_contracts() for item in c["commands"]]

	def test_there_is_at_least_one_command_and_every_one_names_its_callers(self):
		found = self.commands()
		self.assertTrue(found)
		for entity, item in found:
			self.assertTrue(item["callers"], (entity, item["name"]))
			self.assertLessEqual(
				set(item["callers"]), set(registry.load_contracts()[entity]["consumers"]) | {"helpdesk"}
			)

	def test_a_valid_request_is_accepted_for_every_writable_field(self):
		for entity, item in self.commands():
			contract = registry.get_contract(entity)
			sample = {name: "x" for name in item["writable_fields"]}
			self.assertEqual(command._parse_fields(json.dumps(sample), item), sample, (entity, item["name"]))
			self.assertIs(
				registry.command_for(entity, item["name"].split(".")[1]), item, (entity, item["name"])
			)
			self.assertLessEqual(set(item["writable_fields"]), {f["shared"] for f in contract["fields"]})

	def test_a_field_outside_the_command_is_422(self):
		for entity, item in self.commands():
			contract = registry.get_contract(entity)
			outside = ({f["shared"] for f in contract["fields"]} - set(item["writable_fields"])) | {
				"tax_id",
				"name",
				"owner",
				"docstatus",
			}
			for name in sorted(outside):
				with self.assertRaises(command.CommandError, msg=(entity, item["name"], name)) as caught:
					command._parse_fields(json.dumps({name: "x"}), item)
				self.assertEqual(
					(caught.exception.status, caught.exception.code), (422, "field_not_writable")
				)

	def test_a_value_that_is_not_plain_or_is_too_long_is_422(self):
		for entity, item in self.commands():
			name = item["writable_fields"][0]
			for bad in ([1], {"a": 1}, "x" * (command.MAX_VALUE_LENGTH + 1)):
				with self.assertRaises(command.CommandError, msg=(entity, name)) as caught:
					command._parse_fields(json.dumps({name: bad}), item)
				self.assertEqual(caught.exception.status, 422)

	def test_a_command_cannot_write_an_id_or_a_system_field(self):
		for entity, item in self.commands():
			contract = registry.get_contract(entity)
			id_sources = {contract["id_field"], "entity_id"}
			for name in item["writable_fields"]:
				source = next(f["source"] for f in contract["fields"] if f["shared"] == name)
				self.assertNotIn(source, id_sources, (entity, name))
				self.assertNotIn(name, SYSTEM, (entity, name))


if __name__ == "__main__":
	unittest.main()
