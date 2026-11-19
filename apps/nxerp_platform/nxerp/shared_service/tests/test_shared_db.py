"""Migrations, accounts and grants against a real MariaDB (throwaway database and accounts per class).

Skipped unless a server is reachable with SHARED_DB_ROOT_PASSWORD set: run `deploy/scripts/shared.sh test`.
"""

import sys
import tempfile
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared_service import accounts, migrate, sqlutil, views
from nxerp.shared_service.tests.support import SharedDbTestCase

ENTITY_TABLES = [
	"entity_contact",
	"entity_customer",
	"entity_employee_ref",
	"entity_org_unit",
	"entity_project_ref",
	"entity_ticket_summary",
	"entity_user_ref",
]
BASE_TABLES = [
	*ENTITY_TABLES,
	"sync_cursor",
	"sync_dead_letter",
	"consumer_grant",
	"read_audit",
	"contract_registry",
	"consumer_credential",
	"sync_metric",
	"schema_migrations",
]


def on_table(verb: str, table: str, rest: str = "") -> str:
	"""A statement over one table, assembled from a validated identifier (not formatted into a string)."""
	return "".join([verb, " ", sqlutil.ident(table), rest])


def denied(test, conn, sql, params=None):
	"""Run a statement that must be refused for lack of privilege (MariaDB errors 1142 table, 1143 column, 1044 database)."""
	import pymysql

	with test.assertRaises(pymysql.err.OperationalError) as caught:
		with conn.cursor() as cur:
			cur.execute(sql, params)
	test.assertIn(
		caught.exception.args[0],
		(1142, 1143, 1044, 1370),
		f"{sql!r} failed for another reason: {caught.exception}",
	)
	conn.rollback()


class TestMigrations(SharedDbTestCase):
	with_accounts = False

	def test_all_tables_and_the_control_views_exist(self):
		conn = self.connect("root")
		with conn.cursor() as cur:
			cur.execute(
				"SELECT TABLE_NAME AS name, TABLE_TYPE AS kind FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s",
				(self.db_name,),
			)
			found = {row["name"]: row["kind"] for row in cur.fetchall()}
		conn.close()
		for table in BASE_TABLES:
			self.assertEqual(found.get(table), "BASE TABLE", table)
		for view in ("ctl_consumer_grant", "ctl_consumer_credential", "ctl_sync_metric", "ctl_read_audit"):
			self.assertEqual(found.get(view), "VIEW", view)

	def test_applying_again_changes_nothing(self):
		conn = self.connect("root")
		try:
			self.assertEqual(migrate.apply_migrations(conn), [])
			with conn.cursor() as cur:
				cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
				self.assertEqual(
					[r["filename"] for r in cur.fetchall()],
					["0001_shared_model.sql", "0003_read_api_support.sql"],
				)
		finally:
			conn.close()

	def test_a_recorded_migration_that_changed_is_refused(self):
		conn = self.connect("root")
		try:
			with tempfile.TemporaryDirectory() as tmp:
				Path(tmp, "0001_shared_model.sql").write_text("SELECT 1;\n", encoding="utf-8")
				with self.assertRaises(migrate.MigrationError):
					migrate.apply_migrations(conn, Path(tmp))
		finally:
			conn.close()

	def test_a_failing_migration_is_reported_and_not_recorded(self):
		conn = self.connect("root")
		try:
			with tempfile.TemporaryDirectory() as tmp:
				Path(tmp, "0099_broken.sql").write_text(
					"CREATE TABLE IF NOT EXISTS t_ok (x INT);\nSELECT * FROM table_that_does_not_exist;\n",
					encoding="utf-8",
				)
				with self.assertRaises(migrate.MigrationError):
					migrate.apply_migrations(conn, Path(tmp))
			with conn.cursor() as cur:
				cur.execute("SELECT COUNT(*) AS n FROM schema_migrations WHERE filename = '0099_broken.sql'")
				self.assertEqual(cur.fetchone()["n"], 0)
				cur.execute("DROP TABLE IF EXISTS t_ok")
			conn.commit()
		finally:
			conn.close()


