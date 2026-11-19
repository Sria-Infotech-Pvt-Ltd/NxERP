"""Live checks of a running shared stack, run by `scripts/shared_audit.sh`. No frappe. Prints `PASS|FAIL|INFO name detail` lines.

    accounts   (root)  the grant matrix is exact, and the Read API and projector accounts really cannot do what they must not
    probe      (ops or api container) really try, as the app account itself, what it must not do
    columns    (root)  no column of an entity table or view looks like secret, tax, credit, payment or health data
    api        (ops)   the live Read API over HTTP with a real token: 401, 403, 405, field denial, row counts
    sample     (ops)   N random shared rows compared field by field with the owner's own feed

Lines hold counts, names and PASS/FAIL, never a token, a password, a key or a row value.
"""

import http.client
import json
import os
import random
import sys

import pymysql

from nxerp.shared import registry
from nxerp.shared_service import accounts, apply, config, db, feedclient

FORBIDDEN_FRAGMENTS = (
	"password",
	"secret",
	"token",
	"key",
	"tax",
	"salary",
	"iban",
	"bank",
	"ssn",
	"health",
	"credit",
	"payment",
	"payroll",
)
# column names allowed although they contain a fragment (contract names that are about something else)
ALLOWED_COLUMNS: set = set()

failures = 0


