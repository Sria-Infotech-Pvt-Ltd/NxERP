import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime, today

from helpdesk.integrations.external import hrms, pbt
from helpdesk.integrations.external.client import ExternalAPIError
from helpdesk.integrations.external.mapping import map_emails_to_users

# (from_status, to_status). Moving to "Cancelled" is allowed from any status.
ALLOWED_TRANSITIONS = {
    ("Planned", "In Progress"),
    ("In Progress", "In Review"),
    ("In Progress", "Blocked"),
    ("Blocked", "In Progress"),
    ("In Review", "Completed"),
    ("In Review", "In Progress"),
}
CLOSED_STATUSES = ("Completed", "Cancelled")
MANAGER_ROLES = {"System Manager", "Agent Manager"}
# PBT resource types a task can be assigned to; vendors and external people cannot.
ASSIGNABLE_RESOURCE_TYPES = ("employee", "freelancer")
PBT_RESOURCE_FIELDS = ("pbt_resource_type", "pbt_resource_code", "pbt_resource_name")


class HDTask(Document):
    def before_validate(self):
        self.set_default_assignee()

    def validate(self):
        self.validate_pbt_project()
        self.validate_pbt_milestone()
        self.validate_pbt_resource()
        self.validate_assignee_type()
        self.validate_hrms_employee()
        self.validate_milestone()
        self.validate_dates()
        self.validate_status_transition()
        self.validate_blocked_reason()
        self.validate_users_enabled()
        self.protect_system_fields()
        self.update_completion()
        self.update_progress()

    def after_insert(self):
        self.notify_assignment()

    def on_update(self):
        self.record_status_reason()
        self.notify_assignment_change()
        self.notify_returned_from_review()

    def set_default_assignee(self):
        # A freelancer has no user account, so the creator must not be recorded as the assignee.
        # An HRMS employee or PBT resource is mapped to a user (or to nobody) during validate.
        if (
            self.is_new()
            and not self.assigned_to
            and self.assignee_type != "Freelancer"
            and not self.hrms_employee_id
            and not self.pbt_assignment_id
        ):
            self.assigned_to = frappe.session.user

    def validate_assignee_type(self):
        if self.assignee_type == "Freelancer":
            if not self.freelancer and self.pbt_resource_type != "freelancer":
                frappe.throw(_("Select a freelancer for this task"))
            self.assigned_to = None
            self.department = None
            self.designation = None
            self.hrms_employee_id = None
        else:
            self.freelancer = None

    def validate_pbt_project(self):
        """The id is the reference; name and status are re-read from PBT so a client cannot spoof them."""
        if not self.pbt_project_id:
            self.pbt_project_name = None
            self.pbt_project_status = None
            return
        if self.project:
            frappe.throw(_("Choose either a PBT project or a local project, not both"))
        if self.pbt_reference_unchanged():
            return

        project = self.fetch_external(pbt.get_project, self.pbt_project_id)
        if not project:
            frappe.throw(_("Project {0} was not found in PBT").format(self.pbt_project_id))
        self.pbt_project_name = project["project_name"]
        self.pbt_project_status = project["status"]

    def validate_pbt_milestone(self):
        """The milestone must belong to the PBT project. Its name is read from PBT when the
        project or milestone changes, and otherwise kept from the saved task, so a client cannot spoof it."""
        if not self.pbt_milestone_id:
            self.pbt_milestone_name = None
            return
        if not self.pbt_project_id:
            frappe.throw(_("Select a PBT project before choosing its milestone"))

        previous = self.get_doc_before_save()
        if (
            previous
            and previous.pbt_project_id == self.pbt_project_id
            and previous.pbt_milestone_id == self.pbt_milestone_id
        ):
            self.pbt_milestone_name = previous.pbt_milestone_name
            return

        milestone = self.fetch_external(pbt.get_milestone, self.pbt_project_id, self.pbt_milestone_id)
        if not milestone:
            frappe.throw(
                _("Milestone {0} was not found in PBT project {1}").format(
                    self.pbt_milestone_id, self.pbt_project_id
                )
            )
        self.pbt_milestone_name = milestone["milestone_name"]

    def validate_pbt_resource(self):
        """The assignee picked from the PBT project's resources. Type, code and name are read from PBT
        when the project, milestone or assignment changes and otherwise kept from the saved task."""
        if not self.pbt_assignment_id:
            self.clear_pbt_resource()
            return
        if not self.pbt_project_id:
            frappe.throw(_("Select a PBT project before choosing one of its resources"))

        previous = self.get_doc_before_save()
        if previous and all(
            previous.get(f) == self.get(f) for f in ("pbt_project_id", "pbt_milestone_id", "pbt_assignment_id")
        ):
            if previous.assigned_to != self.assigned_to and previous.pbt_resource_type == "employee":
                # Handed to a Help Desk user directly: the PBT resource no longer describes the assignee.
                self.clear_pbt_resource()
                return
            for fieldname in PBT_RESOURCE_FIELDS:
                self.set(fieldname, previous.get(fieldname))
        else:
            resource = self.fetch_external(
                pbt.get_resource, self.pbt_project_id, self.pbt_assignment_id, self.pbt_milestone_id
            )
            if not resource:
                frappe.throw(
                    _("Resource assignment {0} was not found in the selected PBT project or milestone").format(
                        self.pbt_assignment_id
                    )
                )
            if resource["resource_type"] not in ASSIGNABLE_RESOURCE_TYPES:
                frappe.throw(_("Only employees and freelancers can be assigned a task"))
            self.pbt_resource_type = resource["resource_type"]
            self.pbt_resource_code = resource["resource_code"]
            self.pbt_resource_name = resource["resource_name"]
        self.apply_pbt_resource()

    def apply_pbt_resource(self):
        """A PBT freelancer replaces the local freelancer. A PBT employee is linked through HRMS by
        their AIRA id when PBT has one; without it the task only records the PBT name."""
        if self.pbt_resource_type == "freelancer":
            self.assignee_type = "Freelancer"
            self.freelancer = None
        else:
            self.assignee_type = "Employee"
            self.hrms_employee_id = self.pbt_resource_code
            if not self.pbt_resource_code:
                # No AIRA id means no Help Desk user can be found, and the field's "__user" default
                # would otherwise make the creator the assignee.
                self.assigned_to = None

    def clear_pbt_resource(self):
        self.pbt_assignment_id = None
        for fieldname in PBT_RESOURCE_FIELDS:
            self.set(fieldname, None)

    def validate_hrms_employee(self):
        """Verify the employee in HRMS and link a Frappe User only through a matching email.
        An HRMS employee id is never a user id, so an unmapped employee leaves `assigned_to` empty."""
        previous = self.get_doc_before_save()
        if (
            self.hrms_employee_id
            and previous
            and previous.hrms_employee_id == self.hrms_employee_id
            and previous.assigned_to != self.assigned_to
        ):
            # Handed to a Help Desk user directly: the HRMS employee no longer describes the assignee.
            self.hrms_employee_id = None

        if not self.hrms_employee_id:
            self.hrms_employee_name = None
            self.hrms_department = None
            self.hrms_designation = None
            return
        if previous and previous.hrms_employee_id == self.hrms_employee_id:
            return

        employee = self.fetch_external(hrms.get_employee, self.hrms_employee_id)
        if not employee and self.hrms_employee_id_from_pbt():
            self.unlink_hrms_employee()
            return
        if not employee:
            frappe.throw(_("Employee {0} was not found in HRMS").format(self.hrms_employee_id))
        self.hrms_employee_name = employee["employee_name"]
        self.hrms_department = employee["department"]
        self.hrms_designation = employee["designation"]
        self.assigned_to = map_emails_to_users([employee["email"]]).get(employee["email"])

    def hrms_employee_id_from_pbt(self):
        return self.pbt_resource_type == "employee" and self.hrms_employee_id == self.pbt_resource_code

    def unlink_hrms_employee(self):
        """PBT owns project assignments, and its employee codes do not always match HRMS ids, so a code
        HRMS does not know keeps the PBT resource as the assignee with no HRMS employee or Help Desk user."""
        self.hrms_employee_id = None
        self.hrms_employee_name = None
        self.hrms_department = None
        self.hrms_designation = None
        self.assigned_to = None

    def pbt_reference_unchanged(self):
        previous = self.get_doc_before_save()
        return bool(previous and previous.pbt_project_id == self.pbt_project_id)

    @staticmethod
    def fetch_external(fn, *args):
        try:
            return fn(*args)
        except ExternalAPIError as e:
            frappe.throw(e.message, title=_("External service error"))

    def validate_milestone(self):
        if not self.milestone:
            return
        milestone_project = frappe.db.get_value("HD Task Milestone", self.milestone, "project")
        if milestone_project != self.project:
            frappe.throw(_("Milestone {0} does not belong to the selected project").format(self.milestone))

    def validate_dates(self):
        if self.start_date and self.due_date:
            if getdate(self.due_date) < getdate(self.start_date):
                frappe.throw(_("Due Date cannot be earlier than Start Date"))

    def validate_status_transition(self):
        previous = self.get_doc_before_save()
        if not previous:
            return

        old, new = previous.status, self.status
        if old == new:
            return

        if new != "Cancelled" and (old, new) not in ALLOWED_TRANSITIONS:
            frappe.throw(
                _("Status cannot change from {0} to {1}").format(old, new),
                title=_("Invalid Status Change"),
            )

        if old == "In Review" and new in ("Completed", "In Progress"):
            self.validate_reviewer_action(new)

        if old == "In Review" and new == "In Progress":
            if not (self.flags.status_reason or "").strip():
                frappe.throw(_("A comment is required to return a task from review"))

    def validate_reviewer_action(self, new_status):
        """Approving or returning a task is limited to its reviewer or an Agent Manager."""
        user = frappe.session.user
        if user == self.assigned_to and new_status == "Completed":
            frappe.throw(_("You cannot approve your own task"), frappe.PermissionError)

        is_reviewer = bool(self.reviewer) and user == self.reviewer
        if not (is_reviewer or MANAGER_ROLES & set(frappe.get_roles(user))):
            frappe.throw(
                _("Only the reviewer or an Agent Manager can do this"),
                frappe.PermissionError,
            )

    def validate_blocked_reason(self):
        if self.status != "Blocked":
            self.blocked_reason = None
        elif not (self.blocked_reason or "").strip():
            frappe.throw(_("Blocked Reason is required when a task is Blocked"))

    def validate_users_enabled(self):
        for fieldname in ("assigned_to", "reviewer"):
            user = self.get(fieldname)
            if user and not frappe.db.get_value("User", user, "enabled"):
                frappe.throw(_("{0} is disabled").format(user))

    def protect_system_fields(self):
        """completed_on / completed_by are server-owned; discard anything sent by the client."""
        previous = self.get_doc_before_save()
        self.completed_on = previous.completed_on if previous else None
        self.completed_by = previous.completed_by if previous else None

    def update_completion(self):
        if self.status == "Completed":
            if not self.completed_on:
                self.completed_on = now_datetime()
                self.completed_by = frappe.session.user
        else:
            self.completed_on = None
            self.completed_by = None

    def update_progress(self):
        if self.status == "Completed":
            self.progress = 100
            return

        total = len(self.checklist)
        done = sum(1 for row in self.checklist if row.done)
        # Half-up, so 1 of 8 (12.5%) always shows 13% rather than banker's 12%.
        self.progress = int(done * 100 / total + 0.5) if total else 0

    def record_status_reason(self):
        reason = (self.flags.status_reason or "").strip()
        if not reason:
            return
        previous = self.get_doc_before_save()
        if previous and previous.status != self.status:
            self.add_comment("Comment", reason)

    def is_overdue(self):
        return bool(
            self.due_date
            and getdate(self.due_date) < getdate(today())
            and self.status not in CLOSED_STATUSES
        )

    def notify_assignment(self):
        self.send_notification(
            self.assigned_to,
            _("{0} assigned you the task {1}").format(self.actor_name(), self.name),
            self.subject,
        )

    def notify_assignment_change(self):
        previous = self.get_doc_before_save()
        if previous and previous.assigned_to != self.assigned_to:
            self.notify_assignment()

    def notify_returned_from_review(self):
        previous = self.get_doc_before_save()
        if not previous:
            return
        if previous.status == "In Review" and self.status == "In Progress":
            self.send_notification(
                self.assigned_to,
                _("{0} returned task {1} from review").format(
                    self.actor_name(), self.name
                ),
                self.flags.status_reason,
            )

    def notify_overdue(self):
        subject = _("Task {0} is overdue (due {1})").format(self.name, self.due_date)
        already_sent = frappe.db.exists(
            "Notification Log",
            {
                "document_type": "HD Task",
                "document_name": self.name,
                "subject": subject,
            },
        )
        if already_sent:
            return
        self.send_notification(self.assigned_to, subject, self.subject)

    def actor_name(self):
        return frappe.utils.get_fullname(frappe.session.user)

    def send_notification(self, recipient, subject, content=None):
        """Best effort: a failed notification must never fail the task operation."""
        if not recipient or recipient == frappe.session.user:
            return
        try:
            frappe.get_doc(
                {
                    "doctype": "Notification Log",
                    "type": "Alert",
                    "for_user": recipient,
                    "from_user": frappe.session.user,
                    "subject": subject,
                    "email_content": content or "",
                    "document_type": self.doctype,
                    "document_name": self.name,
                    "link": frappe.utils.get_url(f"/helpdesk/tasks/{self.name}"),
                }
            ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="HD Task notification failed")

    @staticmethod
    def default_list_data():
        """Columns and fields the generic list view (helpdesk.api.doc.get_list_data) loads by default."""
        columns = [
            {"label": "ID", "type": "Data", "key": "name", "width": "minmax(0, 1.2fr)"},
            {"label": "Subject", "type": "Data", "key": "subject", "width": "minmax(0, 3fr)"},
            {"label": "Status", "type": "Select", "key": "status", "width": "minmax(0, 1.6fr)"},
            {"label": "Due Date", "type": "Date", "key": "due_date", "width": "minmax(0, 1.4fr)"},
            {"label": "PBT Project", "type": "Data", "key": "pbt_project_name", "width": "minmax(0, 1.8fr)"},
            {"label": "Employee", "type": "Data", "key": "hrms_employee_name", "width": "minmax(0, 1.8fr)"},
        ]
        rows = [
            "name",
            "subject",
            "status",
            "due_date",
            "pbt_project_name",
            "hrms_employee_name",
            "modified",
            "creation",
        ]
        return {"columns": columns, "rows": rows}


