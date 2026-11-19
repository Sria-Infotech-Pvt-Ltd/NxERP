"""Views, SQL helpers and account rendering: unit tests, no database.

python -m unittest discover apps/nxerp_platform/nxerp/shared_service/tests -t apps/nxerp_platform
"""

import re
import secrets
import sys
import unittest
from pathlib import Path
from types import MappingProxyType

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared import registry
from nxerp.shared_service import accounts, grants, migrate, sqlutil, views

# throwaway values made at run time: no password-looking literal in the source
FAKE_MIGRATE, FAKE_PROJECTOR, FAKE_READAPI, FAKE_REPORT = (secrets.token_urlsafe(12) for _ in range(4))

GOLDEN_HELPDESK_CUSTOMER = (
	"CREATE OR REPLACE SQL SECURITY DEFINER VIEW `v_helpdesk_customer` AS\n"
	"SELECT `entity_id`, `tenant_id`, `source_modified`, `synced_at`, `display_name`, `customer_type`, `customer_group`, "
	"`territory`, `disabled`, `primary_contact_id`\n"
	"FROM `entity_customer`\n"
	"WHERE `deleted_at` IS NULL AND `tenant_id` = 'ORG-001'"
)


def grant_rows():
	return [
		{
			"consumer_app": app,
			"entity_type": entity,
			"granted_fields": want["granted_fields"],
			"tenant_id": want["tenant_id"],
		}
		for (app, entity), want in grants.desired_from_contracts().items()
	]


class TestViews(unittest.TestCase):
	def customer(self):
		return registry.get_contract("customer")

	def test_golden_output_for_the_helpdesk_customer_view(self):
		sql = views.render_view(
			self.customer(), "helpdesk", registry.consumers_of("customer")["helpdesk"], tenant="ORG-001"
		)
		self.assertEqual(sql, GOLDEN_HELPDESK_CUSTOMER)

	def test_a_view_without_a_tenant_has_no_tenant_filter(self):
		sql = views.render_view(registry.get_contract("org_unit"), "helpdesk", ["name", "parent_id"])
		self.assertTrue(sql.endswith("WHERE `deleted_at` IS NULL"))
		self.assertIn("`entity_id`, `tenant_id`, `source_modified`, `synced_at`, `name`, `parent_id`", sql)

	def test_columns_follow_the_contract_order_not_the_order_given(self):
		sql = views.render_view(self.customer(), "helpdesk", ["territory", "display_name"])
		self.assertIn("`display_name`, `territory`", sql)

	def test_a_field_that_is_not_in_the_contract_is_refused(self):
		for bad in ("tax_id", "email_id", "credit_limits", "no_such_field", "name"):
			with self.assertRaises(views.ViewError, msg=bad):
				views.render_view(self.customer(), "helpdesk", ["display_name", bad])

	def test_a_field_the_contract_does_not_grant_to_that_app_is_refused(self):
		contract = {**self.customer(), "consumers": {"helpdesk": ["display_name"]}}
		with self.assertRaises(views.ViewError):
			views.render_view(contract, "helpdesk", ["display_name", "territory"])

	def test_an_app_that_is_not_a_consumer_is_refused(self):
		with self.assertRaises(views.ViewError):
			views.render_view(self.customer(), "erpnext", ["display_name"])

	def test_a_planned_contract_and_an_empty_grant_are_refused(self):
		with self.assertRaises(views.ViewError):
			views.render_view(registry.get_contract("employee_ref"), "helpdesk", ["display_name"])
		with self.assertRaises(views.ViewError):
			views.render_view(self.customer(), "helpdesk", [])

	def test_an_unsafe_tenant_value_never_reaches_the_sql(self):
		for tenant in ("x'; DROP TABLE entity_customer; --", "a b", "a`b", ""):
			if tenant == "":
				continue  # an empty tenant means no filter
			with self.assertRaises(ValueError, msg=tenant):
				views.render_view(self.customer(), "helpdesk", ["display_name"], tenant=tenant)

	def test_render_all_makes_one_view_per_active_consumer_grant(self):
		rendered = views.render_all(grant_rows())
		self.assertEqual(
			sorted(rendered),
			[
				"v_erpnext_org_unit",
				"v_erpnext_ticket_summary",
				"v_helpdesk_contact",
				"v_helpdesk_customer",
				"v_helpdesk_org_unit",
			],
		)

	def test_no_generated_view_exposes_an_excluded_or_system_secret_column(self):
		forbidden = {
			"tax_id",
			"credit_limits",
			"payment_terms",
			"default_price_list",
			"email_id",
			"mobile_no",
			"deleted_at",
			"contract_version",
			"last_seq",
			"source_app",
		}
		for name, sql in views.render_all(grant_rows()).items():
			header = sql.split("\nFROM")[0]
			for column in forbidden:
				self.assertNotIn(f"`{column}`", header, f"{name} exposes {column}")

	def test_a_view_can_only_read_its_own_entity_table(self):
		for name, sql in views.render_all(grant_rows()).items():
			entity = name.split("_", 2)[2]
			self.assertIn(f"FROM `entity_{entity}`", sql)


