"""HRMS and PBT proxies and the external references on HD Task.

Every external call is mocked (see mock_external_api). The HRMS response shape is UNVERIFIED,
so those tests pin the mapping table in helpdesk.integrations.external.hrms, not a live contract.
"""

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.task import (
    create_task,
    get_hrms_employee,
    get_hrms_employees,
    get_pbt_projects,
)
from helpdesk.integrations.external import hrms, pbt
from helpdesk.integrations.external.client import ExternalAPIError
from helpdesk.test_utils import (
    INVALID_JSON,
    FakeResponse,
    create_agent,
    hrms_employee,
    make_plain_user,
    make_task,
    make_task_freelancer,
    make_task_project,
    mock_external_api,
    pbt_page,
    pbt_project,
)

AGENT = "ext-agent@example.com"
MAPPED = "ext-mapped@example.com"
DISABLED = "ext-disabled@example.com"
PLAIN = "ext-plain@example.com"


def pbt_only(results=None, **kwargs):
    """Handler that serves `results` for PBT and fails any other host."""

    def handler(url, params, headers):
        assert url.startswith("http://pbt.invalid"), url
        return pbt_page(results if results is not None else [pbt_project()], **kwargs)

    return handler


_DEFAULT = object()


def hrms_only(list_rows=_DEFAULT, detail=None):
    """Handler that serves `list_rows` (default: one employee; None is passed through as a body)."""

    def handler(url, params, headers):
        assert url.startswith("http://hrms.invalid"), url
        if url.endswith("/employees/"):
            return FakeResponse([hrms_employee()] if list_rows is _DEFAULT else list_rows)
        return FakeResponse(detail)

    return handler


def both(pbt_results, employee):
    """PBT serves `pbt_results`; HRMS serves `employee` as the detail answer."""

    def handler(url, params, headers):
        if url.startswith("http://pbt.invalid"):
            return pbt_page(pbt_results)
        return FakeResponse(employee)

    return handler


