"""Apply schema/*.sql to the shared database, in order, once each. No frappe.

Forward-only and idempotent: the files applied are recorded in `schema_migrations` with their SHA-256; a file is never run twice,
and a recorded file whose content has changed is an error (a migration that was already applied must not be edited: add a new
one). Run with the `shared_migrate` account only (all privileges on the shared database, nothing else).
"""

import hashlib
from pathlib import Path

from nxerp.shared_service import sqlutil

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"

CREATE_LEDGER = (
	"CREATE TABLE IF NOT EXISTS schema_migrations ("
	"filename VARCHAR(190) NOT NULL, checksum CHAR(64) NOT NULL, applied_at DATETIME(6) NOT NULL, PRIMARY KEY (filename)"
	") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
)


class MigrationError(RuntimeError):
	"""A recorded migration changed, or a statement failed."""


def schema_files(schema_dir: Path = SCHEMA_DIR) -> list:
	"""`NNNN_name.sql` files in order. Templates (`.tmpl`) are not migrations."""
	return sorted(schema_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def checksum(path: Path) -> str:
	return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_migrations(conn, schema_dir: Path = SCHEMA_DIR) -> list:
	"""Apply every file not yet recorded. Returns the names applied in this run (empty when up to date)."""
	with conn.cursor() as cur:
		cur.execute(CREATE_LEDGER)
		cur.execute("SELECT filename, checksum FROM schema_migrations")
		recorded = {row["filename"]: row["checksum"] for row in cur.fetchall()}
	conn.commit()
	applied = []
	for path in schema_files(schema_dir):
		digest = checksum(path)
		if path.name in recorded:
			if recorded[path.name] != digest:
				raise MigrationError(
					f"{path.name} was applied earlier and has changed since: add a new migration instead"
				)
			continue
		try:
			with conn.cursor() as cur:
				for statement in sqlutil.split_statements(path.read_text(encoding="utf-8")):
					cur.execute(statement)
				cur.execute(
					"INSERT INTO schema_migrations (filename, checksum, applied_at) VALUES (%s, %s, NOW(6))",
					(path.name, digest),
				)
			conn.commit()
		except Exception as exc:
			conn.rollback()
			raise MigrationError(f"{path.name} failed: {type(exc).__name__}: {str(exc)[:200]}") from exc
		applied.append(path.name)
	return applied
