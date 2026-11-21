"""The Read API (T9, T10): tokens, grants, fields, tenants, tombstones, methods, audit, limits. Real views on a real MariaDB.

Skipped without a reachable server: run `deploy/scripts/shared.sh test -p "test_readapi*"`.
"""

import hashlib
import json
import sys
import threading
import time
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared_service import accounts, credentials, grants, views
from nxerp.shared_service.tests.support import SharedDbTestCase

try:
	from werkzeug.test import Client

	from nxerp.shared_service.readapi import MAX_LIMIT, ReadApi
except ImportError:  # the image has Werkzeug and PyMySQL; a host without them skips
	Client = ReadApi = None
	MAX_LIMIT = 200

STAMP_OLD = "2026-11-18 10:00:00.000000"
STAMP_NEW = "2026-11-18 11:00:00.000000"
OWN = object()
SYSTEM = {"entity_id", "tenant_id", "source_modified", "synced_at"}


class ReadApiCase(SharedDbTestCase):
	report_apps = ()

	@classmethod
	def setUpClass(cls):
		if Client is None:
			raise unittest.SkipTest("Werkzeug is not installed")
		super().setUpClass()
		conn = cls.connect("migrate")
		try:
			cls.helpdesk = credentials.issue(conn, "helpdesk")["token"]
			cls.helpdesk_second = credentials.issue(conn, "helpdesk")["token"]
			cls.erpnext = credentials.issue(conn, "erpnext")["token"]
		finally:
			conn.close()

	def setUp(self):
		self.write_rows()
		root = self.connect("root")
		with root.cursor() as cur:
			cur.execute("DELETE FROM read_audit")
		root.commit()
		root.close()
		self.api = self.new_api()
		self.client = Client(self.api)

	def new_api(self, **kwargs) -> ReadApi:
		options = {"cache_seconds": 0, "audit_background": False, "rate_per_minute": 100000}
		options.update(kwargs)
		return ReadApi(connect=lambda: self.connect("readapi", autocommit=True), **options)

	def write_rows(self) -> None:
		"""Customers A (live), B (another tenant), C (tombstone) and five pagination rows; org units X and Y."""
		proj = self.connect("projector")
		with proj.cursor() as cur:
			cur.execute("DELETE FROM entity_customer")
			cur.execute("DELETE FROM entity_org_unit")
			customers = [
				("A", "ORG-001", "Example A", "T-north", None),
				("B", "ORG-002", "Example B", "T-south", None),
				("C", "ORG-001", "Gone C", None, "2026-11-18 09:00:00"),
			] + [(f"P{i}", "ORG-001", f"Page {i}", "T-page", None) for i in range(1, 6)]
			for entity_id, tenant, name, territory, deleted in customers:
				cur.execute(
					"INSERT INTO entity_customer (source_app, entity_id, tenant_id, display_name, territory, source_modified, last_seq, "
					"contract_version, deleted_at, synced_at) VALUES ('erpnext', %s, %s, %s, %s, %s, 1, 1, %s, NOW(6))",
					(entity_id, tenant, name, territory, STAMP_OLD, deleted),
				)
			for entity_id in ("ORG-X", "ORG-Y"):
				cur.execute(
					"INSERT INTO entity_org_unit (source_app, entity_id, tenant_id, name, source_modified, last_seq, contract_version, synced_at) "
					"VALUES ('erpnext', %s, %s, %s, %s, 1, 1, NOW(6))",
					(entity_id, entity_id, f"Org {entity_id}", STAMP_OLD),
				)
		proj.commit()
		proj.close()

	def get(
		self,
		path: str,
		token: str | None = OWN,
		headers: dict | None = None,
		method: str = "GET",
		client=None,
	):
		token = self.helpdesk if token is OWN else token
		sent = dict(headers or {})
		if token:
			sent["Authorization"] = f"Bearer {token}"
		return (client or self.client).open(path, method=method, headers=sent)

	def audit_rows(self) -> list:
		self.api.audit.flush()
		root = self.connect("root")
		try:
			with root.cursor() as cur:
				cur.execute("SELECT * FROM read_audit ORDER BY id")
				return list(cur.fetchall())
		finally:
			root.close()


