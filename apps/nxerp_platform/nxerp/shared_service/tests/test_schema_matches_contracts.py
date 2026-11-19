"""The shared database's DDL and the ownership contracts must agree. No Frappe, no database server.

	python -m unittest apps/nxerp_platform/nxerp/shared_service/tests/test_schema_matches_contracts.py

The SQL file is parsed as text (it is not executed here: "executed against MariaDB 11.8" is UNVERIFIED until
Phase 4 runs it on a scratch server, see the file header).
"""

import copy
import importlib.util
import re
import sys
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[3]
REPO = PLATFORM.parent.parent
sys.path.insert(0, str(PLATFORM))

from nxerp.shared import registry

SCHEMA_DIR = PLATFORM / "nxerp" / "shared_service" / "schema"
SQL_PATH = SCHEMA_DIR / "0001_shared_model.sql"


def _load(name, path):
	spec = importlib.util.spec_from_file_location(name, path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


gen = _load("generate_columns", SCHEMA_DIR / "generate_columns.py")
LINT_PATH = REPO / "scripts" / "check_contracts.py"
# scripts/ is not part of an installed copy of the app (a bench image): skip what needs it instead of failing discovery
lint = _load("check_contracts", LINT_PATH) if LINT_PATH.is_file() else None

CONTROL_TABLES = {"sync_cursor", "sync_dead_letter", "consumer_grant", "read_audit", "contract_registry"}
INDEX_WORDS = ("PRIMARY", "UNIQUE", "KEY", "CONSTRAINT", "FOREIGN", "INDEX", "FULLTEXT")


def strip_comments(sql: str) -> str:
	return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def parse_tables(sql: str) -> dict:
	"""table name -> {"columns": [(name, definition)], "other": [non-column lines], "tail": text after ')'}."""
	tables = {}
	for match in re.finditer(
		r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\)([^;]*);", strip_comments(sql), re.S
	):
		name, body, tail = match.groups()
		columns, other = [], []
		for line in body.strip().splitlines():
			line = line.strip().rstrip(",")
			if not line:
				continue
			first = line.split()[0].upper()
			if first in INDEX_WORDS:
				other.append(line)
			else:
				column, definition = line.split(None, 1)
				columns.append((column, definition))
		tables[name] = {"columns": columns, "other": other, "tail": tail}
	return tables


def problems_for(contracts: dict, tables: dict) -> list:
	"""Every way the parsed DDL disagrees with the contracts (empty = they agree)."""
	problems = []
	system = set(gen.SYSTEM_COLUMNS)
	for entity, contract in contracts.items():
		table = tables.get(gen.table_name(entity))
		if table is None:
			problems.append(f"no table {gen.table_name(entity)} for contract {entity}")
			continue
		by_name = dict(table["columns"])
		for field in contract["fields"]:
			column = field["shared"]
			if column not in by_name:
				problems.append(f"{gen.table_name(entity)}: contract field '{column}' has no column")
			elif not by_name[column].startswith(gen.sql_type(field)):
				problems.append(
					f"{gen.table_name(entity)}.{column}: type {by_name[column]!r} is not {gen.sql_type(field)}"
				)
		shared = {field["shared"] for field in contract["fields"]}
		for column in by_name:
			if column not in system and column not in shared:
				problems.append(f"{gen.table_name(entity)}: column '{column}' has no contract field")
	known = {gen.table_name(entity) for entity in contracts} | CONTROL_TABLES
	for name in tables:
		if name not in known:
			problems.append(f"table '{name}' belongs to no contract and is not a control table")
	return problems


