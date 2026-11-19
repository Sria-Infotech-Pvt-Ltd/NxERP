"""Helpers for the shared-service tests. No frappe.

Database-backed tests need a MariaDB server and the root password in the environment (`SHARED_DB_HOST`, `SHARED_DB_ROOT_PASSWORD`);
`deploy/scripts/shared.sh test` runs them in a one-shot container on the shared stack's private network. Without a reachable
server they skip, so the unit tests still run anywhere. Each test class creates its own throwaway database and accounts (random
names) and drops them afterwards: the stack's real database and accounts are never touched.
"""

import os
import secrets
import unittest

from nxerp.shared_service import accounts, db, grants, migrate, views

SKIP_REASON = "no reachable MariaDB with SHARED_DB_ROOT_PASSWORD set (run: deploy/scripts/shared.sh test)"


def root_connection(database=None):
	"""A root connection, or None when no server is configured or reachable."""
	try:
		import pymysql  # a missing driver is the same as no server

		return db.connect(db.settings_from_env("root"), database=database)
	except (ImportError, db.SettingsError, OSError) as exc:
		del exc
		return None
	except Exception as exc:  # pymysql.err.OperationalError and friends
		if type(exc).__module__.startswith("pymysql"):
			return None
		raise


class SharedDbTestCase(unittest.TestCase):
	"""A throwaway shared database with migrations applied and its own accounts (migrate, projector, readapi, one report account)."""

	with_accounts = True
	report_apps = ("helpdesk",)

	@classmethod
	def setUpClass(cls):
		cls.root = root_connection()
		if cls.root is None:
			raise unittest.SkipTest(SKIP_REASON)
		suffix = secrets.token_hex(4)
		cls.db_name = f"shared_t_{suffix}"
		cls.users = {
			"migrate": f"t_migrate_{suffix}",
			"projector": f"t_projector_{suffix}",
			"readapi": f"t_readapi_{suffix}",
		}
		passwords = {role: secrets.token_urlsafe(18) for role in ("migrate", "projector", "readapi")}
		cls.env = {
			**{k: v for k, v in os.environ.items() if k.startswith("SHARED_DB_")},
			"SHARED_DB_NAME": cls.db_name,
			"SHARED_MIGRATE_USER": cls.users["migrate"],
			"SHARED_PROJECTOR_USER": cls.users["projector"],
			"SHARED_READAPI_USER": cls.users["readapi"],
			"SHARED_MIGRATE_PASSWORD": passwords["migrate"],
			"SHARED_PROJECTOR_PASSWORD": passwords["projector"],
			"SHARED_READAPI_PASSWORD": passwords["readapi"],
			"SHARED_REPORT_RO_APPS": ",".join(cls.report_apps),
		}
		for app in cls.report_apps:
			cls.env[f"SHARED_REPORT_RO_{app.upper()}_PASSWORD"] = secrets.token_urlsafe(18)
		if cls.with_accounts:
			accounts.create_accounts(cls.root, cls.env)
			conn = cls.connect("migrate")
			try:
				migrate.apply_migrations(conn)
				grants.sync(conn)
				views.apply_views(
					conn,
					views.render_all(grants.read_grants(conn)),
					cls.db_name,
					accounts.all_accounts(cls.env),
				)
				accounts.apply_object_grants(conn, cls.env)
			finally:
				conn.close()
		else:
			with cls.root.cursor() as cur:
				cur.execute(
					f"CREATE DATABASE `{cls.db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
				)
			cls.root.commit()
			conn = db.connect(db.settings_from_env("root"), database=cls.db_name)
			try:
				migrate.apply_migrations(conn)
			finally:
				conn.close()

	@classmethod
	def tearDownClass(cls):
		if getattr(cls, "root", None) is None:
			return
		with cls.root.cursor() as cur:
			cur.execute(f"DROP DATABASE IF EXISTS `{cls.db_name}`")
			users = list(cls.users.values()) + [f"report_ro_{app}" for app in cls.report_apps]
			if cls.with_accounts:
				for user in users:
					cur.execute(f"DROP USER IF EXISTS '{user}'@'%'")
		cls.root.commit()
		cls.root.close()

	@classmethod
	def connect(cls, role: str, autocommit: bool = False):
		"""A connection to the throwaway database as `migrate`, `projector`, `readapi` or `root`."""
		if role.startswith("report:"):
			app = role.split(":", 1)[1]
			settings = db.DbSettings(
				host=os.environ.get("SHARED_DB_HOST", "shared-db"),
				port=int(os.environ.get("SHARED_DB_PORT", "3306")),
				name=cls.db_name,
				user=f"report_ro_{app}",
				password=cls.env[f"SHARED_REPORT_RO_{app.upper()}_PASSWORD"],
			)
			return db.connect(settings, autocommit=autocommit)
		if role == "root":
			return db.connect(db.settings_from_env("root"), database=cls.db_name, autocommit=autocommit)
		return db.connect(db.settings_from_env(role, cls.env), autocommit=autocommit)