class TestAuthentication(ReadApiCase):
	def test_t9_no_token_is_401_and_so_is_a_garbage_or_wrong_token(self):
		bad = [
			None,
			"garbage",
			"a" * 12 + "." + "b" * 64,
			self.helpdesk[:-1] + ("0" if self.helpdesk[-1] != "0" else "1"),
		]
		for token in bad:
			response = self.get("/v1/customer/A", token=token)
			self.assertEqual(response.status_code, 401, token)
			self.assertEqual(response.get_json()["error"]["code"], "unauthorized")
			self.assertIn("Bearer", response.headers["WWW-Authenticate"])

	def test_the_scheme_must_be_bearer(self):
		response = self.client.get("/v1/customer/A", headers={"Authorization": "Basic " + self.helpdesk})
		self.assertEqual(response.status_code, 401)

	def test_a_token_that_expired_or_was_revoked_stops_working(self):
		conn = self.connect("migrate")
		try:
			expiring = credentials.issue(conn, "helpdesk", expires_days=1)
			revoked = credentials.issue(conn, "helpdesk")
			self.assertEqual(self.get("/v1/customer/A", token=expiring["token"]).status_code, 200)
			with conn.cursor() as cur:
				cur.execute(
					"UPDATE consumer_credential SET expires_at = NOW(6) - INTERVAL 1 MINUTE WHERE credential_id = %s",
					(expiring["credential_id"],),
				)
			conn.commit()
			credentials.revoke(conn, credential_id=revoked["credential_id"])
		finally:
			conn.close()
		self.api.clear_caches()
		self.assertEqual(self.get("/v1/customer/A", token=expiring["token"]).status_code, 401)
		self.assertEqual(self.get("/v1/customer/A", token=revoked["token"]).status_code, 401)
		self.assertEqual(self.get("/v1/customer/A").status_code, 200, "the other tokens are unaffected")

	def test_rotation_retires_the_old_token_at_once_or_after_a_grace_period(self):
		conn = self.connect("migrate")
		try:
			old = credentials.issue(conn, "erpnext")["token"]
			new = credentials.rotate(conn, "erpnext")["token"]
			self.api.clear_caches()
			self.assertEqual(self.get("/v1/org_unit/ORG-X", token=old).status_code, 401)
			self.assertEqual(self.get("/v1/org_unit/ORG-X", token=new).status_code, 200)
			older = new
			newest = credentials.rotate(conn, "erpnext", grace_hours=1)["token"]
			self.api.clear_caches()
			self.assertEqual(
				self.get("/v1/org_unit/ORG-X", token=older).status_code, 200, "valid during the grace period"
			)
			self.assertEqual(self.get("/v1/org_unit/ORG-X", token=newest).status_code, 200)
		finally:
			conn.close()

	def test_a_token_is_never_stored_only_its_scrypt_hash(self):
		root = self.connect("root")
		try:
			with root.cursor() as cur:
				cur.execute(
					"SELECT credential_id, salt, secret_hash, scrypt_n, scrypt_r, scrypt_p FROM consumer_credential"
				)
				rows = cur.fetchall()
		finally:
			root.close()
		secret = self.helpdesk.split(".")[1]
		for row in rows:
			self.assertEqual(len(row["secret_hash"]), 128)
			self.assertNotIn(secret, json.dumps(row, default=str))
			self.assertGreaterEqual(row["scrypt_n"], 2**14)
		row = next(r for r in rows if r["credential_id"] == self.helpdesk.split(".")[0])
		self.assertTrue(credentials.verify_secret(secret, row))
		self.assertFalse(credentials.verify_secret("0" * 64, row))
		self.assertFalse(
			credentials.verify_secret(secret, None), "an unknown id does the same work and says no"
		)

	def test_a_token_for_an_app_without_any_grant_cannot_be_issued(self):
		conn = self.connect("migrate")
		try:
			with self.assertRaises(credentials.CredentialError):
				credentials.issue(conn, "nobody")
		finally:
			conn.close()


