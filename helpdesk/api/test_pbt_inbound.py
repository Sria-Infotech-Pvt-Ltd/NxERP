"""The read-only task API PBT calls (helpdesk.api.pbt_inbound.get_tasks)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.pbt_inbound import get_tasks
from helpdesk.test_utils import (
    call_pbt_inbound,
    make_task,
    mock_external_api,
    pbt_milestone,
    pbt_project,
    pbt_routes,
)


class TestPBTInboundTasks(FrappeTestCase):
    def setUp(self):
        # Tasks already on the site are left alone; assertions only look at the ones made here.
        self.existing = set(frappe.get_all("HD Task", filters={"pbt_project_id": ["is", "set"]}, pluck="name"))
        handler = pbt_routes(
            [pbt_project("5", "Portal"), pbt_project("8", "Billing")],
            {"5": [pbt_milestone(17, "M1")], "8": []},
        )
        with mock_external_api(handler):
            self.on_milestone = make_task("On M1", pbt_project_id="5", pbt_milestone_id="17", due_date="2026-11-10")
            self.blocked = make_task("Blocked", pbt_project_id="5", status="Blocked", blocked_reason="Waiting")
            self.other_project = make_task("Billing work", pbt_project_id="8")
        self.local = make_task("Local only")

    def tearDown(self):
        frappe.db.rollback()

    def task_ids(self, body) -> set:
        return {row["task_id"] for row in body["data"]["results"]} - self.existing

    def test_is_a_public_get_endpoint(self):
        self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[get_tasks], ["GET"])
        self.assertIn(get_tasks, frappe.guest_methods)

    def test_missing_wrong_or_unconfigured_key_is_401_without_data(self):
        for key, keys in ((None, "k1"), ("wrong", "k1"), ("", "k1"), ("k1", ""), ("k1", " , ")):
            with self.subTest(key=key, keys=keys):
                status, body = call_pbt_inbound(key, keys=keys)
                self.assertEqual(status, 401)
                self.assertEqual((body["status"], body["data"]), ("error", None))

    def test_every_configured_key_works_for_rotation(self):
        for key in ("test-inbound-old", "test-inbound-new"):
            with self.subTest(key=key):
                self.assertEqual(call_pbt_inbound(key)[0], 200)

    def test_only_tasks_linked_to_pbt_are_returned_in_the_pbt_envelope(self):
        status, body = call_pbt_inbound("test-inbound-new")
        self.assertEqual((status, body["status"]), (200, "success"))
        self.assertEqual(self.task_ids(body), {self.on_milestone.name, self.blocked.name, self.other_project.name})
        self.assertEqual(body["data"]["count"], 3 + len(self.existing))
        self.assertTrue(body["data"]["time_zone"])

    def test_row_carries_the_pbt_references_and_dates(self):
        _, body = call_pbt_inbound("test-inbound-new", milestone_id="17")
        row = next(r for r in body["data"]["results"] if r["task_id"] == self.on_milestone.name)
        self.assertEqual(
            {k: row[k] for k in ("task_id", "project_id", "project_name", "milestone_id", "milestone_name", "end_date")},
            {
                "task_id": self.on_milestone.name,
                "project_id": "5",
                "project_name": "Portal",
                "milestone_id": "17",
                "milestone_name": "M1",
                "end_date": "2026-11-10",
            },
        )
        self.assertTrue(row["url"].endswith(f"/helpdesk/tasks/{self.on_milestone.name}"))

    def test_project_milestone_and_status_filters(self):
        cases = (
            ({"project_id": "5"}, {self.on_milestone.name, self.blocked.name}),
            ({"project_id": "8"}, {self.other_project.name}),
            ({"project_id": "404"}, set()),
            ({"project_id": "5", "status": "Blocked"}, {self.blocked.name}),
            ({"status": "Planned,Blocked"}, {self.on_milestone.name, self.blocked.name, self.other_project.name}),
        )
        for params, expected in cases:
            with self.subTest(**params):
                _, body = call_pbt_inbound("test-inbound-new", **params)
                self.assertEqual(self.task_ids(body), expected)

    def test_updated_since_returns_only_later_changes(self):
        frappe.db.set_value("HD Task", self.other_project.name, "modified", "2026-01-01 00:00:00", update_modified=False)
        _, body = call_pbt_inbound("test-inbound-new", updated_since="2026-06-01")
        self.assertNotIn(self.other_project.name, {r["task_id"] for r in body["data"]["results"]})

    def test_paging_and_page_size_cap(self):
        # Tasks already on the site can sit in project "5" too, so the last page is worked out from them.
        total = 2 + len({n for n in self.existing if frappe.db.get_value("HD Task", n, "pbt_project_id") == "5"})
        _, body = call_pbt_inbound("test-inbound-new", project_id="5", page_size=1, page=total)
        self.assertEqual((body["data"]["total_pages"], len(body["data"]["results"])), (total, 1))
        _, body = call_pbt_inbound("test-inbound-new", page_size=500)
        self.assertEqual(body["data"]["page_size"], 100)

    def test_invalid_filters_are_400(self):
        for params in (
            {"status": "Done"},
            {"page": "x"},
            {"page": 0},
            {"updated_since": "yesterday-ish"},
            {"project_id": "5/../8"},
            {"milestone_id": "a b"},
        ):
            with self.subTest(**params):
                status, body = call_pbt_inbound("test-inbound-new", **params)
                self.assertEqual((status, body["status"]), (400, "error"))
