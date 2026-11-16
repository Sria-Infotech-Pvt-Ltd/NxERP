from unittest.mock import patch

import frappe
from frappe.desk.doctype.notification_log.notification_log import NotificationLog
from frappe.email.doctype.email_account.email_account import EmailAccount
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from helpdesk.api import task as task_api
from helpdesk.api.doc import get_list_data, get_quick_filters
from helpdesk.api.task import (
    add_comment,
    assign_task,
    create_task,
    get_mentionable_users,
    bulk_assign,
    bulk_update_status,
    get_task,
    get_task_counts,
    get_task_form_options,
    get_tasks,
    reply_via_email,
    update_checklist,
    update_status,
    update_task_fields,
)
from helpdesk.helpdesk.doctype.hd_task.hd_task import STATUSES, notify_overdue_tasks
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
OUTGOING = frappe._dict(name="Task Test Outgoing", email_id="task-outgoing@example.com")


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
            task_api.reply_via_email: {
                "name": "TASK-0001",
                "message": "hi",
                "to": "someone@example.com",
            },
            task_api.get_mentionable_users: {"name": "TASK-0001"},
            task_api.bulk_assign: {"names": [], "assigned_to": ASSIGNEE},
            task_api.assign_task: {
                "name": "TASK-0001",
                "assignee_type": "Employee",
                "hrms_employee_id": "E-1",
            },
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
        self.assertEqual(len(endpoints), 17)
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
            "reply_via_email",
            "bulk_assign",
            "assign_task",
            "update_task_fields",
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
        self.assertEqual(names, ["name", "subject", "assigned_to"])

    def test_assigned_to_quick_filter_offers_only_enabled_agents(self):
        disabled = "task-disabled-agent@example.com"
        create_agent(disabled)
        frappe.db.set_value("User", disabled, "enabled", 0)
        try:
            frappe.set_user(ASSIGNEE)
            by_name = {f["name"]: f for f in get_quick_filters("HD Task")}
            assigned = by_name["assigned_to"]
            self.assertEqual(assigned["type"], "Select")
            values = [o["value"] for o in assigned["options"]]
            self.assertEqual(values[0], "")  # the blank "no filter" choice
            for agent in (ASSIGNEE, REVIEWER, OTHER):
                self.assertIn(agent, values)
            self.assertNotIn(PLAIN, values)
            self.assertNotIn(disabled, values)
            self.assertNotIn("Guest", values)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("User", disabled, "enabled", 1)

    def test_assigned_to_quick_filter_hands_no_users_to_non_agents(self):
        frappe.set_user(PLAIN)
        assigned = {f["name"]: f for f in get_quick_filters("HD Task")}["assigned_to"]
        self.assertEqual(assigned["options"], [{"label": "", "value": ""}])

    # --- freelancer shown in Assigned To ---

    def test_list_rows_carry_the_freelancer_name(self):
        frappe.set_user(ASSIGNEE)
        freelancer = make_task_freelancer("List Freelancer")
        make_task("by freelancer", assignee_type="Freelancer", freelancer=freelancer)
        make_task("by employee", assigned_to=ASSIGNEE)
        rows = {r["subject"]: r for r in get_list_data("HD Task", is_default=True)["data"]}
        self.assertEqual(rows["by freelancer"]["assignee_type"], "Freelancer")
        self.assertEqual(rows["by freelancer"]["freelancer_name"], "List Freelancer")
        self.assertFalse(rows["by freelancer"].get("assigned_to"))
        self.assertEqual(rows["by employee"]["assignee_type"], "Employee")
        self.assertFalse(rows["by employee"].get("freelancer_name"))

    def test_get_tasks_returns_the_freelancer_name(self):
        frappe.set_user(ASSIGNEE)
        freelancer = make_task_freelancer("Api Freelancer")
        make_task("by freelancer", assignee_type="Freelancer", freelancer=freelancer)
        rows = get_tasks(view="all")["data"]
        self.assertEqual([r["freelancer_name"] for r in rows], ["Api Freelancer"])

    # --- quick filters respect permissions ---

    def filtered_subjects(self, *conditions):
        return sorted(
            r["subject"]
            for r in get_list_data("HD Task", filters=list(conditions), is_default=True)["data"]
        )

    def test_quick_filters_never_reach_another_agents_task(self):
        mine = make_task("Alpha report", assigned_to=ASSIGNEE)
        theirs = make_task("Alpha secret", assigned_to=OTHER)

        frappe.set_user(ASSIGNEE)
        # subject, ID and assignee filters narrow what the agent may see; they never widen it
        self.assertEqual(
            self.filtered_subjects(["subject", "LIKE", "%Alpha%"]), ["Alpha report"]
        )
        self.assertEqual(self.filtered_subjects(["name", "LIKE", f"%{mine.name}%"]), ["Alpha report"])
        self.assertEqual(self.filtered_subjects(["name", "LIKE", f"%{theirs.name}%"]), [])
        self.assertEqual(self.filtered_subjects(["assigned_to", "=", OTHER]), [])
        self.assertEqual(self.filtered_subjects(["assigned_to", "=", ASSIGNEE]), ["Alpha report"])

        frappe.set_user(MANAGER)
        self.assertEqual(self.filtered_subjects(["assigned_to", "=", OTHER]), ["Alpha secret"])
        self.assertEqual(
            self.filtered_subjects(["subject", "LIKE", "%Alpha%"]),
            ["Alpha report", "Alpha secret"],
        )

    # --- sidebar: allowed_statuses and field edits ---

    def test_get_task_returns_the_site_today_and_allowed_statuses(self):
        task = make_task("sidebar", assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        result = get_task(task.name)
        self.assertEqual(result["today"], today())
        self.assertEqual(result["allowed_statuses"], ["In Progress", "Cancelled"])

    def test_allowed_statuses_differ_for_assignee_reviewer_and_manager(self):
        task = self.task_in_review()  # assignee ASSIGNEE, reviewer REVIEWER, status In Review

        def allowed(user):
            frappe.set_user(user)
            return get_task(task.name)["allowed_statuses"]

        # the assignee cannot approve or return their own task; only cancel it
        self.assertEqual(allowed(ASSIGNEE), ["Cancelled"])
        self.assertEqual(allowed(REVIEWER), ["In Progress", "Completed", "Cancelled"])
        self.assertEqual(allowed(MANAGER), ["In Progress", "Completed", "Cancelled"])

    def test_a_manager_who_is_the_assignee_cannot_approve_their_own_task(self):
        task = make_task("mine", assigned_to=MANAGER, reviewer=REVIEWER)
        for status in ("In Progress", "In Review"):
            task.status = status
            task.save()
        frappe.set_user(MANAGER)
        self.assertEqual(get_task(task.name)["allowed_statuses"], ["In Progress", "Cancelled"])
        with self.assertRaises(frappe.PermissionError):
            update_status(task.name, "Completed")

    def test_allowed_statuses_are_empty_without_write_access(self):
        task = make_task("read only for others", assigned_to=ASSIGNEE)
        allowed_statuses_for = frappe.get_attr(
            "helpdesk.helpdesk.doctype.hd_task.hd_task.allowed_statuses_for"
        )
        self.assertEqual(allowed_statuses_for(task, OTHER), [])

    def test_allowed_statuses_match_what_the_server_accepts(self):
        """The option list and HDTask.validate share their helpers; this proves they cannot drift:
        for every user, every starting status and every target, a status is offered exactly when the
        server accepts the change."""
        task = make_task("rules", assigned_to=ASSIGNEE, reviewer=REVIEWER)
        for user in (ASSIGNEE, REVIEWER, MANAGER):
            for old in STATUSES:
                for new in STATUSES:
                    if new == old:
                        continue
                    frappe.set_user("Administrator")
                    frappe.db.set_value(
                        "HD Task",
                        task.name,
                        {
                            "status": old,
                            "blocked_reason": "waiting" if old == "Blocked" else None,
                            "completed_on": None,
                            "completed_by": None,
                        },
                    )
                    frappe.set_user(user)
                    offered = new in get_task(task.name)["allowed_statuses"]
                    try:
                        update_status(task.name, new, "a reason")
                        accepted = True
                    except (frappe.ValidationError, frappe.PermissionError):
                        accepted = False
                    frappe.clear_messages()
                    self.assertEqual(
                        offered,
                        accepted,
                        f"{user}: {old} -> {new} (offered {offered}, accepted {accepted})",
                    )

    def test_blocking_a_task_needs_a_reason(self):
        task = make_task("block me", assigned_to=ASSIGNEE)
        task.status = "In Progress"
        task.save()
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.ValidationError):
            update_status(task.name, "Blocked")
        with self.assertRaises(frappe.ValidationError):
            update_status(task.name, "Blocked", "   ")
        self.assertEqual(update_status(task.name, "Blocked", "waiting on design")["status"], "Blocked")

    def test_returning_a_task_from_review_needs_a_comment(self):
        task = self.task_in_review()
        frappe.set_user(REVIEWER)
        with self.assertRaises(frappe.ValidationError):
            update_status(task.name, "In Progress")
        self.assertEqual(update_status(task.name, "In Progress", "needs rework")["status"], "In Progress")

    def test_update_task_fields_saves_and_validates(self):
        project = make_task_project("Sidebar Project")
        other = make_task_project("Sidebar Other Project")
        milestone = make_task_milestone(project, "Sidebar Milestone")
        task = make_task("edit me", assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)

        result = update_task_fields(
            task.name,
            {
                "priority": "High",
                "reviewer": REVIEWER,
                "project": project,
                "milestone": milestone,
                "start_date": "2026-11-01",
                "due_date": "2026-11-05",
            },
        )
        self.assertEqual(result["priority"], "High")
        saved = frappe.db.get_value(
            "HD Task",
            task.name,
            ["priority", "reviewer", "project", "milestone", "start_date", "due_date"],
            as_dict=True,
        )
        self.assertEqual(
            (saved.priority, saved.reviewer, saved.project, saved.milestone),
            ("High", REVIEWER, project, milestone),
        )
        self.assertEqual((str(saved.start_date), str(saved.due_date)), ("2026-11-01", "2026-11-05"))

        # a milestone of another project is refused, and nothing is saved
        with self.assertRaises(task_api.InvalidTask):
            update_task_fields(task.name, {"project": other})
        self.assertEqual(frappe.db.get_value("HD Task", task.name, "project"), project)
        # changing the project together with emptying the milestone is accepted
        update_task_fields(task.name, {"project": other, "milestone": ""})
        saved = frappe.db.get_value("HD Task", task.name, ["project", "milestone"], as_dict=True)
        self.assertEqual((saved.project, saved.milestone), (other, None))
        # the due date may not precede the start date
        with self.assertRaises(task_api.InvalidTask):
            update_task_fields(task.name, {"due_date": "2026-10-01"})
        # an empty value clears the field
        update_task_fields(task.name, {"reviewer": ""})
        self.assertIsNone(frappe.db.get_value("HD Task", task.name, "reviewer"))

    def test_update_task_fields_refuses_other_fields_and_empty_edits(self):
        task = make_task("locked fields", assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        for values in (
            {"status": "Completed"},
            {"assigned_to": OTHER},
            {"owner": OTHER},
            {"progress": 100},
            {},
        ):
            with self.assertRaises(task_api.InvalidTask):
                update_task_fields(task.name, values)
        stored = frappe.db.get_value(
            "HD Task", task.name, ["status", "assigned_to", "owner"], as_dict=True
        )
        self.assertEqual((stored.status, stored.assigned_to), ("Planned", ASSIGNEE))

    def test_update_task_fields_refuses_a_disabled_reviewer(self):
        task = make_task("disabled reviewer", assigned_to=ASSIGNEE)
        gone = "task-gone-reviewer@example.com"
        create_agent(gone)
        frappe.db.set_value("User", gone, "enabled", 0)
        try:
            frappe.set_user(ASSIGNEE)
            with self.assertRaises(task_api.InvalidTask):
                update_task_fields(task.name, {"reviewer": gone})
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("User", gone, "enabled", 1)

    def test_an_agent_cannot_edit_sidebar_fields_of_a_task_they_cannot_write(self):
        task = make_task("not yours", assigned_to=ASSIGNEE)
        frappe.set_user(OTHER)
        with self.assertRaises(frappe.PermissionError):
            update_task_fields(task.name, {"priority": "Urgent"})
        self.assertEqual(frappe.db.get_value("HD Task", task.name, "priority"), "Medium")
        # a plain user (no Agent role) is refused before anything is looked at
        frappe.set_user(PLAIN)
        with self.assertRaises(frappe.PermissionError):
            update_task_fields(task.name, {"priority": "Urgent"})

    def test_handing_the_review_away_reports_lost_access(self):
        task = make_task("review handover", assigned_to=ASSIGNEE, reviewer=REVIEWER)
        frappe.set_user(REVIEWER)
        result = update_task_fields(task.name, {"reviewer": OTHER})
        self.assertEqual(result, {"name": task.name, "access_lost": True})

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

    # --- assign_task ---

    EMPLOYEE = {
        "employee_name": "Test Employee",
        "department": "Ops",
        "designation": "Engineer",
        "email": "task-employee@example.com",
    }

    def hrms_employee(self, mapped_user=ASSIGNEE):
        return (
            patch(
                "helpdesk.helpdesk.doctype.hd_task.hd_task.hrms.get_employee",
                return_value=self.EMPLOYEE,
            ),
            patch(
                "helpdesk.helpdesk.doctype.hd_task.hd_task.map_emails_to_users",
                return_value={self.EMPLOYEE["email"]: mapped_user},
            ),
        )

    def test_assign_task_to_an_hrms_employee(self):
        task = make_task(assigned_to=MANAGER)
        frappe.set_user(MANAGER)
        get, mapping = self.hrms_employee()
        with get, mapping:
            result = assign_task(task.name, "Employee", hrms_employee_id="E-1")
        self.assertEqual(result["hrms_employee_id"], "E-1")
        self.assertEqual(result["hrms_employee_name"], "Test Employee")
        self.assertEqual(result["assigned_to"], ASSIGNEE)
        self.assertEqual(result["assignee"]["name"], ASSIGNEE)
        self.assertEqual(frappe.db.get_value("HD Task", task.name, "assigned_to"), ASSIGNEE)
        self.assertEqual(len(self.notification_subjects(ASSIGNEE)), 1)

    def test_assign_task_to_a_freelancer_clears_the_user_and_employee(self):
        freelancer = make_task_freelancer("Assign Freelancer")
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(MANAGER)
        result = assign_task(task.name, "Freelancer", freelancer=freelancer)
        self.assertEqual(result["freelancer"], freelancer)
        self.assertIsNone(result["assigned_to"])
        self.assertIsNone(result["hrms_employee_id"])
        self.assertEqual(
            frappe.db.get_value("HD Task", task.name, "assignee_type"), "Freelancer"
        )

    def test_assign_task_rejects_invalid_assignees_and_changes_nothing(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(MANAGER)
        for kwargs in (
            {"assignee_type": "Robot"},
            {"assignee_type": "Employee"},
            {"assignee_type": "Freelancer"},
            {"assignee_type": "Freelancer", "freelancer": "No Such Freelancer"},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(task_api.InvalidTask):
                    assign_task(task.name, **kwargs)
        with patch(
            "helpdesk.helpdesk.doctype.hd_task.hd_task.hrms.get_employee",
            return_value=None,
        ):
            with self.assertRaises(task_api.InvalidTask):
                assign_task(task.name, "Employee", hrms_employee_id="E-404")
        task.reload()
        self.assertEqual(task.assigned_to, ASSIGNEE)
        self.assertEqual(task.assignee_type, "Employee")
        self.assertFalse(task.hrms_employee_id)

    def test_assign_task_is_refused_for_an_agent_with_no_part_in_the_task(self):
        task = make_task(assigned_to=OTHER)
        frappe.set_user(ASSIGNEE)
        with self.assertRaises(frappe.PermissionError):
            assign_task(task.name, "Freelancer", freelancer=make_task_freelancer())
        self.assertEqual(frappe.db.get_value("HD Task", task.name, "assigned_to"), OTHER)

    def test_assign_task_by_the_assignee_keeps_the_hand_over_possible(self):
        freelancer = make_task_freelancer("Handover Freelancer")
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        result = assign_task(task.name, "Freelancer", freelancer=freelancer)
        self.assertEqual(result["freelancer"], freelancer)

    def test_assignee_who_hands_a_task_over_can_no_longer_read_it(self):
        # What the task page relies on: after the hand-over the old assignee's read is refused.
        freelancer = make_task_freelancer("Handover Freelancer 2")
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        assign_task(task.name, "Freelancer", freelancer=freelancer)
        with self.assertRaises(frappe.PermissionError):
            get_task(task.name)

    def test_create_task_saves_the_description_and_defaults_the_assignee(self):
        frappe.set_user(ASSIGNEE)
        result = create_task(
            {"subject": "With description", "description": "<p>Plan <b>it</b></p>"},
            request_id="desc-1",
        )
        self.assertEqual(result["assigned_to"], ASSIGNEE)
        shown = get_task(result["name"])
        self.assertIn("Plan", shown["description"])
        self.assertEqual(create_task({"subject": "x"}, request_id="desc-1")["name"], result["name"])
        self.assertEqual(frappe.db.count("HD Task", {"subject": "With description"}), 1)

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
            task_api.reply_via_email,
            task_api.bulk_assign,
            task_api.assign_task,
            task_api.bulk_update_status,
            task_api.update_task_fields,
        )
        allowed = frappe.allowed_http_methods_for_whitelisted_func
        for fn in reads:
            # GET must be allowed; POST is also accepted because frappe-ui resources POST by default.
            # What matters is that none of these functions writes (checked below by the writes list).
            self.assertIn("GET", allowed[fn], fn.__name__)
            self.assertLessEqual(set(allowed[fn]), {"GET", "POST"}, fn.__name__)
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

    def test_reply_via_email_is_denied_to_an_unrelated_agent(self):
        task = make_task(assigned_to=OTHER)
        frappe.set_user(ASSIGNEE)
        with patch.object(EmailAccount, "find_default_outgoing", return_value=OUTGOING):
            with self.assertRaises(frappe.PermissionError):
                reply_via_email(task.name, "<p>hi</p>", "someone@example.com")
        self.assertEqual(self.task_emails(task.name), 0)

    def test_reply_via_email_rejects_invalid_recipients(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        bad = (
            {"to": "not-an-email"},
            {"to": "ok@example.com", "cc": "bad address@example.com"},
            {"to": "ok@example.com", "bcc": "x@example.com" + chr(13) + chr(10) + "Bcc: y@example.com"},
            {"to": ""},
            {"to": [f"u{i}@example.com" for i in range(21)]},
        )
        with patch.object(EmailAccount, "find_default_outgoing", return_value=OUTGOING):
            for kwargs in bad:
                with self.subTest(**kwargs):
                    with self.assertRaises(frappe.ValidationError):
                        reply_via_email(task.name, "<p>hi</p>", **kwargs)
            with self.assertRaises(frappe.ValidationError):
                reply_via_email(task.name, "<p> </p>", "ok@example.com")
        self.assertEqual(self.task_emails(task.name), 0)

    def test_reply_via_email_creates_a_linked_communication_and_queues_it(self):
        self.ensure_outgoing_account()
        task = make_task(assigned_to=ASSIGNEE, reviewer=REVIEWER)
        # the reviewer may write too (same rule as every other task endpoint)
        for user in (ASSIGNEE, REVIEWER):
            frappe.set_user(user)
            with patch.object(
                EmailAccount, "find_default_outgoing", return_value=OUTGOING
            ), patch.object(task_api.frappe, "sendmail") as sendmail:
                result = reply_via_email(
                    task.name,
                    "<p>Update <script>alert(1)</script>for you</p>",
                    "a@example.com; b@example.com, a@example.com",
                    cc="c@example.com",
                )
            sendmail.assert_called_once()
            kwargs = sendmail.call_args.kwargs
            self.assertEqual(kwargs["recipients"], ["a@example.com", "b@example.com"])
            self.assertEqual(kwargs["cc"], ["c@example.com"])
            self.assertEqual(kwargs["reference_doctype"], "HD Task")
            self.assertEqual(kwargs["reference_name"], task.name)
            self.assertTrue(kwargs["delayed"])
        rows = frappe.get_all(
            "Communication",
            filters={"reference_doctype": "HD Task", "reference_name": task.name},
            fields=["communication_type", "sent_or_received", "sender", "recipients", "content", "owner"],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual({r.owner for r in rows}, {ASSIGNEE, REVIEWER})
        for row in rows:
            self.assertEqual(row.communication_type, "Communication")
            self.assertEqual(row.sent_or_received, "Sent")
            self.assertEqual(row.sender, OUTGOING.email_id)
            self.assertEqual(row.recipients, "a@example.com, b@example.com")
            self.assertNotIn("<script", row.content)
        self.assertEqual(len(result["emails"]), 2)

    def test_reply_via_email_is_allowed_to_a_manager_on_any_task(self):
        self.ensure_outgoing_account()
        task = make_task(assigned_to=OTHER)
        frappe.set_user(MANAGER)
        with patch.object(
            EmailAccount, "find_default_outgoing", return_value=OUTGOING
        ), patch.object(task_api.frappe, "sendmail"):
            reply_via_email(task.name, "<p>hi</p>", "a@example.com")
        self.assertEqual(self.task_emails(task.name), 1)

    def test_reply_via_email_without_an_outgoing_account_is_a_clear_error(self):
        task = make_task(assigned_to=ASSIGNEE)
        frappe.set_user(ASSIGNEE)
        with patch.object(
            EmailAccount, "find_default_outgoing", return_value=None
        ), patch.object(task_api.frappe, "sendmail") as sendmail:
            with self.assertRaises(frappe.ValidationError) as ctx:
                reply_via_email(task.name, "<p>hi</p>", "a@example.com")
        self.assertIn("No outgoing email account is configured", str(ctx.exception))
        sendmail.assert_not_called()
        self.assertEqual(self.task_emails(task.name), 0)

    def ensure_outgoing_account(self):
        """A Communication links to its Email Account, so the fixture must exist for real."""
        if not frappe.db.exists("Email Account", OUTGOING.name):
            frappe.get_doc(
                {
                    "doctype": "Email Account",
                    "email_account_name": OUTGOING.name,
                    "email_id": OUTGOING.email_id,
                    "enable_outgoing": 1,
                    "smtp_server": "localhost",
                    "smtp_port": 25,
                }
            ).insert(ignore_permissions=True, ignore_mandatory=True)

    def task_emails(self, name):
        return frappe.db.count(
            "Communication", {"reference_doctype": "HD Task", "reference_name": name}
        )

    def test_schema_has_no_ticket_or_customer_fields(self):
        fields = {f.fieldname for f in frappe.get_meta("HD Task").fields}
        self.assertFalse({"ticket", "customer", "reference_ticket"} & fields)