class TestAuthorisation(ReadApiCase):
	def test_t9_another_apps_token_is_403_on_an_entity_it_has_no_grant_for(self):
		response = self.get("/v1/customer/A", token=self.erpnext)
		self.assertEqual((response.status_code, response.get_json()["error"]["code"]), (403, "not_granted"))
		self.assertEqual(self.get("/v1/org_unit/ORG-X", token=self.erpnext).status_code, 200)

	def test_t9_a_field_outside_the_grant_is_403_not_an_empty_column(self):
		for fields in (
			"tax_id",
			"display_name,tax_id",
			"source_app",
			"deleted_at",
			"no_such_field",
			"credit_limits",
		):
			response = self.get(f"/v1/customer/A?fields={fields}")
			self.assertEqual(
				(response.status_code, response.get_json()["error"]["code"]),
				(403, "field_not_granted"),
				fields,
			)
		self.assertEqual(self.get("/v1/customer?fields=tax_id").status_code, 403)

	def test_a_granted_field_is_returned_with_the_version_columns(self):
		data = self.get("/v1/customer/A").get_json()["data"]
		self.assertEqual(
			set(data),
			SYSTEM
			| {
				"display_name",
				"customer_type",
				"customer_group",
				"territory",
				"disabled",
				"primary_contact_id",
			},
		)
		self.assertEqual(
			(data["entity_id"], data["display_name"], data["territory"], data["tenant_id"]),
			("A", "Example A", "T-north", "ORG-001"),
		)
		self.assertEqual(data["source_modified"], STAMP_OLD)
		self.assertRegex(data["synced_at"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}$")

	def test_asking_for_some_fields_returns_only_those_plus_the_system_columns(self):
		data = self.get("/v1/customer/A?fields=display_name").get_json()["data"]
		self.assertEqual(set(data), SYSTEM | {"display_name"})

	def test_tombstones_other_tenants_and_unknown_ids_all_look_the_same_404(self):
		bodies = set()
		for entity_id in ("C", "B", "NO-SUCH"):
			response = self.get(f"/v1/customer/{entity_id}")
			self.assertEqual(response.status_code, 404, entity_id)
			bodies.add(response.get_data(as_text=True))
		self.assertEqual(len(bodies), 1, "nothing tells the caller whether the id exists elsewhere")

	def test_the_tenant_filter_applies_and_a_tenant_outside_the_grant_is_refused(self):
		listed = self.get("/v1/customer?limit=200").get_json()["data"]
		self.assertEqual({r["tenant_id"] for r in listed}, {"ORG-001"})
		self.assertNotIn("B", {r["entity_id"] for r in listed})
		self.assertNotIn("C", {r["entity_id"] for r in listed}, "tombstones are hidden")
		self.assertEqual(self.get("/v1/customer/A?tenant=ORG-001").status_code, 200)
		other = self.get("/v1/customer/B?tenant=ORG-002")
		self.assertEqual((other.status_code, other.get_json()["error"]["code"]), (403, "tenant_not_granted"))

	def test_a_grant_without_a_tenant_may_name_one(self):
		everything = self.get("/v1/org_unit?limit=200", token=self.erpnext).get_json()["data"]
		self.assertEqual({r["entity_id"] for r in everything}, {"ORG-X", "ORG-Y"})
		only = self.get("/v1/org_unit?tenant=ORG-Y", token=self.erpnext).get_json()["data"]
		self.assertEqual([r["entity_id"] for r in only], ["ORG-Y"])

	def test_unknown_and_planned_entities_are_404(self):
		for path in (
			"/v1/nothing",
			"/v1/employee_ref",
			"/v1/user_ref/x",
			"/v1/Customer",
			"/v1/customer/A/extra",
			"/other",
		):
			self.assertEqual(self.get(path).status_code, 404, path)

	def test_the_response_never_holds_a_column_the_grant_does_not_list_even_if_the_view_has_one(self):
		conn = self.connect("migrate")
		try:
			with conn.cursor() as cur:
				cur.execute(
					"CREATE OR REPLACE SQL SECURITY DEFINER VIEW v_helpdesk_customer AS SELECT entity_id, tenant_id, source_modified, synced_at, "
					"display_name, customer_type, customer_group, territory, disabled, primary_contact_id, source_app, last_seq, deleted_at "
					"FROM entity_customer WHERE deleted_at IS NULL AND tenant_id = 'ORG-001'"
				)
			conn.commit()
			data = self.get("/v1/customer/A").get_json()["data"]
			self.assertFalse({"source_app", "last_seq", "deleted_at"} & set(data))
			listed = self.get("/v1/customer").get_json()["data"][0]
			self.assertFalse({"source_app", "last_seq", "deleted_at"} & set(listed))
		finally:
			views.apply_views(
				conn,
				views.render_all(grants.read_grants(conn)),
				self.db_name,
				accounts.all_accounts(self.env),
			)
			accounts.apply_object_grants(conn, self.env)
			conn.close()


class TestMethodsParametersAndLimits(ReadApiCase):
	def test_t9_every_method_but_get_is_405_with_or_without_a_token(self):
		for method in ("POST", "PUT", "DELETE", "PATCH"):
			for token in (OWN, None):
				for path in ("/v1/customer", "/v1/customer/A", "/v1/health"):
					response = self.get(path, token=token, method=method)
					self.assertEqual(response.status_code, 405, (method, path))
					self.assertEqual(response.headers["Allow"], "GET")
		self.assertEqual(
			self.get("/v1/customer/A").get_json()["data"]["display_name"], "Example A", "nothing was written"
		)

	def test_bad_parameters_are_422(self):
		for query in (
			"limit=0",
			f"limit={MAX_LIMIT + 1}",
			"limit=abc",
			"limit=-1",
			"min_version=garbage",
			"after=" + "x" * 141,
		):
			self.assertEqual(self.get("/v1/customer?" + query).status_code, 422, query)
		self.assertEqual(self.get("/v1/customer/A?min_version=yesterday").status_code, 422)

	def test_pages_follow_after_with_no_gaps_or_repeats(self):
		seen, after = [], ""
		for _ in range(10):
			page = self.get(f"/v1/customer?limit=2&after={after}").get_json()
			seen += [r["entity_id"] for r in page["data"]]
			if not page["next_after"]:
				break
			after = page["next_after"]
		self.assertEqual(seen, sorted(seen))
		self.assertEqual(seen, ["A", "P1", "P2", "P3", "P4", "P5"])

	def test_health_needs_no_token_and_is_not_audited(self):
		before = len(self.audit_rows())
		response = self.get("/v1/health", token=None)
		self.assertEqual((response.status_code, response.get_json()), (200, {"status": "ok"}))
		self.assertEqual(len(self.audit_rows()), before)

	def test_metrics_need_a_token_and_hold_numbers_not_row_values(self):
		self.assertEqual(self.get("/v1/metrics", token=None).status_code, 401)
		body = self.get("/v1/metrics").get_json()
		self.assertIn("projector", body)
		self.assertIn("api", body)
		self.assertNotIn("Example A", json.dumps(body))

	def test_metrics_in_text_form_name_every_metric_and_json_stays_the_default(self):
		self.assertEqual(self.get("/v1/metrics?format=text", token=None).status_code, 401)
		response = self.get("/v1/metrics?format=text")
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.content_type.startswith("text/plain"))
		text = response.get_data(as_text=True)
		for name in (
			"outbox_lag_seconds",
			"outbox_pending",
			"projector_errors",
			"dead_letters",
			"reconcile_drift",
			"rebuild_age_seconds",
			"read_api_requests",
			"read_api_denied",
		):
			self.assertIn(f"# TYPE {name} ", text, name)
		self.assertNotIn("Example A", text)
		self.assertIn("projector", self.get("/v1/metrics").get_json())  # the Helpdesk client still reads JSON
		accepted = self.get("/v1/metrics", headers={"Accept": "text/plain"})
		self.assertTrue(accepted.content_type.startswith("text/plain"))

	def test_the_rate_limit_is_per_token(self):
		api = self.new_api(rate_per_minute=3)
		client = Client(api)
		codes = [self.get("/v1/customer/A", client=client).status_code for _ in range(5)]
		self.assertEqual(codes, [200, 200, 200, 429, 429])
		limited = self.get("/v1/customer/A", client=client)
		self.assertGreaterEqual(int(limited.headers["Retry-After"]), 1)
		self.assertEqual(limited.get_json()["error"]["code"], "rate_limited")
		self.assertEqual(
			self.get("/v1/org_unit/ORG-X", token=self.erpnext, client=client).status_code,
			200,
			"another token has its own bucket",
		)
		self.assertEqual(
			self.get("/v1/customer/A", token=self.helpdesk_second, client=client).status_code, 200
		)

	def test_a_database_that_is_down_is_503_without_sql_or_a_trace(self):
		import pymysql

		def down():
			raise pymysql.err.OperationalError(2003, "Can't connect to MySQL server")

		api = ReadApi(connect=down, audit_background=False, cache_seconds=0)
		client = Client(api)
		for path in ("/v1/health", "/v1/customer/A", "/v1/customer"):
			response = client.get(path, headers={"Authorization": "Bearer " + self.helpdesk})
			self.assertEqual(response.status_code, 503, path)
			text = response.get_data(as_text=True)
			self.assertEqual(response.get_json()["error"]["code"], "database_unavailable")
			for forbidden in ("SELECT", "pymysql", "Traceback", "2003", "MySQL"):
				self.assertNotIn(forbidden, text)