class TestGrants(unittest.TestCase):
	def test_grants_come_only_from_active_contracts_and_stay_inside_them(self):
		desired = grants.desired_from_contracts()
		for (app, entity), want in desired.items():
			contract = registry.get_contract(entity)
			self.assertEqual(contract["status"], "active", entity)
			self.assertTrue(set(want["granted_fields"]) <= set(contract["consumers"][app]), (app, entity))
		for planned in ("employee_ref", "project_ref", "user_ref"):
			self.assertFalse([k for k in desired if k[1] == planned])

	def test_the_tenant_comes_from_the_contract(self):
		desired = grants.desired_from_contracts()
		self.assertEqual(desired[("helpdesk", "customer")]["tenant_id"], "ORG-001")
		self.assertIsNone(desired[("helpdesk", "org_unit")]["tenant_id"], "an org unit is its own tenant")


class TestSqlUtil(unittest.TestCase):
	def test_identifiers_are_validated(self):
		self.assertEqual(sqlutil.ident("entity_customer"), "`entity_customer`")
		for bad in ("a-b", "a b", "a`;DROP", "", "x" * 65, None, 5, "é"):
			with self.assertRaises(ValueError, msg=repr(bad)):
				sqlutil.ident(bad)

	def test_select_builds_from_validated_names_only(self):
		self.assertEqual(
			sqlutil.select(
				"v_helpdesk_customer",
				["entity_id", "display_name"],
				where="`tenant_id` = %s",
				order_by="`entity_id`",
				limit=True,
			),
			"SELECT `entity_id`, `display_name` FROM `v_helpdesk_customer` WHERE `tenant_id` = %s ORDER BY `entity_id` LIMIT %s",
		)
		with self.assertRaises(ValueError):
			sqlutil.select("v_x", ["a; DROP TABLE x"])
		with self.assertRaises(ValueError):
			sqlutil.select("v_x", [])

	def test_split_statements_handles_comments_and_quotes(self):
		script = (
			"-- a comment with a ; semicolon\n"
			"CREATE TABLE a (x VARCHAR(3) DEFAULT ';');  -- trailing\n"
			"/* block ; comment */ INSERT INTO a VALUES ('it''s; fine');\n"
			"SELECT `we;ird`;\n"
		)
		self.assertEqual(
			sqlutil.split_statements(script),
			[
				"CREATE TABLE a (x VARCHAR(3) DEFAULT ';')",
				"INSERT INTO a VALUES ('it''s; fine')",
				"SELECT `we;ird`",
			],
		)

	def test_the_real_migrations_split_into_statements(self):
		for path in migrate.schema_files():
			statements = sqlutil.split_statements(path.read_text(encoding="utf-8"))
			self.assertTrue(statements, path.name)
			for statement in statements:
				self.assertNotIn("--", statement.replace("'--'", ""), path.name)

	def test_migrations_are_numbered_in_order_and_the_template_is_not_one(self):
		names = [p.name for p in migrate.schema_files()]
		self.assertEqual(names, sorted(names))
		self.assertEqual(names[0], "0001_shared_model.sql")
		self.assertIn("0003_read_api_support.sql", names)
		self.assertFalse([n for n in names if n.endswith(".tmpl")])


