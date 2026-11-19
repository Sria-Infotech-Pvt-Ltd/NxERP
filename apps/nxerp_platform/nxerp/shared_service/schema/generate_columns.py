"""Columns of the shared read database, derived from the ownership contracts. No Frappe, no database.

The shared tables are derived from the contracts (docs/architecture/shared-data-contracts.md): one typed table per
entity, `entity_<entity_type>`, whose business columns are exactly the contract's allow-listed `fields`, plus the
system columns every entity table carries. The entity tables in `0001_shared_model.sql` are this module's output;
`tests/test_schema_matches_contracts.py` parses the SQL file and fails if the two ever differ.

	python generate_columns.py            # print the columns of every entity
	python generate_columns.py --ddl      # print the CREATE TABLE statements for the entity tables
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGISTRY_PATH = HERE.parents[1] / "shared" / "registry.py"

# Columns every entity table has, in order, around the contract's own columns.
SYSTEM_LEADING = (
	("source_app", "VARCHAR(64) NOT NULL"),
	("entity_id", "VARCHAR(140) NOT NULL"),
	("tenant_id", "VARCHAR(64) NOT NULL"),
)
SYSTEM_TRAILING = (
	("source_modified", "DATETIME(6) NOT NULL"),
	("last_seq", "BIGINT NOT NULL"),
	("contract_version", "INT NOT NULL"),
	("deleted_at", "DATETIME(6) NULL DEFAULT NULL"),
	("synced_at", "DATETIME(6) NOT NULL"),
)
SYSTEM_COLUMNS = tuple(name for name, _ in (*SYSTEM_LEADING, *SYSTEM_TRAILING))

# Extra secondary indexes by entity (column names are shared fields of that entity).
EXTRA_INDEXES = {
	"contact": ("customer_id",),
	"ticket_summary": ("customer_id", "status"),
}

CHARSET = "utf8mb4"
COLLATION = "utf8mb4_unicode_ci"


def _load_registry():
	spec = importlib.util.spec_from_file_location("nxerp_shared_registry", REGISTRY_PATH)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def sql_type(field: dict) -> str:
	"""MariaDB column type for a contract field."""
	kind = field["type"]
	if kind == "string":
		return f"VARCHAR({field.get('max_length', 140)})"
	return {"integer": "INT", "boolean": "TINYINT(1)", "datetime": "DATETIME(6)", "date": "DATE"}[kind]


def table_name(entity_type: str) -> str:
	return f"entity_{entity_type}"


def columns_for(contract: dict) -> list:
	"""[(column, type)] of the contract's business columns, in contract order (no system columns)."""
	return [(field["shared"], sql_type(field)) for field in contract["fields"]]


def all_columns(contracts: dict | None = None) -> dict:
	"""entity_type -> [(column, type)] for every contract."""
	contracts = contracts if contracts is not None else _load_registry().load_contracts()
	return {entity: columns_for(contract) for entity, contract in contracts.items()}


def render_entity_table(contract: dict) -> str:
	entity = contract["entity_type"]
	lines = [f"CREATE TABLE IF NOT EXISTS {table_name(entity)} ("]
	for name, definition in SYSTEM_LEADING:
		lines.append(f"\t{name} {definition},")
	for name, kind in columns_for(contract):
		lines.append(f"\t{name} {kind} NULL DEFAULT NULL,")
	for name, definition in SYSTEM_TRAILING:
		lines.append(f"\t{name} {definition},")
	lines.append("\tPRIMARY KEY (source_app, entity_id),")
	indexes = [("idx_live", "tenant_id, deleted_at")]
	indexes += [(f"idx_{column}", column) for column in EXTRA_INDEXES.get(entity, ())]
	for position, (name, columns) in enumerate(indexes):
		comma = "," if position < len(indexes) - 1 else ""
		lines.append(f"\tKEY {name} ({columns}){comma}")
	lines.append(f") ENGINE=InnoDB DEFAULT CHARSET={CHARSET} COLLATE={COLLATION};")
	return "\n".join(lines)


def render_entity_tables(contracts: dict | None = None) -> str:
	contracts = contracts if contracts is not None else _load_registry().load_contracts()
	return "\n\n".join(render_entity_table(contract) for contract in contracts.values())


def main(argv: list) -> int:
	if "--ddl" in argv:
		print(render_entity_tables())
		return 0
	for entity, columns in all_columns().items():
		print(f"{table_name(entity)}: " + ", ".join(f"{name} {kind}" for name, kind in columns))
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