class TestFreshness(ReadApiCase):
	def test_min_version_waits_for_the_projector_then_returns_the_new_row(self):
		def projector_catches_up():
			time.sleep(0.5)
			conn = self.connect("projector")
			with conn.cursor() as cur:
				cur.execute(
					"UPDATE entity_customer SET display_name = 'Example A, updated', source_modified = %s WHERE entity_id = 'A'",
					(STAMP_NEW,),
				)
			conn.commit()
			conn.close()

		thread = threading.Thread(target=projector_catches_up)
		thread.start()
		started = time.monotonic()
		response = self.get(f"/v1/customer/A?min_version={STAMP_NEW}")
		thread.join()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.get_json()["data"]["display_name"], "Example A, updated")
		self.assertTrue(0.3 < time.monotonic() - started < 2.0)

	def test_min_version_that_never_arrives_is_202_pending_after_about_two_seconds(self):
		started = time.monotonic()
		response = self.get("/v1/customer/A?min_version=2030-01-01 00:00:00")
		elapsed = time.monotonic() - started
		self.assertEqual((response.status_code, response.get_json()["status"]), (202, "pending"))
		self.assertTrue(1.8 < elapsed < 4.0, elapsed)
		listed = self.get("/v1/customer?min_version=2030-01-01 00:00:00")
		self.assertEqual(listed.status_code, 202)

	def test_a_row_already_new_enough_returns_at_once(self):
		started = time.monotonic()
		self.assertEqual(self.get(f"/v1/customer/A?min_version={STAMP_OLD}").status_code, 200)
		self.assertEqual(self.get(f"/v1/customer?min_version={STAMP_OLD}").status_code, 200)
		self.assertLess(time.monotonic() - started, 1.5)


