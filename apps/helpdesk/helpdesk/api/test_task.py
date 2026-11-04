from unittest.mock import patch

import frappe
from frappe.desk.doctype.notification_log.notification_log import NotificationLog
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from helpdesk.api import task as task_api
from helpdesk.api.doc import get_list_data, get_quick_filters
from helpdesk.api.task import (
    add_comment,
    get_mentionable_users,
    bulk_assign,
    bulk_update_status,
    get_task,
    get_task_counts,
    get_task_form_options,
    get_tasks,
    update_checklist,
    update_status,
)
from helpdesk.helpdesk.doctype.hd_task.hd_task import notify_overdue_tasks
from helpdesk.test_utils import (
    create_agent,
    create_agent_manager,
    make_task,
    make_plain_user,
    make_task_freelancer,
    make_task_milestone,
    make_task_project,
    make_ticket,
)

ASSIGNEE = "task-assignee@example.com"
REVIEWER = "task-reviewer@example.com"
OTHER = "task-other@example.com"
MANAGER = "task-manager@example.com"
PLAIN = "task-plain@example.com"


def task_api_endpoints():
    return [
        name
        for name, fn in vars(task_api).items()
        if callable(fn) and getattr(fn, "__module__", None) == task_api.__name__
        and fn in frappe.whitelisted
    ]