def permission_query(user):
    if not user:
        user = frappe.session.user

    roles = set(frappe.get_roles(user))
    if "Administrator" == user or MANAGER_ROLES & roles:
        return ""
    if "Agent" not in roles:
        return "1=0"

    escaped = frappe.db.escape(user)
    return (
        f"(`tabHD Task`.owner = {escaped} OR `tabHD Task`.assigned_to = {escaped}"
        f" OR `tabHD Task`.reviewer = {escaped})"
    )


def has_permission(doc, user=None, ptype=None):
    if not user:
        user = frappe.session.user

    roles = set(frappe.get_roles(user))
    if user == "Administrator" or MANAGER_ROLES & roles:
        return True
    if "Agent" not in roles:
        return False
    # A new document has no owner yet; the role-level create check already passed.
    if ptype == "create":
        return True

    # Judge access by what is stored: a pending reassignment in memory must not
    # revoke the current assignee's right to hand the task over.
    name = doc.get("name")
    stored = name and frappe.db.get_value(
        "HD Task", name, ["owner", "assigned_to", "reviewer"], as_dict=True
    )
    people = stored or doc
    return user in (people.owner, people.assigned_to, people.reviewer)


def notify_overdue_tasks():
    """Daily scheduler job; one notification per task per due date."""
    names = frappe.get_all(
        "HD Task",
        filters={
            "due_date": ["between", ["1900-01-01", add_days(today(), -1)]],
            "status": ["not in", CLOSED_STATUSES],
            "assigned_to": ["is", "set"],
        },
        pluck="name",
    )
    for name in names:
        frappe.get_doc("HD Task", name).notify_overdue()