class TestPBTClient(FrappeTestCase):
    def test_follows_every_page(self):
        pages = {
            1: pbt_page([pbt_project("P-1")], page=1, total_pages=3, count=3),
            2: pbt_page([pbt_project("P-2")], page=2, total_pages=3, count=3),
            3: pbt_page([pbt_project("P-3")], page=3, total_pages=3, count=3),
        }
        with mock_external_api(lambda url, params, headers: pages[params["page"]]) as calls:
            projects = pbt.get_all_projects()
        self.assertEqual([p["project_id"] for p in projects], ["P-1", "P-2", "P-3"])
        self.assertEqual([c[1]["page"] for c in calls], [1, 2, 3])

    def test_page_cap_stops_a_runaway_upstream(self):
        def endless(url, params, headers):
            return pbt_page([pbt_project()], page=params["page"], total_pages=10**6)

        with mock_external_api(endless) as calls:
            pbt.get_all_projects()
        self.assertEqual(len(calls), pbt.MAX_PAGES)

    def test_search_and_status_filters_are_sent(self):
        with mock_external_api(pbt_only([])) as calls:
            pbt.get_all_projects(search="portal", status="uat", client_id="C-9")
        params = calls[0][1]
        self.assertEqual((params["search"], params["status"], params["client_id"]), ("portal", "uat", "C-9"))

    def test_unknown_status_is_rejected_without_a_request(self):
        with mock_external_api(pbt_only()) as calls:
            with self.assertRaises(ExternalAPIError):
                pbt.get_all_projects(status="bogus")
        self.assertEqual(calls, [])

    def test_key_is_sent_as_a_header_only(self):
        with mock_external_api(pbt_only()) as calls:
            pbt.get_all_projects()
        url, params, headers = calls[0]
        self.assertEqual(headers["X-API-Key"], "test-pbt-key")
        self.assertNotIn("test-pbt-key", str(params) + url)

    def test_empty_result_is_an_empty_list(self):
        with mock_external_api(pbt_only([])):
            self.assertEqual(pbt.get_all_projects(), [])

    def test_nullable_fields_stay_none_and_unusable_rows_are_dropped(self):
        rows = [pbt_project("P-1"), {"project_id": None, "project_name": "no id"}, {"project_id": "P-2"}, "junk"]
        with mock_external_api(pbt_only(rows)):
            projects = pbt.get_all_projects()
        self.assertEqual(len(projects), 1)
        self.assertIsNone(projects[0]["end_date"])
        self.assertIsNone(projects[0]["project_manager_name"])
        self.assertEqual(projects[0]["status"], "development")
        self.assertEqual(projects[0]["status_display"], "Development")

    def test_project_id_is_kept_as_a_string(self):
        with mock_external_api(pbt_only([pbt_project(project_id=14)])):
            self.assertEqual(pbt.get_all_projects()[0]["project_id"], "14")

    def test_get_project_requires_an_exact_id_match(self):
        with mock_external_api(pbt_only([pbt_project("P-10")])):
            self.assertIsNone(pbt.get_project("P-1"))
            self.assertEqual(pbt.get_project("P-10")["project_name"], "Test PBT Project")

    def test_invalid_responses(self):
        bad = [
            INVALID_JSON,
            FakeResponse([]),
            FakeResponse({"status": "error", "data": {}}),
            FakeResponse({"status": "success", "data": {"results": "x"}}),
            FakeResponse({"status": "success", "data": None}),
        ]
        for response in bad:
            with self.subTest(body=response.body if response is not INVALID_JSON else "invalid json"):
                with mock_external_api(lambda *a, r=response: r):
                    with self.assertRaises(ExternalAPIError):
                        pbt.get_all_projects()

    def test_http_errors_become_safe_messages(self):
        for status in (400, 401, 403, 404, 500, 502):
            with self.subTest(status=status):
                with mock_external_api(lambda *a, s=status: FakeResponse({"detail": "secret upstream text"}, s)):
                    with self.assertRaises(ExternalAPIError) as ctx:
                        pbt.get_all_projects()
                self.assertEqual(ctx.exception.status, status)
                self.assertNotIn("secret", ctx.exception.message)
                self.assertNotIn("pbt.invalid", ctx.exception.message)
                self.assertNotIn("test-pbt-key", ctx.exception.message)

    def test_rate_limit_with_short_wait_is_retried_once(self):
        answers = iter([FakeResponse({"retry_after_seconds": 1}, 429), pbt_page([pbt_project()])])
        with mock_external_api(lambda *a: next(answers)) as calls:
            self.assertEqual(len(pbt.get_all_projects()), 1)
        self.assertEqual(len(calls), 2)

    def test_rate_limit_with_long_wait_is_reported_not_retried(self):
        with mock_external_api(lambda *a: FakeResponse({"retry_after_seconds": 120}, 429)) as calls:
            with self.assertRaises(ExternalAPIError) as ctx:
                pbt.get_all_projects()
        self.assertEqual((ctx.exception.status, ctx.exception.retry_after), (429, 120))
        self.assertEqual(len(calls), 1)

    def test_rate_limit_after_a_retry_gives_up(self):
        with mock_external_api(lambda *a: FakeResponse({"retry_after_seconds": 0}, 429)) as calls:
            with self.assertRaises(ExternalAPIError):
                pbt.get_all_projects()
        self.assertEqual(len(calls), 2)

    def test_timeout_and_unavailable(self):
        for exc in (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            with self.subTest(exc=exc.__name__):

                def fail(*a, exc=exc):
                    raise exc("http://pbt.invalid/?x=test-pbt-key")

                with mock_external_api(fail):
                    with self.assertRaises(ExternalAPIError) as ctx:
                        pbt.get_all_projects()
                self.assertNotIn("test-pbt-key", ctx.exception.message)
                self.assertNotIn("pbt.invalid", ctx.exception.message)

    def test_missing_configuration(self):
        for config in ({}, {"PBT_API_BASE_URL": "http://pbt.invalid"}, {"PBT_API_KEY": "k"}):
            with self.subTest(config=list(config)):
                with mock_external_api(pbt_only(), config=config) as calls:
                    with self.assertRaises(ExternalAPIError):
                        pbt.get_all_projects()
                self.assertEqual(calls, [])

    def test_pbt_ignores_the_hrms_key(self):
        config = {"HRMS_API_BASE_URL": "http://hrms.invalid", "HRMS_API_KEY": "only-hrms"}
        with mock_external_api(pbt_only(), config=config):
            with self.assertRaises(ExternalAPIError):
                pbt.get_all_projects()


class TestHRMSClient(FrappeTestCase):
    def test_list_is_normalised(self):
        rows = [hrms_employee("E-1", "Asha", "ASHA@Example.com"), hrms_employee("E-2", "Ravi", None, None, None)]
        with mock_external_api(hrms_only(rows)) as calls:
            employees = hrms.get_employees()
        self.assertEqual(calls[0][2]["X-API-Key"], "test-hrms-key")
        self.assertEqual([e["employee_id"] for e in employees], ["E-1", "E-2"])
        self.assertEqual(employees[0]["email"], "asha@example.com")
        self.assertEqual((employees[1]["email"], employees[1]["department"], employees[1]["designation"]), (None, None, None))

    def test_list_accepts_wrapped_bodies(self):
        rows = [hrms_employee()]
        for body in (rows, {"results": rows}, {"data": rows}, {"data": {"results": rows}}):
            with self.subTest(body=type(body).__name__):
                with mock_external_api(hrms_only(body)):
                    self.assertEqual(len(hrms.get_employees()), 1)

    def test_every_page_is_fetched_and_inactive_employees_are_skipped(self):
        pages = {
            1: [hrms_employee("E-1", "One"), {**hrms_employee("E-2", "Gone"), "is_active": False}],
            2: [hrms_employee("E-3", "Three")],
        }

        def handler(url, params, headers):
            page = params["page"]
            return FakeResponse(
                {"status": "success", "data": {"page": page, "total_pages": 2, "results": pages[page]}}
            )

        with mock_external_api(handler) as calls:
            ids = [e["employee_id"] for e in hrms.get_employees()]
        self.assertEqual(ids, ["E-1", "E-3"])
        self.assertEqual([c[1]["page"] for c in calls], [1, 2])

    def test_page_count_is_capped_when_upstream_never_stops(self):
        def handler(url, params, headers):
            return FakeResponse({"data": {"total_pages": 10**6, "results": [hrms_employee()]}})

        with mock_external_api(handler) as calls:
            hrms.get_employees()
        self.assertEqual(len(calls), hrms.MAX_PAGES)

    def test_empty_and_invalid_lists(self):
        with mock_external_api(hrms_only([])):
            self.assertEqual(hrms.get_employees(), [])
        for body in ("text", {"unexpected": 1}, None):
            with self.subTest(body=body):
                with mock_external_api(hrms_only(body)):
                    with self.assertRaises(ExternalAPIError):
                        hrms.get_employees()
        with mock_external_api(lambda *a: INVALID_JSON):
            with self.assertRaises(ExternalAPIError):
                hrms.get_employees()

    def test_rows_without_id_or_name_are_dropped(self):
        with mock_external_api(hrms_only([{"employee_id": "E-1"}, {"employee_name": "x"}, 5, hrms_employee()])):
            self.assertEqual(len(hrms.get_employees()), 1)

    def test_detail(self):
        with mock_external_api(hrms_only(detail=hrms_employee("E-7", "Mia"))) as calls:
            self.assertEqual(hrms.get_employee("E-7")["employee_name"], "Mia")
        self.assertTrue(calls[0][0].endswith("/api/external/employees/E-7/"))
        with mock_external_api(hrms_only(detail={"data": hrms_employee("E-7")})):
            self.assertEqual(hrms.get_employee("E-7")["employee_id"], "E-7")

    def test_detail_for_another_id_is_not_accepted(self):
        with mock_external_api(hrms_only(detail=hrms_employee("E-8"))):
            self.assertIsNone(hrms.get_employee("E-7"))

    def test_detail_id_cannot_alter_the_url_path(self):
        for bad in ("", "../x", "a/b", "a?b=1", "..", " ", "a#b"):
            with self.subTest(employee_id=bad):
                with mock_external_api(hrms_only(detail=hrms_employee())) as calls:
                    with self.assertRaises(ExternalAPIError):
                        hrms.get_employee(bad)
                self.assertEqual(calls, [])

    def test_errors_timeouts_and_missing_key(self):
        for status in (401, 404, 429, 500):
            with self.subTest(status=status):
                with mock_external_api(lambda *a, s=status: FakeResponse({}, s)):
                    with self.assertRaises(ExternalAPIError):
                        hrms.get_employees()

        def timeout(*a):
            raise requests.exceptions.ReadTimeout()

        with mock_external_api(timeout):
            with self.assertRaises(ExternalAPIError):
                hrms.get_employees()
        with mock_external_api(hrms_only(), config={"HRMS_API_BASE_URL": "http://hrms.invalid"}) as calls:
            with self.assertRaises(ExternalAPIError):
                hrms.get_employees()
        self.assertEqual(calls, [])


class TestTaskExternalReferences(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_agent(AGENT)
        make_plain_user(PLAIN)
        make_plain_user(MAPPED)
        make_plain_user(DISABLED)
        frappe.db.set_value("User", DISABLED, "enabled", 0)
        frappe.db.commit()

    def setUp(self):
        frappe.set_user(AGENT)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()

    # --- proxy endpoints ---

    def test_proxy_returns_projects_and_employees_with_user_mapping(self):
        rows = [
            hrms_employee("E-1", "Mapped", MAPPED),
            hrms_employee("E-2", "Unmapped", "nobody@example.com"),
            hrms_employee("E-3", "Disabled", DISABLED),
            hrms_employee("E-4", "No email", None),
        ]
        with mock_external_api(hrms_only(rows)):
            users = {e["employee_id"]: e["user"] for e in get_hrms_employees()}
        self.assertEqual(users, {"E-1": MAPPED, "E-2": None, "E-3": None, "E-4": None})
        with mock_external_api(pbt_only()):
            self.assertEqual(get_pbt_projects(search="x")[0]["project_id"], "P-1")

    def test_proxy_detail_and_not_found(self):
        with mock_external_api(hrms_only(detail=hrms_employee("E-1", email=MAPPED))):
            self.assertEqual(get_hrms_employee("E-1")["user"], MAPPED)
        with mock_external_api(hrms_only(detail=hrms_employee("E-2"))):
            with self.assertRaises(frappe.ValidationError):
                get_hrms_employee("E-1")

    def test_proxy_failures_are_user_safe(self):
        with mock_external_api(lambda *a: FakeResponse({"detail": "internal"}, 500)):
            for fn in (get_pbt_projects, get_hrms_employees):
                with self.assertRaises(frappe.ValidationError) as ctx:
                    fn()
                self.assertNotIn("internal", str(ctx.exception))

    def test_proxies_reject_guests_and_non_agents(self):
        for user in ("Guest", PLAIN):
            frappe.set_user(user)
            for fn, kwargs in (
                (get_pbt_projects, {}),
                (get_hrms_employees, {}),
                (get_hrms_employee, {"employee_id": "E-1"}),
            ):
                with self.subTest(user=user, endpoint=fn.__name__):
                    with mock_external_api(both([pbt_project()], hrms_employee())) as calls:
                        with self.assertRaises(frappe.PermissionError):
                            fn(**kwargs)
                    self.assertEqual(calls, [])

    # --- task creation ---

    def test_task_with_pbt_project_and_mapped_employee_persists(self):
        employee = hrms_employee("E-1", "Mapped Person", MAPPED, "Engineering", "Developer")
        with mock_external_api(both([pbt_project("P-9", "Billing Portal", status="uat")], employee)):
            task = make_task(
                "External task",
                pbt_project_id="P-9",
                hrms_employee_id="E-1",
                # a client must not be able to choose these
                pbt_project_name="Spoofed",
                hrms_employee_name="Spoofed",
                hrms_department="Spoofed",
                assigned_to=AGENT,
            )
        saved = frappe.db.get_value(
            "HD Task",
            task.name,
            [
                "pbt_project_id",
                "pbt_project_name",
                "pbt_project_status",
                "hrms_employee_id",
                "hrms_employee_name",
                "hrms_department",
                "hrms_designation",
                "assigned_to",
                "project",
            ],
            as_dict=True,
        )
        self.assertEqual(
            tuple(saved.values()),
            ("P-9", "Billing Portal", "uat", "E-1", "Mapped Person", "Engineering", "Developer", MAPPED, None),
        )

    def test_unmapped_employee_is_not_assigned_to_the_creator_or_anyone(self):
        with mock_external_api(both([], hrms_employee("E-2", email="nobody@example.com"))):
            task = make_task(hrms_employee_id="E-2")
        self.assertIsNone(task.assigned_to)
        self.assertEqual(task.hrms_employee_name, "Test Employee")

    def test_disabled_users_are_not_mapped(self):
        with mock_external_api(both([], hrms_employee("E-3", email=DISABLED))):
            self.assertIsNone(make_task(hrms_employee_id="E-3").assigned_to)

    def test_employee_id_is_never_used_as_a_user_id(self):
        with mock_external_api(both([], hrms_employee("Administrator", email=None))):
            self.assertIsNone(make_task(hrms_employee_id="Administrator").assigned_to)

    def test_invalid_references_are_rejected_and_nothing_is_saved(self):
        before = frappe.db.count("HD Task")
        with mock_external_api(both([pbt_project("P-1")], None)):
            with self.assertRaises(frappe.ValidationError):
                make_task(pbt_project_id="P-404")
            with self.assertRaises(frappe.ValidationError):
                make_task(hrms_employee_id="E-404")
        self.assertEqual(frappe.db.count("HD Task"), before)

    def test_external_outage_blocks_only_tasks_that_use_external_references(self):
        def down(*a):
            raise requests.exceptions.ConnectionError()

        with mock_external_api(down):
            with self.assertRaises(frappe.ValidationError):
                make_task(pbt_project_id="P-1")
            with self.assertRaises(frappe.ValidationError):
                make_task(hrms_employee_id="E-1")
            task = make_task("Plain task")
        self.assertEqual(task.assigned_to, AGENT)

    def test_pbt_and_local_project_are_exclusive(self):
        with mock_external_api(both([pbt_project("P-1")], None)):
            with self.assertRaises(frappe.ValidationError):
                make_task(project=make_task_project("Both Project"), pbt_project_id="P-1")

    def test_pbt_project_does_not_create_a_local_project(self):
        before = frappe.db.count("HD Task Project")
        with mock_external_api(both([pbt_project("P-1")], None)):
            make_task(pbt_project_id="P-1")
        self.assertEqual(frappe.db.count("HD Task Project"), before)

    def test_milestone_validation_still_applies_to_pbt_projects(self):
        from helpdesk.test_utils import make_task_milestone

        milestone = make_task_milestone(make_task_project("Local For Milestone"))
        with mock_external_api(both([pbt_project("P-1")], None)):
            with self.assertRaises(frappe.ValidationError):
                make_task(pbt_project_id="P-1", milestone=milestone)

    def test_saved_references_are_not_rechecked_on_unrelated_edits(self):
        with mock_external_api(both([pbt_project("P-1")], hrms_employee("E-1", email=MAPPED))):
            task = make_task(pbt_project_id="P-1", hrms_employee_id="E-1")
        with mock_external_api(lambda *a: FakeResponse({}, 500)) as calls:
            task.priority = "High"
            task.save(ignore_permissions=True)
        self.assertEqual(calls, [])

    def test_changing_the_employee_remaps_the_user(self):
        with mock_external_api(both([], hrms_employee("E-1", email=MAPPED))):
            task = make_task(hrms_employee_id="E-1")
        self.assertEqual(task.assigned_to, MAPPED)
        with mock_external_api(both([], hrms_employee("E-2", "Other", "nobody@example.com"))):
            task.hrms_employee_id = "E-2"
            task.save(ignore_permissions=True)
        self.assertEqual((task.hrms_employee_name, task.assigned_to), ("Other", None))

    def test_assigning_a_help_desk_user_directly_clears_the_hrms_employee(self):
        with mock_external_api(both([], hrms_employee("E-1", email=MAPPED))):
            task = make_task(hrms_employee_id="E-1")
        task.assigned_to = AGENT
        task.save(ignore_permissions=True)
        self.assertEqual((task.hrms_employee_id, task.hrms_employee_name, task.assigned_to), (None, None, AGENT))

    def test_freelancer_task_drops_the_hrms_employee(self):
        with mock_external_api(both([], hrms_employee("E-1", email=MAPPED))) as calls:
            task = make_task(
                assignee_type="Freelancer",
                freelancer=make_task_freelancer(),
                hrms_employee_id="E-1",
            )
        self.assertEqual((task.hrms_employee_id, task.hrms_employee_name, task.assigned_to), (None, None, None))
        self.assertEqual(calls, [])

    def test_existing_tasks_without_external_references_are_unchanged(self):
        task = make_task("Legacy", project=make_task_project("Legacy Project"), assigned_to=AGENT)
        with mock_external_api(lambda *a: FakeResponse({}, 500)) as calls:
            task.reload()
            task.status = "In Progress"
            task.save(ignore_permissions=True)
        self.assertEqual(calls, [])
        self.assertEqual((task.project, task.assigned_to, task.pbt_project_id, task.hrms_employee_id), ("Legacy Project", AGENT, None, None))

    def test_new_fields_have_the_approved_definitions(self):
        meta = frappe.get_meta("HD Task")
        for fieldname in (
            "pbt_project_id",
            "pbt_project_name",
            "pbt_project_status",
            "hrms_employee_id",
            "hrms_employee_name",
            "hrms_department",
            "hrms_designation",
        ):
            self.assertEqual(meta.get_field(fieldname).fieldtype, "Data", fieldname)
            self.assertFalse(meta.get_field(fieldname).reqd, fieldname)
        # the legacy fields keep their original links
        self.assertEqual(meta.get_field("project").options, "HD Task Project")
        self.assertEqual(meta.get_field("department").options, "HD Team")
        self.assertEqual(meta.get_field("designation").options, "HD Task Designation")
        self.assertEqual(meta.get_field("assigned_to").options, "User")

    # --- HTTP verbs and status codes ---

    def test_employee_endpoint_accepts_get_and_only_reads_from_hrms(self):
        self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[get_hrms_employees], ["GET"])
        with mock_external_api(hrms_only([hrms_employee("E-1", "Ada", MAPPED)])) as calls:
            rows = get_hrms_employees()
        self.assertEqual([(r["employee_id"], r["employee_name"]) for r in rows], [("E-1", "Ada")])
        # mock_external_api only patches requests.get: any other verb would hit the network
        self.assertEqual(len(calls), 1)
        self.assertNotIn("X-API-Key", str(rows))

    def test_employee_endpoint_with_no_employees_returns_empty_list(self):
        with mock_external_api(hrms_only([])):
            self.assertEqual(get_hrms_employees(), [])

    def test_employee_failures_map_to_gateway_status_codes(self):
        def raises(exc):
            def handler(*args):
                raise exc

            return handler

        cases = (
            (raises(requests.exceptions.ReadTimeout()), 504),
            (raises(requests.exceptions.ConnectionError()), 503),
            (lambda *a: FakeResponse({}, 401), 502),
            (lambda *a: FakeResponse({}, 500), 502),
        )
        for handler, expected in cases:
            with self.subTest(expected=expected), mock_external_api(handler):
                with self.assertRaises(frappe.ValidationError) as ctx:
                    get_hrms_employees()
                self.assertEqual(ctx.exception.http_status_code, expected)
                self.assertNotEqual(ctx.exception.http_status_code, 417)

    def test_create_task_is_post_only_and_returns_201(self):
        self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[create_task], ["POST"])
        frappe.local.response = frappe._dict()
        task = create_task({"subject": "Created over HTTP", "status": "Planned"})
        self.assertEqual(frappe.local.response.get("http_status_code"), 201)
        self.assertEqual(task["subject"], "Created over HTTP")
        self.assertTrue(frappe.db.exists("HD Task", task["name"]))

    def test_create_task_ignores_a_client_supplied_doctype(self):
        task = create_task({"doctype": "User", "subject": "Still a task"})
        self.assertEqual(task["doctype"], "HD Task")

    def test_create_task_validation_failure_is_422_without_201(self):
        frappe.local.response = frappe._dict()
        with self.assertRaises(frappe.ValidationError) as ctx:
            create_task({"subject": "Blocked, no reason", "status": "Blocked"})
        self.assertEqual(ctx.exception.http_status_code, 422)
        self.assertIsNone(frappe.local.response.get("http_status_code"))

    def test_create_task_permission_failure_is_403_without_201(self):
        frappe.set_user(PLAIN)
        frappe.local.response = frappe._dict()
        with self.assertRaises(frappe.PermissionError) as ctx:
            create_task({"subject": "Nope"})
        self.assertEqual(ctx.exception.http_status_code, 403)
        self.assertIsNone(frappe.local.response.get("http_status_code"))

    def test_create_task_with_same_request_id_does_not_duplicate(self):
        request_id = frappe.generate_hash(length=10)
        frappe.local.response = frappe._dict()
        first = create_task({"subject": "Double click"}, request_id=request_id)
        self.assertEqual(frappe.local.response.get("http_status_code"), 201)
        frappe.local.response = frappe._dict()
        second = create_task({"subject": "Double click"}, request_id=request_id)
        self.assertEqual(second["name"], first["name"])
        self.assertIsNone(frappe.local.response.get("http_status_code"))
        self.assertEqual(frappe.db.count("HD Task", {"subject": "Double click"}), 1)
        frappe.cache().delete_value(f"hd_task_create:{AGENT}:{request_id}")