class TestHDTask(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for email in (ASSIGNEE, REVIEWER, OTHER):
            create_agent(email)
        create_agent_manager(MANAGER)
        make_plain_user(PLAIN)

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.delete("HD Task")
        frappe.db.delete("Notification Log", {"document_type": "HD Task"})

    def tearDown(self):
        frappe.set_user("Administrator")

    def task_in_review(self, **kwargs):
        task = make_task(assigned_to=ASSIGNEE, reviewer=REVIEWER, **kwargs)
        for status in ("In Progress", "In Review"):
            task.status = status
            task.save()
        return task

    def notification_subjects(self, user):
        return frappe.get_all(
            "Notification Log",
            filters={"for_user": user, "document_type": "HD Task"},
            pluck="subject",
        )

    # --- defaults / validation ---

    def test_defaults(self):
        frappe.set_user(ASSIGNEE)
        task = make_task()
        self.assertEqual(task.status, "Planned")
        self.assertEqual(task.priority, "Medium")
        self.assertEqual(task.assigned_to, ASSIGNEE)
        self.assertEqual(task.progress, 0)
        self.assertTrue(task.name.startswith("TASK-"))

    def test_form_fields_persist_in_database(self):
        frappe.set_user(ASSIGNEE)
        project = make_task_project("Persist Project")
        milestone = make_task_milestone(project)
        task = make_task(
            "Persist Test Task",
            status="In Progress",
            project=project,
            milestone=milestone,
            assignee_type="Employee",
            assigned_to=ASSIGNEE,
            start_date="2026-11-01",
            due_date="2026-11-05",
        )
        frappe.db.commit()
        saved = frappe.db.get_value(
            "HD Task",
            task.name,
            [
                "subject",
                "status",
                "project",
                "milestone",
                "assignee_type",
                "assigned_to",
                "start_date",
                "due_date",
            ],
            as_dict=True,
        )
        self.assertEqual(saved.subject, "Persist Test Task")
        self.assertEqual(saved.status, "In Progress")
        self.assertEqual(saved.project, project)
        self.assertEqual(saved.milestone, milestone)
        self.assertEqual(saved.assignee_type, "Employee")
        self.assertEqual(saved.assigned_to, ASSIGNEE)
        self.assertEqual(str(saved.start_date), "2026-11-01")
        self.assertEqual(str(saved.due_date), "2026-11-05")

    def test_milestone_must_belong_to_project(self):
        project = make_task_project("Milestone Project")
        other = make_task_project("Other Milestone Project")
        milestone = make_task_milestone(project)
        task = make_task(project=project, milestone=milestone)
        self.assertEqual(task.milestone, milestone)
        with self.assertRaises(frappe.ValidationError):
            make_task(project=other, milestone=milestone)

    def test_freelancer_task_requires_freelancer_and_has_no_assignee(self):
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.ValidationError):
            make_task(assignee_type="Freelancer")
        task = make_task(
            assignee_type="Freelancer",
            freelancer=make_task_freelancer(),
            department=None,
        )
        self.assertIsNone(task.assigned_to)

    def test_employee_task_drops_freelancer(self):
        frappe.set_user(ASSIGNEE)
        task = make_task(freelancer=make_task_freelancer())
        self.assertEqual(task.assignee_type, "Employee")
        self.assertIsNone(task.freelancer)
        self.assertEqual(task.assigned_to, ASSIGNEE)

    def test_form_options_follow_project(self):
        frappe.set_user(ASSIGNEE)
        project = make_task_project("Options Project")
        milestone = make_task_milestone(project)
        options = get_task_form_options(project=project)
        self.assertEqual([m.name for m in options["milestones"]], [milestone])
        self.assertEqual(get_task_form_options()["milestones"], [])

    def test_due_date_before_start_date_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            make_task(start_date=today(), due_date=add_days(today(), -1))

    def test_new_task_can_start_in_any_status(self):
        for status in ("In Progress", "In Review", "Cancelled"):
            self.assertEqual(make_task(status=status).status, status)

    def test_new_blocked_task_requires_reason(self):
        with self.assertRaises(frappe.ValidationError):
            make_task(status="Blocked")
        task = make_task(status="Blocked", blocked_reason="Waiting on vendor")
        self.assertEqual(task.status, "Blocked")

    def test_new_completed_task_gets_completion_fields(self):
        task = make_task(status="Completed")
        self.assertEqual(task.progress, 100)
        self.assertTrue(task.completed_on)
        self.assertEqual(task.completed_by, frappe.session.user)

    def test_blocked_requires_reason(self):
        task = make_task()
        task.status = "In Progress"
        task.save()
        for reason in (None, "  "):
            task.reload()
            task.status = "Blocked"
            task.blocked_reason = reason
            with self.assertRaises(frappe.ValidationError):
                task.save()
        task.reload()
        task.status = "Blocked"
        task.blocked_reason = "Waiting on vendor"
        task.save()
        task.status = "In Progress"
        task.save()
        self.assertFalse(task.blocked_reason)

    def test_disabled_assignee_rejected(self):
        create_agent("task-disabled@example.com")
        frappe.db.set_value("User", "task-disabled@example.com", "enabled", 0)
        with self.assertRaises(frappe.ValidationError):
            make_task(assigned_to="task-disabled@example.com")

    # --- status transitions ---

    def test_allowed_transitions(self):
        task = make_task(assigned_to=ASSIGNEE, reviewer=REVIEWER)
        task.status = "In Progress"
        task.save()
        task.status = "Blocked"
        task.blocked_reason = "x"
        task.save()
        task.status = "In Progress"
        task.save()
        task.status = "In Review"
        task.save()
        frappe.set_user(REVIEWER)
        task.status = "Completed"
        task.save()
        self.assertEqual(task.status, "Completed")

    def test_rejected_transitions(self):
        rejected = [
            ("Planned", "In Review"),
            ("Planned", "Completed"),
            ("Planned", "Blocked"),
            ("In Progress", "Completed"),
            ("In Progress", "Planned"),
            ("Blocked", "In Review"),
            ("Blocked", "Completed"),
            ("In Review", "Planned"),
            ("In Review", "Blocked"),
            ("Completed", "Planned"),
            ("Completed", "In Progress"),
            ("Cancelled", "Planned"),
        ]
        for old, new in rejected:
            task = make_task(assigned_to=ASSIGNEE, reviewer=REVIEWER)
            frappe.db.set_value("HD Task", task.name, "status", old)
            task = frappe.get_doc("HD Task", task.name)
            task.status = new
            task.blocked_reason = "reason"
            with self.assertRaises(frappe.ValidationError, msg=f"{old}->{new}"):
                task.save()

    def test_any_status_to_cancelled(self):
        for old in ("Planned", "In Progress", "In Review", "Completed", "Blocked"):
            task = make_task()
            frappe.db.set_value("HD Task", task.name, "status", old)
            task = frappe.get_doc("HD Task", task.name)
            task.status = "Cancelled"
            task.save()
            self.assertEqual(task.status, "Cancelled")

    # --- review permissions ---

    def test_reviewer_can_approve_and_completion_fields_set(self):
        task = self.task_in_review()
        frappe.set_user(REVIEWER)
        result = update_status(task.name, "Completed")
        self.assertEqual(result.status, "Completed")
        self.assertEqual(result.progress, 100)
        self.assertEqual(result.completed_by, REVIEWER)
        self.assertTrue(result.completed_on)

    def test_agent_manager_can_approve(self):
        task = self.task_in_review()
        frappe.set_user(MANAGER)
        self.assertEqual(update_status(task.name, "Completed").status, "Completed")

    def test_unrelated_agent_cannot_approve(self):
        task = self.task_in_review(owner=OTHER)
        frappe.set_user(OTHER)
        with self.assertRaises(frappe.PermissionError):
            update_status(task.name, "Completed")

    def test_assignee_cannot_approve_own_task(self):
        task = self.task_in_review()
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.PermissionError):
            update_status(task.name, "Completed")

    def test_manager_cannot_approve_task_assigned_to_them(self):
        task = make_task(assigned_to=MANAGER, reviewer=REVIEWER)
        for status in ("In Progress", "In Review"):
            task.status = status
            task.save()
        frappe.set_user(MANAGER)
        with self.assertRaises(frappe.PermissionError):
            update_status(task.name, "Completed")

    def test_client_cannot_set_completion_fields(self):
        task = make_task()
        task.completed_by = OTHER
        task.completed_on = "2000-01-01 00:00:00"
        task.save()
        task.reload()
        self.assertFalse(task.completed_by)
        self.assertFalse(task.completed_on)

    def test_return_from_review_requires_comment(self):
        task = self.task_in_review()
        frappe.set_user(REVIEWER)
        with self.assertRaises(frappe.ValidationError):
            update_status(task.name, "In Progress")
        with self.assertRaises(frappe.ValidationError):
            update_status(task.name, "In Progress", "   ")

        result = update_status(task.name, "In Progress", "Needs more detail")
        self.assertEqual(result.status, "In Progress")
        self.assertIn("Needs more detail", [c.content for c in result.comments])

    def test_only_reviewer_can_return_from_review(self):
        task = self.task_in_review()
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.PermissionError):
            update_status(task.name, "In Progress", "pulling back")

    # --- checklist / progress ---

    def test_progress_from_checklist(self):
        task = make_task(
            checklist=[{"item": f"i{n}", "done": 1 if n == 0 else 0} for n in range(8)]
        )
        self.assertEqual(task.progress, 13)  # 12.5% rounds half-up

    def test_progress_without_checklist_is_zero(self):
        self.assertEqual(make_task().progress, 0)

    def test_update_checklist_recalculates_progress(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        result = update_checklist(
            task.name,
            [
                {"item": "a", "done": 1},
                {"item": "b", "done": 0},
                {"item": " ", "done": 1},
            ],
        )
        self.assertEqual(len(result.checklist), 2)
        self.assertEqual(result.progress, 50)

    def test_completed_task_stays_at_100(self):
        task = self.task_in_review(checklist=[{"item": "a", "done": 0}])
        frappe.set_user(REVIEWER)
        update_status(task.name, "Completed")
        frappe.set_user(ASSIGNEE)
        result = update_checklist(task.name, [{"item": "a", "done": 0}])
        self.assertEqual(result.progress, 100)

    # --- record level permissions ---

    def test_agent_only_sees_own_tasks(self):
        mine = make_task("mine", assigned_to=ASSIGNEE)
        review = make_task("review", assigned_to=OTHER, reviewer=ASSIGNEE)
        hidden = make_task("hidden", assigned_to=OTHER)
        frappe.set_user(ASSIGNEE)
        names = [t.name for t in get_tasks(view="all")["data"]]
        self.assertIn(mine.name, names)
        self.assertIn(review.name, names)
        self.assertNotIn(hidden.name, names)
        with self.assertRaises(frappe.PermissionError):
            get_task(hidden.name)

    def test_manager_sees_everything(self):
        make_task("a", assigned_to=ASSIGNEE)
        make_task("b", assigned_to=OTHER)
        frappe.set_user(MANAGER)
        self.assertEqual(get_tasks(view="all")["total"], 2)

    def test_agent_cannot_delete_but_manager_can(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("HD Task", task.name)
        frappe.set_user(MANAGER)
        frappe.delete_doc("HD Task", task.name)
        self.assertFalse(frappe.db.exists("HD Task", task.name))

    def test_agent_can_create_and_edit(self):
        frappe.set_user(ASSIGNEE)
        task = frappe.get_doc({"doctype": "HD Task", "subject": "Created"}).insert()
        task.priority = "High"
        task.save()
        self.assertEqual(task.priority, "High")

    def test_non_agent_is_rejected(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            get_tasks()
        with self.assertRaises(frappe.PermissionError):
            get_task_counts()

    def test_every_endpoint_rejects_guest_and_users_without_agent_role(self):
        calls = {
            task_api.get_tasks: {},
            task_api.get_task_counts: {},
            task_api.get_pbt_projects: {},
            task_api.get_hrms_employees: {},
            task_api.get_hrms_employee: {"employee_id": "E-1"},
            task_api.get_task: {"name": "TASK-0001"},
            task_api.create_task: {"doc": {"subject": "x"}},
            task_api.update_status: {"name": "TASK-0001", "status": "In Progress"},
            task_api.update_checklist: {"name": "TASK-0001", "checklist": []},
            task_api.add_comment: {"name": "TASK-0001", "content": "hi"},
            task_api.get_mentionable_users: {"name": "TASK-0001"},
            task_api.bulk_assign: {"names": [], "assigned_to": ASSIGNEE},
            task_api.bulk_update_status: {"names": [], "status": "In Progress"},
        }
        task = make_task(assigned_to=ASSIGNEE)
        for user in ("Guest", PLAIN):
            frappe.set_user(user)
            for fn, kwargs in calls.items():
                kwargs = {k: (task.name if v == "TASK-0001" else v) for k, v in kwargs.items()}
                with self.subTest(user=user, endpoint=fn.__name__):
                    with self.assertRaises(frappe.PermissionError):
                        fn(**kwargs)
        self.assertEqual(frappe.db.get_value("HD Task", task.name, "status"), "Planned")

    def test_guest_cannot_reach_endpoints_over_http(self):
        endpoints = task_api_endpoints()
        self.assertEqual(len(endpoints), 14)
        frappe.set_user("Guest")
        for name in endpoints:
            with self.subTest(endpoint=name):
                with self.assertRaises(frappe.PermissionError):
                    frappe.is_whitelisted(getattr(task_api, name))

    def test_state_changing_endpoints_are_post_only(self):
        for name in (
            "update_status",
            "update_checklist",
            "add_comment",
            "bulk_assign",
            "bulk_update_status",
        ):
            with self.subTest(endpoint=name):
                allowed = frappe.allowed_http_methods_for_whitelisted_func[
                    getattr(task_api, name)
                ]
                self.assertEqual(list(allowed), ["POST"])

    def test_agent_cannot_read_or_change_a_task_they_have_no_part_in(self):
        task = make_task(assigned_to=OTHER)
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.PermissionError):
            get_task(task.name)
        with self.assertRaises(frappe.PermissionError):
            update_status(task.name, "In Progress")
        with self.assertRaises(frappe.PermissionError):
            update_checklist(task.name, [{"item": "x", "done": 0}])
        self.assertEqual(frappe.db.get_value("HD Task", task.name, "status"), "Planned")

    def test_agent_cannot_assign_a_task_to_a_disabled_user(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.db.set_value("User", OTHER, "enabled", 0)
        try:
            frappe.set_user(ASSIGNEE)
            result = bulk_assign([task.name], OTHER)
            self.assertEqual(result["updated"], [])
            self.assertEqual(len(result["failed"]), 1)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("User", OTHER, "enabled", 1)

    # --- generic Frappe document APIs must not bypass the rules ---

    def test_generic_apis_respect_record_permissions(self):
        hidden = make_task("hidden", assigned_to=OTHER)
        mine = make_task("mine", assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        names = [t.name for t in frappe.client.get_list("HD Task", fields=["name"])]
        self.assertIn(mine.name, names)
        self.assertNotIn(hidden.name, names)
        with self.assertRaises(frappe.PermissionError):
            frappe.client.get("HD Task", hidden.name)
        with self.assertRaises(frappe.PermissionError):
            frappe.client.set_value("HD Task", hidden.name, "priority", "Urgent")
        with self.assertRaises(frappe.PermissionError):
            frappe.client.delete("HD Task", mine.name)

    def test_set_value_cannot_bypass_the_workflow_or_protected_fields(self):
        task = make_task(assigned_to=ASSIGNEE, reviewer=REVIEWER)
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.ValidationError):
            frappe.client.set_value("HD Task", task.name, "status", "Completed")
        frappe.client.set_value(
            "HD Task", task.name, {"completed_by": ASSIGNEE, "progress": 99}
        )
        task.reload()
        self.assertFalse(task.completed_by)
        self.assertEqual(task.progress, 0)

    def test_insert_cannot_preset_completion_fields(self):
        frappe.set_user(ASSIGNEE)
        task = frappe.client.insert(
            {
                "doctype": "HD Task",
                "subject": "y",
                "progress": 100,
                "completed_by": OTHER,
                "completed_on": "2000-01-01 00:00:00",
            }
        )
        self.assertEqual(task.progress, 0)
        self.assertFalse(task.completed_by)
        self.assertEqual(task.owner, ASSIGNEE)

    # --- list / counts / filters / pagination ---

    def test_views_and_counts(self):
        make_task("mine", assigned_to=ASSIGNEE, due_date=add_days(today(), -2))
        make_task("done late", assigned_to=ASSIGNEE, due_date=add_days(today(), -2))
        frappe.db.set_value("HD Task", {"subject": "done late"}, "status", "Completed")
        make_task("unassigned")
        frappe.db.set_value("HD Task", {"subject": "unassigned"}, "assigned_to", None)
        make_task("soon", assigned_to=OTHER, due_date=today())
        frappe.set_user(MANAGER)

        counts = get_task_counts()
        self.assertEqual(counts["all"], 4)
        self.assertEqual(counts["overdue"], 1)  # closed tasks are never overdue
        self.assertEqual(counts["unassigned"], 1)
        self.assertEqual(counts["open"], 3)
        self.assertEqual(counts["my"], 0)
        self.assertEqual(counts["due_this_week"], 1)
        self.assertEqual(
            [t.subject for t in get_tasks(view="overdue")["data"]], ["mine"]
        )

    def test_filters_combine_with_view(self):
        project = make_task_project()
        make_task("alpha one", assigned_to=ASSIGNEE, priority="High", project=project)
        make_task("alpha two", assigned_to=ASSIGNEE, priority="Low")
        make_task("beta", assigned_to=ASSIGNEE, priority="High")
        frappe.set_user(ASSIGNEE)
        result = get_tasks(
            filters={"search": "alpha", "priority": "High", "project": project},
            view="my",
        )
        self.assertEqual([t.subject for t in result["data"]], ["alpha one"])
        by_id = get_tasks(filters={"search": result["data"][0].name})
        self.assertEqual(by_id["total"], 1)

    def test_pagination(self):
        for n in range(5):
            make_task(f"t{n}", assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        first = get_tasks(page=1, page_size=2)
        last = get_tasks(page=3, page_size=2)
        self.assertEqual((first["total"], len(first["data"])), (5, 2))
        self.assertEqual(len(last["data"]), 1)

    def test_list_returns_assignee_details(self):
        make_task(assigned_to=ASSIGNEE, reviewer=REVIEWER)
        frappe.set_user(ASSIGNEE)
        row = get_tasks()["data"][0]
        self.assertEqual(row.assignee.name, ASSIGNEE)
        self.assertEqual(row.reviewer, REVIEWER)

    def test_unknown_view_rejected(self):
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.ValidationError):
            get_tasks(view="nope")

    def test_page_size_is_capped_and_page_is_clamped(self):
        for n in range(3):
            make_task(f"t{n}", assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        self.assertEqual(get_tasks(page_size=100000)["page_size"], task_api.MAX_PAGE_SIZE)
        self.assertEqual(get_tasks(page_size=0)["page_size"], 1)
        self.assertEqual(get_tasks(page_size=-5)["page_size"], 1)
        clamped = get_tasks(page=0, page_size=2)
        self.assertEqual(clamped["page"], 1)
        self.assertEqual(len(clamped["data"]), 2)

    def test_page_past_the_end_is_empty_but_keeps_the_total(self):
        for n in range(3):
            make_task(f"t{n}", assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        result = get_tasks(page=9, page_size=2)
        self.assertEqual(result["data"], [])
        self.assertEqual(result["total"], 3)

    def test_pages_do_not_overlap_and_cover_every_task(self):
        expected = {make_task(f"t{n}", assigned_to=ASSIGNEE).name for n in range(5)}
        frappe.set_user(ASSIGNEE)
        seen = []
        for page in (1, 2, 3):
            seen += [t.name for t in get_tasks(page=page, page_size=2)["data"]]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), expected)

    def test_pagination_accepts_string_arguments_from_http(self):
        for n in range(3):
            make_task(f"t{n}", assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        result = get_tasks(page="2", page_size="2", filters='{"priority": "Medium"}')
        self.assertEqual((result["page"], result["page_size"]), (2, 2))
        self.assertEqual(len(result["data"]), 1)

    def test_totals_only_count_tasks_the_user_may_see(self):
        make_task("mine", assigned_to=ASSIGNEE)
        make_task("theirs one", assigned_to=OTHER)
        make_task("theirs two", assigned_to=OTHER)
        frappe.set_user(ASSIGNEE)
        self.assertEqual(get_tasks(view="all")["total"], 1)
        self.assertEqual(get_task_counts()["all"], 1)
        frappe.set_user(MANAGER)
        self.assertEqual(get_tasks(view="all")["total"], 3)

    # --- generic list view (get_list_data / quick filters) ---

    def test_generic_list_loads_the_default_task_columns(self):
        make_task("mine", assigned_to=ASSIGNEE)
        make_task("theirs", assigned_to=OTHER)
        frappe.set_user(ASSIGNEE)
        result = get_list_data("HD Task", is_default=True)
        self.assertEqual(
            [c["key"] for c in result["columns"]],
            [
                "name",
                "subject",
                "status",
                "priority",
                "assigned_to",
                "due_date",
                "project",
                "pbt_project_name",
                "hrms_employee_name",
            ],
        )
        self.assertEqual([r["subject"] for r in result["data"]], ["mine"])

    def test_quick_filters_come_from_the_doctype_standard_filters(self):
        frappe.set_user(ASSIGNEE)
        names = [f["name"] for f in get_quick_filters("HD Task")]
        self.assertEqual(
            names, ["name", "subject", "status", "priority", "assigned_to", "project"]
        )

    # --- bulk / comments ---

    def test_bulk_assign_reports_failures_without_blocking_others(self):
        allowed = make_task(assigned_to=ASSIGNEE)
        denied = make_task(assigned_to=OTHER)
        frappe.set_user(ASSIGNEE)
        result = bulk_assign([allowed.name, denied.name], REVIEWER)
        self.assertEqual(result["updated"], [allowed.name])
        self.assertEqual([f["name"] for f in result["failed"]], [denied.name])
        self.assertEqual(
            frappe.db.get_value("HD Task", allowed.name, "assigned_to"), REVIEWER
        )

    def test_bulk_status(self):
        first = make_task(assigned_to=ASSIGNEE)
        second = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        result = bulk_update_status([first.name, second.name], "In Progress")
        self.assertEqual(len(result["updated"]), 2)
        result = bulk_update_status([first.name], "Completed")
        self.assertEqual(len(result["failed"]), 1)

    def test_add_comment_is_sanitised(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        result = add_comment(task.name, "<p>hello</p><script>x()</script>")
        self.assertEqual(len(result.comments), 1)
        self.assertNotIn("<script", result.comments[0].content)
        with self.assertRaises(frappe.ValidationError):
            add_comment(task.name, " ")

    # --- mentions ---

    @staticmethod
    def mention(user, label="X", extra=""):
        return (
            f'<p>hi <span class="mention" data-type="mention" data-id="{user}" '
            f'data-label="{label}"{extra}>@{label}</span></p>'
        )

    def test_mention_of_user_with_access_is_kept_and_notified(self):
        task = make_task(assigned_to=ASSIGNEE, reviewer=REVIEWER)
        frappe.set_user(ASSIGNEE)
        result = add_comment(task.name, self.mention(REVIEWER, "Reviewer"))
        self.assertIn(f'data-id="{REVIEWER}"', result.comments[0].content)
        mentions = frappe.get_all(
            "Notification Log",
            filters={"for_user": REVIEWER, "type": "Mention", "document_name": task.name},
        )
        self.assertEqual(len(mentions), 1)

    def test_mention_of_user_without_access_becomes_plain_text(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        result = add_comment(task.name, self.mention(OTHER, "Other"))
        content = result.comments[0].content
        self.assertNotIn("mention", content)
        self.assertIn("@Other", content)
        self.assertFalse(
            frappe.db.exists(
                "Notification Log", {"for_user": OTHER, "document_name": task.name}
            )
        )

    def test_group_and_unknown_mentions_are_stripped(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        group = add_comment(
            task.name, self.mention(REVIEWER, "G", ' data-is-group="true"')
        )
        unknown = add_comment(task.name, self.mention("nobody@example.com", "N"))
        for comment in unknown.comments:
            self.assertNotIn("mention", comment.content)
        self.assertNotIn("mention", group.comments[0].content)

    def test_mentionable_users_are_limited_to_those_with_access(self):
        task = make_task(assigned_to=ASSIGNEE, reviewer=REVIEWER)
        frappe.set_user(ASSIGNEE)
        ids = {u["id"] for u in get_mentionable_users(task.name)}
        self.assertTrue({ASSIGNEE, REVIEWER, MANAGER} <= ids)
        self.assertNotIn(OTHER, ids)

    def test_cannot_comment_or_list_mentions_on_inaccessible_task(self):
        task = make_task(assigned_to=OTHER)
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.PermissionError):
            add_comment(task.name, "<p>hello</p>")
        with self.assertRaises(frappe.PermissionError):
            get_mentionable_users(task.name)

    def test_comment_is_attached_only_to_the_task(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        add_comment(task.name, "<p>hello</p>")
        comment = frappe.get_all(
            "Comment",
            filters={"reference_name": task.name, "comment_type": "Comment"},
            fields=["reference_doctype"],
        )
        self.assertEqual([c.reference_doctype for c in comment], ["HD Task"])

    def test_reads_are_get_only_and_writes_are_post_only(self):
        """Reads must be cacheable GETs and a GET must never reach a function that changes a Task."""
        reads = (
            task_api.get_tasks,
            task_api.get_task,
            task_api.get_task_counts,
            task_api.get_task_form_options,
            task_api.get_mentionable_users,
            task_api.get_pbt_projects,
            task_api.get_hrms_employees,
            task_api.get_hrms_employee,
        )
        writes = (
            task_api.create_task,
            task_api.update_status,
            task_api.update_checklist,
            task_api.add_comment,
            task_api.bulk_assign,
            task_api.bulk_update_status,
        )
        allowed = frappe.allowed_http_methods_for_whitelisted_func
        for fn in reads:
            self.assertEqual(allowed[fn], ["GET"], fn.__name__)
        for fn in writes:
            self.assertEqual(allowed[fn], ["POST"], fn.__name__)
        # every whitelisted Task endpoint is classified above
        self.assertEqual(len(task_api_endpoints()), len(reads) + len(writes))

    # --- notifications ---

    def test_assignment_notifications(self):
        frappe.set_user(MANAGER)
        task = make_task(assigned_to=ASSIGNEE)
        self.assertEqual(len(self.notification_subjects(ASSIGNEE)), 1)
        task.assigned_to = OTHER
        task.save()
        self.assertEqual(len(self.notification_subjects(OTHER)), 1)

    def test_return_from_review_notifies_assignee(self):
        task = self.task_in_review()
        frappe.set_user(REVIEWER)
        update_status(task.name, "In Progress", "redo")
        self.assertTrue(
            any("returned" in s for s in self.notification_subjects(ASSIGNEE))
        )

    def test_overdue_notification_sent_once(self):
        make_task(assigned_to=ASSIGNEE, due_date=add_days(today(), -1))
        notify_overdue_tasks()
        notify_overdue_tasks()
        overdue = [s for s in self.notification_subjects(ASSIGNEE) if "overdue" in s]
        self.assertEqual(len(overdue), 1)

    def test_notification_failure_does_not_block_task(self):
        frappe.set_user(MANAGER)
        with patch.object(NotificationLog, "after_insert", side_effect=RuntimeError):
            task = make_task(assigned_to=ASSIGNEE)
        self.assertTrue(frappe.db.exists("HD Task", task.name))

    # --- ticket independence ---

    def test_task_lifecycle_never_touches_tickets(self):
        ticket = make_ticket()
        before = frappe.db.get_value("HD Ticket", ticket.name, "modified")
        count = frappe.db.count("HD Ticket")

        task = self.task_in_review()
        frappe.set_user(REVIEWER)
        update_status(task.name, "Completed")
        frappe.set_user("Administrator")
        frappe.delete_doc("HD Task", task.name)

        self.assertEqual(frappe.db.count("HD Ticket"), count)
        self.assertEqual(frappe.db.get_value("HD Ticket", ticket.name, "modified"), before)

    def test_creating_ticket_creates_no_tasks(self):
        make_ticket()
        self.assertEqual(frappe.db.count("HD Task"), 0)

    def test_schema_has_no_ticket_or_customer_fields(self):
        fields = {f.fieldname for f in frappe.get_meta("HD Task").fields}
        self.assertFalse({"ticket", "customer", "reference_ticket"} & fields)