class TestAudit(ReadApiCase):
	def test_t9_every_call_is_audited_including_the_denied_ones(self):
		self.get("/v1/customer/A", headers={"X-Acting-User": "user@example.test", "X-Request-Id": "req-123"})
		self.get("/v1/customer/A", token=None)
		self.get("/v1/customer/A", token=self.erpnext)
		self.get("/v1/customer/A?fields=tax_id")
		self.get("/v1/customer/NO-SUCH")
		self.get("/v1/customer/A", method="POST")
		self.get("/v1/customer/B?tenant=ORG-002")
		self.get("/v1/customer?limit=0")
		self.get("/v1/customer?limit=2")
		rows = self.audit_rows()
		self.assertEqual(len(rows), 9)
		outcomes = [r["outcome"] for r in rows]
		self.assertEqual(
			outcomes,
			[
				"ok",
				"denied_unauthorized",
				"denied_not_granted",
				"denied_field",
				"not_found",
				"denied_method",
				"denied_tenant",
				"bad_request",
				"ok",
			],
		)
		first = rows[0]
		self.assertEqual(
			(first["consumer_app"], first["entity_type"], first["entity_id"], first["row_count"]),
			("helpdesk", "customer", "A", 1),
		)
		self.assertEqual((first["acting_user"], first["request_id"]), ("user@example.test", "req-123"))
		self.assertEqual(first["ids_hash"], hashlib.sha256(b"A").hexdigest())
		self.assertIn("display_name", json.loads(first["fields_returned"]))
		self.assertEqual(rows[1]["consumer_app"], "-", "an unauthenticated call is audited with no app")
		self.assertEqual(rows[2]["consumer_app"], "erpnext")
		self.assertEqual(rows[-1]["row_count"], 2)
		self.assertTrue(rows[-1]["ids_hash"] and len(rows[-1]["ids_hash"]) == 64)

	def test_the_audit_never_stores_a_token_or_a_row_value(self):
		self.get("/v1/customer/A?fields=display_name")
		self.get("/v1/customer/A", token=None)
		text = json.dumps(self.audit_rows(), default=str)
		self.assertNotIn(self.helpdesk.split(".")[1], text)
		self.assertNotIn("Example A", text)

	def test_audit_rows_are_written_in_batches_in_the_background(self):
		api = self.new_api(audit_background=True)
		client = Client(api)
		for _ in range(5):
			self.get("/v1/customer/A", client=client)
		deadline = time.monotonic() + 3
		count = 0
		while time.monotonic() < deadline and count < 5:
			time.sleep(0.2)
			root = self.connect("root")
			with root.cursor() as cur:
				cur.execute("SELECT COUNT(*) AS n FROM read_audit")
				count = cur.fetchone()["n"]
			root.close()
		self.assertGreaterEqual(count, 5)


if __name__ == "__main__":
	unittest.main()
