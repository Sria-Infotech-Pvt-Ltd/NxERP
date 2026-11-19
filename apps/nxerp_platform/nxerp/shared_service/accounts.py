"""Accounts and grants of the shared database. No frappe.

`create_accounts` (root, one-shot) renders `schema/0002_accounts_and_views.sql.tmpl`: the database, and the migrate, projector
and Read API accounts (plus optional `report_ro_<app>` accounts). It never prints a password: passwords are bound parameters.

`apply_object_grants` (migrate or root) then makes each account's per-object privileges exactly the matrix of blueprint 2.5, after
the tables and views exist, revoking anything extra, so running it again converges instead of accumulating:

	shared_projector  SELECT, INSERT, UPDATE, DELETE on the entity tables and the sync control tables
	shared_readapi    SELECT on the v_* views and three ctl_* views, INSERT on ctl_read_audit; nothing on any base table
	report_ro_<app>   SELECT on that app's v_<app>_* views only; no INSERT
	no account has a database-wide or global privilege (shared_migrate excepted, on this database only)
"""

import os
import re
from pathlib import Path
from string import Template

from nxerp.shared_service import sqlutil

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"
TEMPLATE = SCHEMA_DIR / "0002_accounts_and_views.sql.tmpl"
PASSWORD_MARKER = re.compile(r"\{\{pw:([a-z_]+)\}\}")

PROJECTOR_CONTROL_TABLES = ("sync_cursor", "sync_dead_letter", "sync_metric", "contract_registry")
READAPI_READ_VIEWS = ("ctl_consumer_grant", "ctl_consumer_credential", "ctl_sync_metric")
READAPI_AUDIT_VIEW = "ctl_read_audit"
PROJECTOR_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})
NO_SUCH_GRANT = (1141, 1147)


def account_names(env=None) -> dict:
	"""The account names in use (defaults, overridable by SHARED_<ROLE>_USER) and the report_ro account list."""
	env = os.environ if env is None else env
	names = {
		"migrate": env.get("SHARED_MIGRATE_USER", "shared_migrate"),
		"projector": env.get("SHARED_PROJECTOR_USER", "shared_projector"),
		"readapi": env.get("SHARED_READAPI_USER", "shared_readapi"),
	}
	for value in names.values():
		sqlutil.ident(value)
	apps = [a.strip() for a in env.get("SHARED_REPORT_RO_APPS", "").split(",") if a.strip()]
	for app in apps:
		sqlutil.ident(f"report_ro_{app}")
	return {**names, "report_apps": apps}


def render_accounts(env=None) -> list:
	"""[(sql, params)] for the account template and the report accounts. Passwords are parameters; nothing printable holds one."""
	env = os.environ if env is None else env
	names = account_names(env)
	db = env.get("SHARED_DB_NAME", "nxerp_shared")
	sqlutil.ident(db)
	ssl = "REQUIRE SSL" if env.get("SHARED_DB_REQUIRE_SSL", "0") == "1" else "REQUIRE NONE"
	passwords = {
		role: env.get(f"SHARED_{role.upper()}_PASSWORD", "") for role in ("migrate", "projector", "readapi")
	}
	statements = sqlutil.split_statements(TEMPLATE.read_text(encoding="utf-8"))
	substitutions = {
		"db": db,
		"migrate": names["migrate"],
		"projector": names["projector"],
		"readapi": names["readapi"],
		"ssl": ssl,
	}
	rendered = []
	for app in names["report_apps"]:
		user = f"report_ro_{app}"
		passwords[user] = env.get(f"SHARED_REPORT_RO_{app.upper()}_PASSWORD", "")
		statements += [
			f"CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY {{{{pw:{user}}}}} ${{ssl}}",
			f"ALTER USER '{user}'@'%' IDENTIFIED BY {{{{pw:{user}}}}} ${{ssl}}",
		]
	for statement in statements:
		bound = bool(PASSWORD_MARKER.search(statement))
		# PyMySQL interpolates only when parameters are passed: escape a literal % (the '%' host) only in those statements
		text = Template(statement.replace("%", "%%") if bound else statement).substitute(substitutions)
		params = []
		for role in PASSWORD_MARKER.findall(text):
			if not passwords.get(role):
				raise ValueError(f"the password for {role} is not set in the environment")
			params.append(passwords[role])
		rendered.append((PASSWORD_MARKER.sub("%s", text), tuple(params)))
	return rendered


def create_accounts(root_conn, env=None) -> list:
	"""Create the database and accounts (idempotent: existing accounts get the current password). Returns the account names only."""
	env = os.environ if env is None else env
	with root_conn.cursor() as cur:
		for sql, params in render_accounts(env):
			cur.execute(sql, params or None)
	root_conn.commit()
	names = account_names(env)
	accounts = [
		names["migrate"],
		names["projector"],
		names["readapi"],
		*[f"report_ro_{a}" for a in names["report_apps"]],
	]
	apply_object_grants(root_conn, env)
	return accounts


def _objects(conn, db: str) -> dict:
	with conn.cursor() as cur:
		cur.execute(
			"SELECT TABLE_NAME AS name, TABLE_TYPE AS kind FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s",
			(db,),
		)
		return {row["name"]: row["kind"] for row in cur.fetchall()}