def line(kind: str, name: str, detail: str = "") -> None:
	global failures
	if kind == "FAIL":
		failures += 1
	print(f"{kind} {name} {detail}".rstrip(), flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
	line("PASS" if ok else "FAIL", name, detail if not ok else "")


def audit_accounts() -> None:
	conn = db.connect(db.settings_from_env("root"))
	try:
		name = os.environ.get("SHARED_DB_NAME", "nxerp_shared")
		expected = accounts.expected_grants(conn)
		current = accounts.current_grants(conn, name, list(expected))
		for account, objects in expected.items():
			have = current[account]["objects"]
			check(
				f"grants.{account}.objects",
				set(have) == set(objects),
				f"expected {sorted(objects)} got {sorted(have)}",
			)
			wrong = [o for o, privs in objects.items() if set(have.get(o, ())) != set(privs)]
			check(f"grants.{account}.privileges", not wrong, f"differs on {wrong}")
			check(
				f"grants.{account}.no-schema-level",
				not current[account]["schema"],
				f"{sorted(current[account]['schema'])}",
			)
		with conn.cursor() as cur:
			cur.execute(
				"SELECT COUNT(*) AS n FROM information_schema.USER_PRIVILEGES WHERE GRANTEE LIKE %s AND PRIVILEGE_TYPE <> 'USAGE'",
				("%shared\\_%",),
			)
			check(
				"grants.no-global-privileges",
				cur.fetchone()["n"] == 0,
				"an app account holds a global privilege",
			)
	finally:
		conn.close()


DENIED_CODES = (1044, 1142, 1143, 1370, 1045)
CANNOT = {
	"readapi": [
		("reads-a-base-table", "SELECT 1 FROM entity_customer LIMIT 1"),
		("reads-the-credential-table", "SELECT 1 FROM consumer_credential LIMIT 1"),
		("reads-the-cursor-table", "SELECT 1 FROM sync_cursor LIMIT 1"),
		("deletes-from-an-entity-view", "DELETE FROM v_helpdesk_customer"),
		("updates-the-grant-view", "UPDATE ctl_consumer_grant SET enabled = 0"),
		("drops-a-view", "DROP VIEW v_helpdesk_customer"),
		("creates-a-table", "CREATE TABLE should_not_exist (a INT)"),
	],
	"projector": [
		("reads-the-audit", "SELECT 1 FROM read_audit LIMIT 1"),
		("reads-the-credential-table", "SELECT 1 FROM consumer_credential LIMIT 1"),
		("drops-an-entity-table", "DROP TABLE entity_customer"),
		("creates-a-table", "CREATE TABLE should_not_exist (a INT)"),
		("alters-an-entity-table", "ALTER TABLE entity_customer ADD COLUMN x INT"),
	],
}
CAN = {
	"readapi": [("selects-an-entity-view", "SELECT COUNT(*) FROM v_helpdesk_customer")],
	"projector": [("selects-an-entity-table", "SELECT COUNT(*) FROM entity_customer")],
}


def audit_probe(role: str = "") -> None:
	"""Really try, as this role's own account, what it must not be able to do (the role whose password is in this container's env)."""
	role = role or ("readapi" if os.environ.get("SHARED_READAPI_PASSWORD") else "projector")
	conn = db.connect(db.settings_from_env(role), autocommit=True)
	try:
		with conn.cursor() as cur:
			for name, statement in CAN[role]:
				try:
					cur.execute(statement)
					check(f"probe.{role}.can-{name}", True)
				except pymysql.MySQLError as exc:
					check(f"probe.{role}.can-{name}", False, f"error {exc.args[0]}")
			for name, statement in CANNOT[role]:
				try:
					cur.execute(statement)
					check(f"probe.{role}.cannot-{name}", False, "the statement WORKED")
				except pymysql.MySQLError as exc:
					check(
						f"probe.{role}.cannot-{name}",
						exc.args[0] in DENIED_CODES,
						f"unexpected error {exc.args[0]}",
					)
	finally:
		conn.close()


def audit_columns() -> None:
	conn = db.connect(db.settings_from_env("root"))
	try:
		with conn.cursor() as cur:
			cur.execute(
				"SELECT TABLE_NAME AS t, COLUMN_NAME AS c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s "
				"AND (TABLE_NAME LIKE 'entity\\_%%' OR TABLE_NAME LIKE 'v\\_%%')",
				(os.environ.get("SHARED_DB_NAME", "nxerp_shared"),),
			)
			rows = cur.fetchall()
	finally:
		conn.close()
	bad = [
		f"{r['t']}.{r['c']}"
		for r in rows
		if any(f in r["c"].lower() for f in FORBIDDEN_FRAGMENTS) and r["c"] not in ALLOWED_COLUMNS
	]
	check("columns.no-sensitive-names", not bad, f"suspicious columns: {bad}")
	line("INFO", "columns.checked", f"{len(rows)} columns in entity tables and views")


class Http:
	def __init__(self, token: str | None = None):
		self.token = token

	def call(self, method: str, path: str, token=...):
		conn = http.client.HTTPConnection("shared-api", 8080, timeout=10)
		headers = {}
		use = self.token if token is ... else token
		if use:
			headers["Authorization"] = f"Bearer {use}"
		conn.request(method, path, headers=headers)
		response = conn.getresponse()
		body = response.read().decode("utf-8", "replace")
		conn.close()
		try:
			data = json.loads(body)
		except ValueError:
			data = None
		return response.status, data


def audit_api() -> None:
	token_file = os.environ.get("SHARED_API_TOKEN_FILE", "/run/nxerp-shared/read-helpdesk.token")
	with open(token_file, encoding="ascii") as handle:
		token = handle.read().strip()
	api = Http(token)
	status, _ = api.call("GET", "/v1/health", token=None)
	check("api.health", status == 200, str(status))
	for label, path, method, tok, want in [
		("no-token", "/v1/customer", "GET", None, 401),
		("wrong-token", "/v1/customer", "GET", "0" * 12 + "." + "0" * 64, 401),
		("not-granted-entity", "/v1/ticket_summary", "GET", ..., 403),
		("field-outside-grant", "/v1/customer?fields=tax_id", "GET", ..., 403),
		("post", "/v1/customer", "POST", ..., 405),
		("put", "/v1/customer/X", "PUT", ..., 405),
		("delete", "/v1/customer/X", "DELETE", ..., 405),
		("unknown-entity", "/v1/nothing", "GET", ..., 404),
		("unknown-id", "/v1/customer/NO-SUCH-ID", "GET", ..., 404),
		("bad-limit", "/v1/customer?limit=0", "GET", ..., 422),
	]:
		status, _ = api.call(method, path, token=tok)
		check(f"api.{label}", status == want, f"expected {want} got {status}")
	status, data = api.call("GET", "/v1/customer?limit=200")
	ok = status == 200 and isinstance(data, dict)
	check("api.list-customers", ok, str(status))
	if ok:
		contract = registry.get_contract("customer")
		granted = {f["shared"] for f in contract["fields"]}
		extra = (
			{key for row in data["data"] for key in row}
			- granted
			- {"entity_id", "tenant_id", "source_modified", "synced_at"}
		)
		check("api.no-field-outside-contract", not extra, f"{sorted(extra)}")
		line("INFO", "api.customers", f"{len(data['data'])} rows")


def audit_sample(count: int = 20) -> None:
	env = os.environ
	settings = db.settings_from_env("projector")
	conn = db.connect(settings, autocommit=True)
	checked = mismatched = 0
	try:
		for source in config.load_sources():
			client = feedclient.FeedClient(source, config.read_key(source))
			for contract in registry.load_contracts().values():
				table = f"entity_{contract['entity_type']}"
				with conn.cursor() as cur:
					cur.execute(f"SELECT entity_id FROM `{table}` WHERE deleted_at IS NULL", ())  # nosec B608
					ids = [r["entity_id"] for r in cur.fetchall()]
				if not ids:
					continue
				picked = random.SystemRandom().sample(ids, min(count, len(ids)))
				try:
					owner = client.snapshot_by_ids(contract["entity_type"], picked)
				except feedclient.FeedRejected:
					continue
				found = {row["entity_id"]: row for row in owner.get("rows", owner.get("items", []))}
				for entity_id in picked:
					if entity_id not in found:
						continue
					with conn.cursor() as cur:
						cur.execute(f"SELECT * FROM `{table}` WHERE entity_id = %s", (entity_id,))  # nosec B608
						row = cur.fetchone()
					checked += 1
					if apply.row_hash(contract, row) != _owner_hash(found[entity_id]):
						mismatched += 1
				line(
					"INFO",
					f"sample.{source.app_key}.{contract['entity_type']}",
					f"{len(picked)} ids picked of {len(ids)}",
				)
	finally:
		conn.close()
	check("sample.rows-equal-owner", checked > 0 and mismatched == 0, f"{mismatched} of {checked} differ")
	line("INFO", "sample.checked", str(checked))
	_ = env


def _owner_hash(item: dict) -> str:
	from nxerp.shared import payload

	return payload.payload_hash(item.get("payload", item))


def main(argv: list) -> int:
	checks = {
		"accounts": audit_accounts,
		"probe": audit_probe,
		"columns": audit_columns,
		"api": audit_api,
		"sample": audit_sample,
	}
	if len(argv) != 2 or argv[1] not in checks:
		print(
			"usage: python -m nxerp.shared_service.audit accounts|probe|columns|api|sample", file=sys.stderr
		)
		return 2
	try:
		checks[argv[1]]()
	except (pymysql.MySQLError, OSError, ValueError, KeyError, feedclient.FeedUnavailable) as exc:
		line("FAIL", f"{argv[1]}.error", type(exc).__name__)
	return 1 if failures else 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