class TestAccountsAndGrants(SharedDbTestCase):
	def current(self):
		"""What each governed account holds now, read with root (the migrate account cannot see other accounts' grants)."""
		conn = self.connect("root")
		try:
			return accounts.current_grants(conn, self.db_name, accounts.all_accounts(self.env))
		finally:
			conn.close()

	def test_the_grants_are_exactly_the_matrix(self):
		root = self.connect("root")
		try:
			wanted = accounts.expected_grants(root, self.env)
		finally:
			root.close()
		have = self.current()
		self.assertTrue(wanted, "the matrix is not empty")
		for account, objects in wanted.items():
			self.assertEqual(
				{o: set(p) for o, p in objects.items()},
				have[account]["objects"],
				f"{account} differs from the matrix",
			)
			self.assertEqual(have[account]["schema"], set(), f"{account} has a database-wide privilege")

	def test_applying_the_grants_again_ends_in_the_same_state(self):
		before = self.current()
		conn = self.connect("migrate")
		try:
			accounts.apply_object_grants(conn, self.env)
			accounts.apply_object_grants(conn, self.env)
		finally:
			conn.close()
		self.assertEqual(self.current(), before)

	def test_an_extra_privilege_is_revoked_by_the_next_run(self):
		root = self.connect("root")
		with root.cursor() as cur:
			cur.execute(
				f"GRANT SELECT ON `{self.db_name}`.`consumer_grant` TO '{self.users['projector']}'@'%'"
			)
			cur.execute(
				f"GRANT INSERT ON `{self.db_name}`.`entity_customer` TO '{self.users['readapi']}'@'%'"
			)
			cur.execute(f"GRANT SELECT ON `{self.db_name}`.* TO 'report_ro_helpdesk'@'%'")
		root.commit()
		root.close()
		have = self.current()
		self.assertIn(
			"consumer_grant",
			have[self.users["projector"]]["objects"],
			"the extra grant is in place before the run",
		)
		self.assertTrue(have["report_ro_helpdesk"]["schema"])
		conn = self.connect("migrate")
		try:
			accounts.apply_object_grants(conn, self.env)
		finally:
			conn.close()
		have = self.current()
		self.assertNotIn("consumer_grant", have[self.users["projector"]]["objects"])
		self.assertNotIn("entity_customer", have[self.users["readapi"]]["objects"])
		self.assertEqual(have["report_ro_helpdesk"]["schema"], set())

	def test_the_projector_writes_the_entity_and_sync_tables_and_nothing_else(self):
		conn = self.connect("projector")
		try:
			with conn.cursor() as cur:
				cur.execute(
					"INSERT INTO entity_customer (source_app, entity_id, tenant_id, display_name, source_modified, last_seq, contract_version, synced_at) "
					"VALUES ('erpnext', 'C-1', 'ORG-001', 'Example', NOW(6), 1, 1, NOW(6))"
				)
				cur.execute("UPDATE sync_cursor SET last_seq = 1 WHERE source_app = 'x'")
				cur.execute("SELECT COUNT(*) AS n FROM entity_customer")
			conn.commit()
			for table in ("consumer_grant", "consumer_credential", "read_audit", "schema_migrations"):
				denied(self, conn, on_table("SELECT 1 FROM", table, " LIMIT 1"))
			denied(self, conn, "SELECT 1 FROM ctl_consumer_grant LIMIT 1")
			denied(self, conn, "CREATE TABLE evil (x INT)")
			denied(self, conn, "DROP TABLE entity_customer")
		finally:
			conn.close()

	def test_t10_the_read_api_account_reads_views_and_writes_only_the_audit_view(self):
		conn = self.connect("readapi")
		try:
			with conn.cursor() as cur:
				cur.execute("SELECT * FROM v_helpdesk_customer LIMIT 1")
				cur.execute("SELECT credential_id FROM ctl_consumer_credential LIMIT 1")
				cur.execute("SELECT consumer_app FROM ctl_consumer_grant LIMIT 1")
				cur.execute(
					"INSERT INTO ctl_read_audit (read_at, consumer_app, entity_type, row_count, outcome) VALUES (NOW(6), 'helpdesk', 'customer', 1, 'ok')"
				)
			conn.commit()
			for table in BASE_TABLES:
				denied(self, conn, on_table("SELECT 1 FROM", table, " LIMIT 1"))
				denied(self, conn, on_table("INSERT INTO", table, " VALUES ()"))
			denied(self, conn, "UPDATE v_helpdesk_customer SET display_name = 'x'")
			denied(self, conn, "DELETE FROM v_helpdesk_customer")
			denied(self, conn, "INSERT INTO v_helpdesk_customer (entity_id) VALUES ('x')")
			denied(self, conn, "DELETE FROM ctl_read_audit")
			denied(self, conn, "UPDATE ctl_read_audit SET outcome = 'x'")
			denied(self, conn, "SELECT * FROM ctl_read_audit LIMIT 1")
			denied(self, conn, "INSERT INTO ctl_consumer_grant (consumer_app) VALUES ('x')")
			denied(self, conn, "CREATE VIEW leak AS SELECT * FROM entity_customer")
			with conn.cursor() as cur:
				cur.execute("SHOW GRANTS")
				text = " ".join(str(next(iter(row.values()))) for row in cur.fetchall())
			self.assertNotIn("ALL PRIVILEGES", text)
			self.assertNotIn(f"`{self.db_name}`.*", text, "no database-wide grant")
		finally:
			conn.close()

	def test_the_view_hides_tombstones_other_tenants_and_unlisted_columns(self):
		proj = self.connect("projector")
		with proj.cursor() as cur:
			cur.execute("DELETE FROM entity_customer")
			for entity_id, tenant, deleted in (
				("A", "ORG-001", None),
				("B", "ORG-002", None),
				("C", "ORG-001", "2026-11-18 10:00:00"),
			):
				cur.execute(
					"INSERT INTO entity_customer (source_app, entity_id, tenant_id, display_name, territory, source_modified, last_seq, contract_version, deleted_at, synced_at) "
					"VALUES ('erpnext', %s, %s, 'Example', 'T', NOW(6), 1, 1, %s, NOW(6))",
					(entity_id, tenant, deleted),
				)
		proj.commit()
		proj.close()
		conn = self.connect("readapi")
		try:
			with conn.cursor() as cur:
				cur.execute("SELECT entity_id FROM v_helpdesk_customer ORDER BY entity_id")
				self.assertEqual([r["entity_id"] for r in cur.fetchall()], ["A"])
				cur.execute("SELECT * FROM v_helpdesk_customer LIMIT 1")
				columns = set(cur.fetchone())
			conn.commit()
		finally:
			conn.close()
		self.assertEqual(
			columns,
			{
				"entity_id",
				"tenant_id",
				"source_modified",
				"synced_at",
				"display_name",
				"customer_type",
				"customer_group",
				"territory",
				"disabled",
				"primary_contact_id",
			},
		)
		for hidden in ("source_app", "deleted_at", "last_seq", "contract_version"):
			self.assertNotIn(hidden, columns)

	def test_a_report_account_sees_only_its_own_apps_views(self):
		conn = self.connect("report:helpdesk")
		try:
			with conn.cursor() as cur:
				cur.execute("SELECT entity_id FROM v_helpdesk_customer LIMIT 1")
			conn.commit()
			denied(self, conn, "SELECT 1 FROM v_erpnext_org_unit LIMIT 1")
			denied(self, conn, "SELECT 1 FROM entity_customer LIMIT 1")
			denied(
				self,
				conn,
				"INSERT INTO ctl_read_audit (read_at, consumer_app, entity_type, row_count, outcome) VALUES (NOW(6), 'x', 'y', 0, 'z')",
			)
		finally:
			conn.close()

	def test_a_view_for_a_grant_that_is_gone_is_dropped_and_loses_its_privilege(self):
		conn = self.connect("migrate")
		try:
			with conn.cursor() as cur:
				cur.execute(
					"UPDATE consumer_grant SET enabled = 0 WHERE consumer_app = 'helpdesk' AND entity_type = 'org_unit'"
				)
			conn.commit()
			from nxerp.shared_service import grants

			result = views.apply_views(
				conn,
				views.render_all(grants.read_grants(conn)),
				self.db_name,
				accounts.all_accounts(self.env),
			)
			accounts.apply_object_grants(conn, self.env)
			self.assertIn("v_helpdesk_org_unit", result["dropped"])
			self.assertIsNone(self.current()[self.users["readapi"]]["objects"].get("v_helpdesk_org_unit"))
		finally:
			conn.close()


if __name__ == "__main__":
	unittest.main()
