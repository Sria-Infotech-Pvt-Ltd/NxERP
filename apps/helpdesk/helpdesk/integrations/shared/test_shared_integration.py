"""Helpdesk on the new path (Phase 7B): reads through the Read API, changes through the command API, never touches ERPNext.

Stubs replace the network (`requests`); everything else is real (the site, HD Customer, Redis cache, hooks). Fake data and fake tokens only.
Run: bench --site <site> run-tests --app helpdesk --module helpdesk.integrations.shared.test_shared_integration
"""

import inspect
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from helpdesk.integrations.erpnext.utils import should_sync
from helpdesk.integrations.shared import api, command_client, read_client
from helpdesk.integrations.shared.settings import refuse_customer_write

ENV = {
    "NXDESK_SHARED_API_URL": "http://shared-api.example.test:8080",
    "NXDESK_SHARED_API_TOKEN": "aaaaaaaaaaaa.fake-token-for-tests-only",
    "NXDESK_NXERP_URL": "http://nxerp.example.test:8000",
    "NXDESK_COMMAND_API_KEY": "fake-key",
    "NXDESK_COMMAND_API_SECRET": "fake-secret",
}


OK_BODY = {"message": {"ok": True, "source_modified": "2026-11-20 10:05:00.000000"}}


def now_stamp(seconds_ago: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds_ago)).strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )


def row(name="Example Co", seconds_ago=1, **extra) -> dict:
    return {
        "entity_id": "CUST-0001",
        "tenant_id": "ORG-001",
        "source_modified": "2026-11-20 10:00:00.000000",
        "synced_at": now_stamp(seconds_ago),
        "display_name": name,
        "customer_type": "Company",
        "customer_group": "Commercial",
        "territory": "North",
        "disabled": 0,
        "primary_contact_id": "CONTACT-0001",
        **extra,
    }