class TestAccountRendering(unittest.TestCase):
	ENV = MappingProxyType(
		{
			"SHARED_DB_NAME": "nxerp_shared",
			"SHARED_MIGRATE_PASSWORD": FAKE_MIGRATE,
			"SHARED_PROJECTOR_PASSWORD": FAKE_PROJECTOR,
			"SHARED_READAPI_PASSWORD": FAKE_READAPI,
		}
	)

	def test_no_statement_contains_a_password_and_each_password_is_a_bound_parameter(self):
		rendered = accounts.render_accounts(dict(self.ENV))
		secrets_ = [v for k, v in self.ENV.items() if k.endswith("_PASSWORD")]
		for sql, params in rendered:
			for secret in secrets_:
				self.assertNotIn(secret, sql)
			self.assertEqual(sql.count("%s"), len(params))
		bound = [p for _, params in rendered for p in params]
		self.assertEqual(sorted(set(bound)), sorted(secrets_))

	def test_a_literal_percent_host_is_escaped_only_where_parameters_are_bound(self):
		for sql, params in accounts.render_accounts(dict(self.ENV)):
			if params:
				self.assertIn("'@'%%'", sql)
			elif "GRANT" in sql:
				self.assertIn("'@'%'", sql)
				self.assertNotIn("%%", sql)

	def test_the_projector_and_the_api_get_no_privilege_in_the_template(self):
		text = " ".join(sql for sql, _ in accounts.render_accounts(dict(self.ENV)))
		self.assertEqual(
			len(re.findall(r"GRANT (?!OPTION)", text)), 1, "one GRANT statement: the migrate account"
		)
		self.assertIn("GRANT ALL PRIVILEGES ON `nxerp_shared`.* TO 'shared_migrate'", text)

	def test_ssl_is_required_only_when_asked(self):
		off = " ".join(sql for sql, _ in accounts.render_accounts(dict(self.ENV)))
		on = " ".join(
			sql for sql, _ in accounts.render_accounts({**dict(self.ENV), "SHARED_DB_REQUIRE_SSL": "1"})
		)
		self.assertIn("REQUIRE NONE", off)
		self.assertNotIn("REQUIRE SSL", off)
		self.assertIn("REQUIRE SSL", on)
		self.assertNotIn("REQUIRE NONE", on)

	def test_report_accounts_are_created_only_when_listed(self):
		self.assertNotIn("report_ro_", " ".join(sql for sql, _ in accounts.render_accounts(dict(self.ENV))))
		env = {
			**self.ENV,
			"SHARED_REPORT_RO_APPS": "helpdesk",
			"SHARED_REPORT_RO_HELPDESK_PASSWORD": FAKE_REPORT,
		}
		self.assertIn("'report_ro_helpdesk'", " ".join(sql for sql, _ in accounts.render_accounts(env)))

	def test_a_missing_password_and_an_unsafe_name_are_refused(self):
		with self.assertRaises(ValueError):
			accounts.render_accounts({k: v for k, v in self.ENV.items() if k != "SHARED_READAPI_PASSWORD"})
		with self.assertRaises(ValueError):
			accounts.render_accounts({**dict(self.ENV), "SHARED_REPORT_RO_APPS": "x'; DROP USER 'root"})
		with self.assertRaises(ValueError):
			accounts.render_accounts({**dict(self.ENV), "SHARED_DB_NAME": "db`; DROP DATABASE mysql; --"})

	def test_the_settings_object_never_prints_a_password(self):
		from nxerp.shared_service import db

		settings = db.settings_from_env("projector", {"SHARED_PROJECTOR_PASSWORD": FAKE_PROJECTOR})
		self.assertNotIn(FAKE_PROJECTOR, repr(settings))
		self.assertNotIn(FAKE_PROJECTOR, str(settings))


if __name__ == "__main__":
	unittest.main()