def _report_views(conn, report_app: str) -> set:
	"""The exact views of one app: v_<app>_<entity> for each enabled grant row (a prefix match would confuse app names)."""
	with conn.cursor() as cur:
		cur.execute(
			"SELECT entity_type FROM consumer_grant WHERE consumer_app = %s AND enabled = 1", (report_app,)
		)
		return {f"v_{report_app}_{row['entity_type']}" for row in cur.fetchall()}


def expected_grants(conn, env=None) -> dict:
	"""{account: {object: frozenset(privileges)}}: the matrix, computed from the objects that exist now."""
	env = os.environ if env is None else env
	names = account_names(env)
	db = env.get("SHARED_DB_NAME", "nxerp_shared")
	objects = _objects(conn, db)
	matrix = {
		names["projector"]: {
			name: PROJECTOR_PRIVILEGES
			for name in objects
			if name.startswith("entity_") or name in PROJECTOR_CONTROL_TABLES
		},
		names["readapi"]: {
			**{
				name: frozenset({"SELECT"})
				for name, kind in objects.items()
				if kind == "VIEW" and name.startswith("v_")
			},
			**{name: frozenset({"SELECT"}) for name in READAPI_READ_VIEWS if name in objects},
			**({READAPI_AUDIT_VIEW: frozenset({"INSERT"})} if READAPI_AUDIT_VIEW in objects else {}),
		},
	}
	if "consumer_grant" in objects:
		for app in names["report_apps"]:
			matrix[f"report_ro_{app}"] = {
				v: frozenset({"SELECT"}) for v in _report_views(conn, app) if v in objects
			}
	else:
		for app in names["report_apps"]:
			matrix[f"report_ro_{app}"] = {}
	return matrix


def current_grants(conn, db: str, accounts: list) -> dict:
	"""{account: {"objects": {object: set}, "schema": set}} read from information_schema (what this connection may see)."""
	result = {account: {"objects": {}, "schema": set()} for account in accounts}
	with conn.cursor() as cur:
		cur.execute(
			"SELECT GRANTEE AS grantee, TABLE_NAME AS obj, PRIVILEGE_TYPE AS priv FROM information_schema.TABLE_PRIVILEGES WHERE TABLE_SCHEMA = %s",
			(db,),
		)
		for row in cur.fetchall():
			user = row["grantee"].split("@")[0].strip("'")
			if user in result:
				result[user]["objects"].setdefault(row["obj"], set()).add(row["priv"])
		cur.execute(
			"SELECT GRANTEE AS grantee, PRIVILEGE_TYPE AS priv FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA = %s",
			(db,),
		)
		for row in cur.fetchall():
			user = row["grantee"].split("@")[0].strip("'")
			if user in result:
				result[user]["schema"].add(row["priv"])
	return result


def all_accounts(env=None) -> list:
	"""The projector, Read API and report accounts (the migrate account is not governed by the matrix)."""
	names = account_names(env)
	return [names["projector"], names["readapi"], *[f"report_ro_{app}" for app in names["report_apps"]]]


def revoke_everything(cur, db: str, obj: str | None, account: str) -> None:
	"""Remove every privilege `account` holds on one object (or on the whole database when obj is None). No error if it has none.

	Reading another account's grants needs privileges the migrate account does not have, so the grants are made exact by
	revoking and re-granting instead of by comparing."""
	target = f"{sqlutil.ident(db)}.*" if obj is None else f"{sqlutil.ident(db)}.{sqlutil.ident(obj)}"
	try:
		cur.execute(f"REVOKE ALL PRIVILEGES ON {target} FROM '{account}'@'%'")  # nosec B608 - identifiers validated
	except Exception as exc:
		# 1141 (database level) and 1147 (object level): "there is no such grant", which is the state we want
		if not (type(exc).__module__.startswith("pymysql") and exc.args and exc.args[0] in NO_SUCH_GRANT):
			raise


def apply_object_grants(conn, env=None) -> dict:
	"""Make the per-object privileges of the projector, Read API and report accounts exactly the matrix. Returns counts only.

	For each account: revoke everything on the database and on every object that exists, then grant exactly the matrix. Running it
	again therefore ends in the same state, whatever the starting state (including a privilege added by hand)."""
	env = os.environ if env is None else env
	db = env.get("SHARED_DB_NAME", "nxerp_shared")
	sqlutil.ident(db)
	matrix = expected_grants(conn, env)
	objects = sorted(_objects(conn, db))
	summary = {}
	with conn.cursor() as cur:
		for account, wanted in matrix.items():
			revoke_everything(cur, db, None, account)
			for obj in objects:
				revoke_everything(cur, db, obj, account)
			privileges = 0
			for obj, privs in wanted.items():
				cur.execute(
					f"GRANT {', '.join(sorted(privs))} ON {sqlutil.ident(db)}.{sqlutil.ident(obj)} TO '{account}'@'%'"
				)  # nosec B608
				privileges += len(privs)
			summary[account] = {"objects": len(wanted), "privileges": privileges}
	conn.commit()
	return summary