def response(status=200, body=None, headers=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = body if body is not None else {}
    return r


class SharedCase(FrappeTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict("os.environ", ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        conf = patch.dict(frappe.conf, {"nxerp_shared_read": 1})
        conf.start()
        self.addCleanup(conf.stop)
        self.customer_id = f"CUST-{frappe.generate_hash(length=8)}"
        frappe.cache.delete_value(f"nxdesk_shared:customer:{self.customer_id}")
        self.addCleanup(
            frappe.cache.delete_value, f"nxdesk_shared:customer:{self.customer_id}"
        )

    def hd_customer(self, name=None, **kw):
        doc = frappe.get_doc(
            {
                "doctype": "HD Customer",
                "customer_name": name or f"NXT Shared {frappe.generate_hash(length=6)}",
                "customer_ref_id": self.customer_id,
                **kw,
            }
        )
        doc.flags.ignore_erpnext_sync = True
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc,
            "HD Customer",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc


class TestReadClient(SharedCase):
    def test_a_read_calls_the_read_api_with_the_token_and_returns_the_row_with_its_age(
        self,
    ):
        with patch.object(
            read_client.requests, "get", return_value=response(200, {"data": row()})
        ) as get:
            result = read_client.get_customer(self.customer_id)
        url = get.call_args.args[0]
        self.assertEqual(
            url, f"http://shared-api.example.test:8080/v1/customer/{self.customer_id}"
        )
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"],
            f"Bearer {ENV['NXDESK_SHARED_API_TOKEN']}",
        )
        self.assertEqual(get.call_args.kwargs["timeout"], (2, 3))
        self.assertEqual(
            (result["data"]["display_name"], result["error"], result["stale"]),
            ("Example Co", None, False),
        )
        self.assertIsNotNone(result["synced_at"])

    def test_a_second_read_inside_60_seconds_is_served_from_the_cache(self):
        with patch.object(
            read_client.requests, "get", return_value=response(200, {"data": row()})
        ) as get:
            read_client.get_customer(self.customer_id)
            again = read_client.get_customer(self.customer_id)
        self.assertEqual(get.call_count, 1)
        self.assertTrue(again["from_cache"])

    def test_min_version_bypasses_the_cache_and_is_sent(self):
        with patch.object(
            read_client.requests, "get", return_value=response(200, {"data": row()})
        ) as get:
            read_client.get_customer(self.customer_id)
            read_client.get_customer(
                self.customer_id, min_version="2026-11-20 10:00:00.000000"
            )
        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args.kwargs["params"],
            {"min_version": "2026-11-20 10:00:00.000000"},
        )

    def test_a_row_the_shared_layer_wrote_over_5_minutes_ago_is_flagged_stale(self):
        with patch.object(
            read_client.requests,
            "get",
            return_value=response(200, {"data": row(seconds_ago=400)}),
        ):
            result = read_client.get_customer(self.customer_id)
        self.assertTrue(result["stale"])
        self.assertIsNone(result["error"])

    def test_a_timeout_is_retried_once_then_reported_without_raising(self):
        with patch.object(
            read_client.requests, "get", side_effect=requests.exceptions.Timeout()
        ) as get:
            result = read_client.get_customer(self.customer_id)
        self.assertEqual(get.call_count, 2)
        self.assertEqual((result["data"], result["error"]), (None, "timeout"))

    def test_a_429_is_retried_once_after_the_asked_wait(self):
        answers = [
            response(429, headers={"Retry-After": "1"}),
            response(200, {"data": row()}),
        ]
        with (
            patch.object(read_client.requests, "get", side_effect=answers) as get,
            patch.object(read_client.time, "sleep") as sleep,
        ):
            result = read_client.get_customer(self.customer_id)
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once()
        self.assertEqual(result["data"]["display_name"], "Example Co")

    def test_when_the_read_api_is_down_the_last_known_row_is_shown_flagged(self):
        with patch.object(
            read_client.requests,
            "get",
            return_value=response(200, {"data": row("Last Known Co")}),
        ):
            read_client.get_customer(self.customer_id)
        cached = frappe.cache.get_value(f"nxdesk_shared:customer:{self.customer_id}")
        cached["fetched_at"] -= (
            120  # older than the 60 second cache: the next read goes to the network
        )
        frappe.cache.set_value(
            f"nxdesk_shared:customer:{self.customer_id}", cached, expires_in_sec=3600
        )
        with patch.object(
            read_client.requests,
            "get",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            result = read_client.get_customer(self.customer_id)
        self.assertEqual(result["data"]["display_name"], "Last Known Co")
        self.assertTrue(result["stale"])
        self.assertEqual(result["error"], "unavailable")

    def test_failures_are_named_by_kind_and_never_carry_a_url_or_a_token(self):
        for status, kind in (
            (401, "denied"),
            (403, "denied"),
            (404, "not_found"),
            (500, "unavailable"),
            (202, "pending"),
        ):
            with patch.object(
                read_client.requests, "get", return_value=response(status, {})
            ):
                result = read_client.get_customer(f"{self.customer_id}-{status}")
            self.assertEqual((result["data"], result["error"]), (None, kind), status)
            self.assertNotIn("fake-token", repr(result))
            self.assertNotIn("shared-api", repr(result))

    def test_without_configuration_nothing_is_sent(self):
        with (
            patch.dict(
                "os.environ",
                {"NXDESK_SHARED_API_TOKEN": "", "NXDESK_SHARED_API_URL": ""},
            ),
            patch.object(read_client.requests, "get") as get,
        ):
            result = read_client.get_customer(self.customer_id)
        get.assert_not_called()
        self.assertEqual(result["error"], "not_configured")

    def test_only_the_two_shared_entities_and_plain_ids_are_read(self):
        with patch.object(read_client.requests, "get") as get:
            for entity, entity_id in (
                ("sales_invoice", "X"),
                ("customer", ""),
                ("customer", None),
                ("tax", "1"),
            ):
                self.assertEqual(
                    read_client.get_entity(entity, entity_id)["error"], "bad_request"
                )
        get.assert_not_called()


class TestCommandClient(SharedCase):
    def test_a_command_sends_the_acting_user_and_one_key_and_no_password(self):
        with patch.object(
            command_client.requests, "post", return_value=response(200, OK_BODY)
        ) as post:
            result = command_client.apply(
                "customer",
                "CUST-1",
                "request_change",
                {"territory": "North"},
                idempotency_key="hd-key-0001-abcdef",
                acting_user="agent@example.test",
            )
        self.assertTrue(result["ok"])
        kwargs = post.call_args.kwargs
        self.assertEqual(
            post.call_args.args[0],
            "http://nxerp.example.test:8000/api/method/nxerp.shared.command.apply",
        )
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "hd-key-0001-abcdef")
        self.assertEqual(kwargs["data"]["idempotency_key"], "hd-key-0001-abcdef")
        self.assertEqual(kwargs["data"]["acting_user"], "agent@example.test")
        self.assertEqual(
            set(kwargs["data"]),
            {
                "entity_type",
                "entity_id",
                "command",
                "fields",
                "idempotency_key",
                "acting_user",
            },
        )
        self.assertTrue(
            kwargs["headers"]["Authorization"].startswith("token fake-key:")
        )
        self.assertEqual(kwargs["timeout"], (3, 15))

    def test_a_retry_reuses_the_same_idempotency_key(self):
        answers = [requests.exceptions.Timeout(), response(200, OK_BODY)]
        with patch.object(command_client.requests, "post", side_effect=answers) as post:
            command_client.apply(
                "customer",
                "CUST-1",
                "request_change",
                {"territory": "North"},
                idempotency_key="hd-key-0002-abcdef",
                acting_user="a@example.test",
            )
        keys = {c.kwargs["data"]["idempotency_key"] for c in post.call_args_list}
        headers = {c.kwargs["headers"]["Idempotency-Key"] for c in post.call_args_list}
        self.assertEqual(
            (post.call_count, keys, headers),
            (2, {"hd-key-0002-abcdef"}, {"hd-key-0002-abcdef"}),
        )

    def test_a_5xx_is_retried_once_with_the_same_key_and_then_reported(self):
        with (
            patch.object(
                command_client.requests,
                "post",
                return_value=response(
                    503, {"message": {"error": "unavailable", "message": "retry"}}
                ),
            ) as post,
            self.assertRaises(command_client.CommandFailed) as caught,
        ):
            command_client.apply(
                "customer",
                "CUST-1",
                "request_change",
                {"territory": "North"},
                idempotency_key="hd-key-0003-abcdef",
                acting_user="a@example.test",
            )
        self.assertEqual(post.call_count, 2)
        self.assertEqual(caught.exception.code, "unavailable")

    def test_an_owner_refusal_is_reported_with_its_code_and_not_retried(self):
        for status, code in (
            (403, "forbidden"),
            (409, "version_conflict"),
            (422, "field_not_writable"),
            (404, "not_found"),
        ):
            body = {"message": {"error": code, "message": "no"}}
            with (
                patch.object(
                    command_client.requests, "post", return_value=response(status, body)
                ) as post,
                self.assertRaises(command_client.CommandFailed) as caught,
            ):
                command_client.apply(
                    "customer",
                    "CUST-1",
                    "request_change",
                    {"territory": "North"},
                    idempotency_key="hd-key-0004-abcdef",
                    acting_user="a@example.test",
                )
            self.assertEqual((post.call_count, caught.exception.code), (1, code))

    def test_a_down_nxerp_is_a_clear_error_and_nothing_is_applied_locally(self):
        with (
            patch.object(
                command_client.requests,
                "post",
                side_effect=requests.exceptions.ConnectionError(),
            ) as post,
            self.assertRaises(command_client.CommandFailed) as caught,
        ):
            command_client.apply(
                "customer",
                "CUST-1",
                "request_change",
                {"territory": "North"},
                idempotency_key="hd-key-0005-abcdef",
                acting_user="a@example.test",
            )
        self.assertEqual((post.call_count, caught.exception.code), (2, "unavailable"))
        self.assertIn("nothing was changed", caught.exception.message)

    def test_unconfigured_and_keyless_calls_never_reach_the_network(self):
        with patch.object(command_client.requests, "post") as post:
            with (
                patch.dict("os.environ", {"NXDESK_COMMAND_API_SECRET": ""}),
                self.assertRaises(command_client.CommandFailed) as no_secret,
            ):
                command_client.apply(
                    "customer",
                    "C",
                    "request_change",
                    {"territory": "x"},
                    idempotency_key="hd-key-0006-abcdef",
                    acting_user="a@example.test",
                )
            with self.assertRaises(command_client.CommandFailed) as no_key:
                command_client.apply(
                    "customer",
                    "C",
                    "request_change",
                    {"territory": "x"},
                    idempotency_key="",
                    acting_user="a@example.test",
                )
        post.assert_not_called()
        self.assertEqual(
            (no_secret.exception.code, no_key.exception.code),
            ("not_configured", "bad_request"),
        )

    def test_each_user_action_gets_its_own_key(self):
        self.assertEqual(len({command_client.new_key() for _ in range(50)}), 50)


class TestCustomerCardAndActions(SharedCase):
    def test_t20_with_the_setting_on_the_card_shows_the_fields_from_the_read_api(self):
        hd = self.hd_customer()
        with patch.object(
            read_client.requests,
            "get",
            return_value=response(200, {"data": row("Example Co")}),
        ):
            card = api.get_customer_card(hd.name)
        self.assertEqual(
            (card["enabled"], card["linked"], card["name"], card["banner"]),
            (True, True, "Example Co", False),
        )
        self.assertEqual(card["fields"]["territory"], "North")
        self.assertNotIn("tenant_id", card["fields"])
        self.assertEqual(
            frappe.db.get_value("HD Customer", hd.name, "customer_name_cache"),
            "Example Co",
        )

    def test_t21_a_read_api_timeout_shows_the_cached_name_and_the_banner_and_never_raises(
        self,
    ):
        hd = self.hd_customer()
        with patch.object(
            read_client.requests,
            "get",
            return_value=response(200, {"data": row("Cached Co")}),
        ):
            api.get_customer_card(hd.name)
        cached = frappe.cache.get_value(f"nxdesk_shared:customer:{self.customer_id}")
        cached["fetched_at"] -= 600
        frappe.cache.set_value(
            f"nxdesk_shared:customer:{self.customer_id}", cached, expires_in_sec=3600
        )
        with patch.object(
            read_client.requests, "get", side_effect=requests.exceptions.Timeout()
        ):
            card = api.get_customer_card(hd.name)
        self.assertEqual(
            (card["name"], card["banner"], card["error"], card["stale"]),
            ("Cached Co", True, "timeout", True),
        )

    def test_t21_with_nothing_cached_the_card_still_answers_with_the_remembered_name(
        self,
    ):
        hd = self.hd_customer()
        frappe.db.set_value(
            "HD Customer",
            hd.name,
            "customer_name_cache",
            "Remembered Co",
            update_modified=False,
        )
        with patch.object(
            read_client.requests,
            "get",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            card = api.get_customer_card(hd.name)
        self.assertEqual(
            (card["name"], card["banner"], card["error"]),
            ("Remembered Co", True, "unavailable"),
        )

    def test_the_ticket_side_stays_usable_when_the_read_api_is_down(self):
        """A HD Customer can still be saved, renamed-by-field and used while the Read API is unreachable."""
        hd = self.hd_customer()
        with patch.object(
            read_client.requests,
            "get",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            api.get_customer_card(hd.name)
            hd.customer_type = "Individual"
            hd.save(ignore_permissions=True)
        self.assertEqual(
            frappe.db.get_value("HD Customer", hd.name, "customer_type"), "Individual"
        )

    def test_with_the_setting_off_the_new_path_does_nothing_and_refuses(self):
        hd = self.hd_customer()
        with (
            patch.dict(frappe.conf, {"nxerp_shared_read": 0}),
            patch.object(read_client.requests, "get") as get,
            patch.object(command_client.requests, "post") as post,
        ):
            self.assertEqual(api.get_customer_card(hd.name), {"enabled": False})
            with self.assertRaises(frappe.ValidationError):
                api.update_customer(hd.name, {"territory": "North"})
        get.assert_not_called()
        post.assert_not_called()

    def test_an_update_goes_through_the_command_api_as_the_agent_and_a_retry_reuses_the_key(
        self,
    ):
        hd = self.hd_customer()
        ok = response(
            200,
            {"message": {"ok": True, "source_modified": "2026-11-20 10:05:00.000000"}},
        )
        with patch.object(command_client.requests, "post", return_value=ok) as post:
            first = api.update_customer(hd.name, {"territory": "South"})
            retry = api.update_customer(
                hd.name,
                {"territory": "South"},
                idempotency_key=first["idempotency_key"],
            )
        self.assertEqual(retry["idempotency_key"], first["idempotency_key"])
        sent = [c.kwargs["data"] for c in post.call_args_list]
        self.assertEqual(
            {d["idempotency_key"] for d in sent[1:]}, {first["idempotency_key"]}
        )
        self.assertEqual(sent[0]["acting_user"], frappe.session.user)
        self.assertEqual(
            (sent[0]["entity_type"], sent[0]["entity_id"], sent[0]["command"]),
            ("customer", self.customer_id, "request_change"),
        )
        # nothing about the customer was written in Helpdesk
        self.assertFalse(frappe.db.get_value("HD Customer", hd.name, "domain"))

    def test_a_refused_command_is_shown_to_the_agent_with_its_code_and_changes_nothing(
        self,
    ):
        hd = self.hd_customer()
        refused = response(
            403,
            {
                "message": {
                    "error": "acting_user_forbidden",
                    "message": "The acting user may not use this command",
                }
            },
        )
        with (
            patch.object(command_client.requests, "post", return_value=refused),
            self.assertRaises(frappe.ValidationError) as caught,
        ):
            api.update_customer(hd.name, {"territory": "South"})
        self.assertIn("acting_user_forbidden", str(caught.exception))

    def test_only_the_contract_fields_can_be_asked_for(self):
        hd = self.hd_customer()
        with patch.object(command_client.requests, "post") as post:
            for bad in (
                {"customer_name": "Renamed"},
                {"tax_id": "1"},
                {},
                {"territory": "x", "disabled": 1},
                "not json",
            ):
                with self.assertRaises(frappe.ValidationError, msg=repr(bad)):
                    api.update_customer(hd.name, bad)
        post.assert_not_called()

    def test_an_update_to_the_contact_uses_the_primary_contact_from_the_read_api(self):
        hd = self.hd_customer()
        ok = response(
            200,
            {"message": {"ok": True, "source_modified": "2026-11-20 10:06:00.000000"}},
        )
        with (
            patch.object(
                read_client.requests, "get", return_value=response(200, {"data": row()})
            ),
            patch.object(command_client.requests, "post", return_value=ok) as post,
        ):
            api.update_contact(hd.name, {"phone": "+10000000009"})
        data = post.call_args.kwargs["data"]
        self.assertEqual(
            (data["entity_type"], data["entity_id"], data["command"]),
            ("contact", "CONTACT-0001", "update_contact"),
        )

    def test_no_code_path_creates_or_deletes_an_erpnext_customer(self):
        """Inserting and deleting a HD Customer with the setting on touches no ERPNext Customer: every document operation is watched."""
        seen = []
        real_get_doc, real_delete_doc = frappe.get_doc, frappe.delete_doc

        def watch_get_doc(*args, **kwargs):
            first = args[0] if args else kwargs.get("doctype")
            seen.append(first.get("doctype") if isinstance(first, dict) else first)
            return real_get_doc(*args, **kwargs)

        def watch_delete_doc(doctype, *args, **kwargs):
            seen.append(doctype)
            return real_delete_doc(doctype, *args, **kwargs)

        with (
            patch.object(frappe, "get_doc", side_effect=watch_get_doc),
            patch.object(frappe, "delete_doc", side_effect=watch_delete_doc),
        ):
            hd = self.hd_customer()
            frappe.delete_doc(
                "HD Customer", hd.name, force=True, ignore_permissions=True
            )
        self.assertNotIn("Customer", seen)
        self.assertIn("HD Customer", seen)
        # a path that would have created one now refuses with a clear message
        doc = frappe.get_doc(
            {
                "doctype": "HD Customer",
                "customer_name": f"NXT Refuse {frappe.generate_hash(length=6)}",
            }
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            doc.create_customer_in_erpnext()
        self.assertIn("Ask NXERP", str(caught.exception))
        with self.assertRaises(frappe.ValidationError):
            refuse_customer_write()

    def test_the_shared_package_never_names_an_erpnext_doctype_or_the_database(self):
        folder = Path(inspect.getfile(api)).parent
        for path in folder.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(
                    r'(?<!HD )"Customer"|"Sales Invoice"|"GL Entry"|"Employee"|"Company"',
                    text,
                ),
                path.name,
            )
            self.assertNotIn("frappe.db.sql", text, path.name)
            self.assertNotIn("import nxerp", text, path.name)
            self.assertNotIn("import erpnext", text, path.name)
            self.assertNotIn("from erpnext", text, path.name)


class TestSwitchAndPatch(SharedCase):
    def test_should_sync_is_false_when_the_setting_is_on_and_unchanged_when_off(self):
        with (
            patch.object(frappe.db, "get_single_value", return_value=1),
            patch.object(
                frappe,
                "get_installed_apps",
                return_value=["frappe", "erpnext", "helpdesk"],
            ),
        ):
            self.assertFalse(should_sync(), "on: the mirror hooks do nothing")
            with patch.dict(frappe.conf, {"nxerp_shared_read": 0}):
                self.assertTrue(should_sync(), "off: exactly today's rule")
            with patch.dict(frappe.conf, {}, clear=False):
                frappe.conf.pop("nxerp_shared_read", None)
                self.assertTrue(should_sync(), "unset: exactly today's rule")

    def test_the_rename_patch_is_idempotent_and_keeps_values(self):
        from helpdesk.patches import (
            rename_erpnext_customer_to_customer_ref_id as patch_module,
        )

        patch_module.execute()  # already renamed: a no-op
        patch_module.execute()
        columns = patch_module._columns()
        self.assertIn("customer_ref_id", columns)
        self.assertIn("customer_name_cache", columns)
        self.assertNotIn("erpnext_customer", columns)
        # both columns present (the model sync ran first): values are copied and the old column dropped
        frappe.db.sql_ddl(
            "ALTER TABLE `tabHD Customer` ADD COLUMN `erpnext_customer` varchar(140)"
        )
        hd = frappe.get_doc(
            {
                "doctype": "HD Customer",
                "customer_name": f"NXT Patch {frappe.generate_hash(length=6)}",
            }
        )
        hd.flags.ignore_erpnext_sync = True
        hd.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc,
            "HD Customer",
            hd.name,
            force=True,
            ignore_permissions=True,
        )
        frappe.db.sql(
            "UPDATE `tabHD Customer` SET erpnext_customer = %s WHERE name = %s",
            ("CUST-PATCH-1", hd.name),
        )
        patch_module.execute()
        patch_module.execute()
        self.assertEqual(
            frappe.db.get_value("HD Customer", hd.name, "customer_ref_id"),
            "CUST-PATCH-1",
        )
        self.assertNotIn("erpnext_customer", patch_module._columns())