class TestSchemaMatchesContracts(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.sql = SQL_PATH.read_text(encoding="utf-8")
		cls.tables = parse_tables(cls.sql)
		cls.contracts = registry.load_contracts()

	def test_every_contract_field_has_a_column_and_nothing_else_does(self):
		self.assertEqual(problems_for(self.contracts, self.tables), [])

	def test_the_entity_tables_are_exactly_what_the_generator_writes(self):
		self.assertIn(gen.render_entity_tables(self.contracts), self.sql)

	def test_there_is_one_table_per_entity_and_the_five_control_tables(self):
		self.assertEqual(set(self.tables), {gen.table_name(e) for e in self.contracts} | CONTROL_TABLES)

	def test_each_entity_table_has_the_system_columns_and_the_key(self):
		for entity in self.contracts:
			table = self.tables[gen.table_name(entity)]
			names = [name for name, _ in table["columns"]]
			for column in gen.SYSTEM_COLUMNS:
				self.assertIn(column, names, f"{entity}: {column}")
			self.assertIn("PRIMARY KEY (source_app, entity_id)", table["other"], entity)

	def test_the_version_stamp_and_tombstone_columns_have_the_right_types(self):
		columns = dict(self.tables["entity_customer"]["columns"])
		self.assertTrue(columns["source_modified"].startswith("DATETIME(6) NOT NULL"))
		self.assertTrue(columns["last_seq"].startswith("BIGINT NOT NULL"))
		self.assertTrue(columns["contract_version"].startswith("INT NOT NULL"))
		self.assertTrue(columns["deleted_at"].startswith("DATETIME(6)"))

	def test_every_table_is_utf8mb4(self):
		for name, table in self.tables.items():
			self.assertIn("CHARSET=utf8mb4", table["tail"], name)

	@unittest.skipUnless(lint is not None, "scripts/check_contracts.py is not part of this deployment")
	def test_no_column_is_on_the_deny_list(self):
		for name, table in self.tables.items():
			for column, _ in table["columns"]:
				self.assertIsNone(lint._deny_hit(column), f"{name}.{column}")

	def test_no_foreign_keys_no_accounts_no_grants(self):
		code = strip_comments(self.sql).upper()
		for forbidden in ("FOREIGN KEY", "REFERENCES", "CREATE USER", "GRANT", "IDENTIFIED BY", "PASSWORD"):
			# whole words only: the table consumer_grant is not a GRANT statement
			self.assertIsNone(re.search(rf"(?<![A-Z0-9_]){forbidden}(?![A-Z0-9_])", code), forbidden)

	def test_the_sync_cursor_and_dead_letter_support_idempotent_apply(self):
		cursor = dict(self.tables["sync_cursor"]["columns"])
		self.assertIn("last_seq", cursor)
		self.assertIn("PRIMARY KEY (source_app)", self.tables["sync_cursor"]["other"])
		self.assertIn("UNIQUE KEY uq_event (source_app, event_id)", self.tables["sync_dead_letter"]["other"])

	def test_no_planned_app_is_displayed_or_created_as_an_account(self):
		# the DDL only names owners through contract data; it never creates anything for them
		self.assertNotIn("CREATE USER", self.sql.upper())


class TestCheck22TheCheckCatchesDrift(unittest.TestCase):
	"""Check 2.2: delete one field from a copy of a contract and the schema test fails, naming the column."""

	def test_a_contract_field_without_a_column_is_named(self):
		tables = parse_tables(SQL_PATH.read_text(encoding="utf-8"))
		contracts = copy.deepcopy(registry.load_contracts())
		contracts["customer"]["fields"].append(
			{"shared": "customer_region", "source": "territory", "class": "S1", "type": "string"}
		)
		problems = problems_for(contracts, tables)
		self.assertEqual(problems, ["entity_customer: contract field 'customer_region' has no column"])

	def test_a_column_without_a_contract_field_is_named(self):
		tables = parse_tables(SQL_PATH.read_text(encoding="utf-8"))
		contracts = copy.deepcopy(registry.load_contracts())
		contracts["customer"]["fields"] = [
			f for f in contracts["customer"]["fields"] if f["shared"] != "territory"
		]
		problems = problems_for(contracts, tables)
		self.assertEqual(problems, ["entity_customer: column 'territory' has no contract field"])

	def test_a_wrong_column_type_is_named(self):
		tables = parse_tables(SQL_PATH.read_text(encoding="utf-8"))
		contracts = copy.deepcopy(registry.load_contracts())
		for field in contracts["customer"]["fields"]:
			if field["shared"] == "disabled":
				field["type"] = "integer"
		problems = problems_for(contracts, tables)
		self.assertEqual(len(problems), 1)
		self.assertIn("entity_customer.disabled", problems[0])

	def test_an_entity_without_a_table_is_named(self):
		tables = parse_tables(SQL_PATH.read_text(encoding="utf-8"))
		del tables["entity_org_unit"]
		problems = problems_for(registry.load_contracts(), tables)
		self.assertIn("no table entity_org_unit for contract org_unit", problems)


if __name__ == "__main__":
	unittest.main()
