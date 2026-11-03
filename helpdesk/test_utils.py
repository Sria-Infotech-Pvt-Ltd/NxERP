import json
import os
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.core.doctype.communication.test_communication import create_email_account
from frappe.utils import add_to_date, getdate

from helpdesk.api.settings.field_dependency import create_update_field_dependency
from helpdesk.consts import DEFAULT_SLA
from helpdesk.integrations.erpnext.utils import create_customer_field
from helpdesk.utils import get_customers, is_frappe_version

if is_frappe_version("16", above=True):
    from frappe.tests.utils import make_test_objects
else:
    from frappe.test_runner import make_test_objects


SLA_PRIORITY_NAME = "SLA Priority"
TEST_HOLIDAY_LIST_NAME = "Test Holiday List"


def before_tests():
    frappe.db.set_single_value("HD Settings", "skip_email_workflow", 0)  # nosemgrep
    frappe.db.set_single_value(
        "HD Settings", "enable_email_ticket_feedback", 0
    )  # nosemgrep
    frappe.db.set_single_value("HD Settings", "default_priority", None)
    # frappe.flags.mute_emails = True
    make_holiday_list()
    make_new_sla()
    make_test_objects("Email Domain", reset=True)
    create_email_account()
    create_customer_field()
    complete_erpnext_setup()
    frappe.db.commit()  # nosemgrep


def make_new_sla():
    condition = "doc.priority in ['High', 'Urgent', 'Low']"
    sla_doc = make_sla(SLA_PRIORITY_NAME, condition)
    sla_doc = sla_doc.reload()
    sla_doc.holiday_list = TEST_HOLIDAY_LIST_NAME

    sla_doc.support_and_resolution = []
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        service_day = frappe.get_doc(
            {
                "doctype": "HD Service Day",
                "workday": day,
                "start_time": "10:00:00",
                "end_time": "18:00:00",
            }
        )
        sla_doc.append("support_and_resolution", service_day)

    low_priority = frappe.get_doc(
        {
            "doctype": "HD Service Level Priority",
            "default_priority": 0,
            "priority": "Low",
            "response_time": 60 * 60 * 24,
            "resolution_time": 60 * 60 * 72,
        }
    )

    medium_priority = frappe.get_doc(
        {
            "doctype": "HD Service Level Priority",
            "default_priority": 1,
            "priority": "Medium",
            "response_time": 60 * 60 * 8,
            "resolution_time": 60 * 60 * 24,
        }
    )

    high_priority = frappe.get_doc(
        {
            "doctype": "HD Service Level Priority",
            "default_priority": 0,
            "priority": "High",
            "response_time": 60 * 60 * 1,
            "resolution_time": 60 * 60 * 4,
        }
    )

    urgent_priority = frappe.get_doc(
        {
            "doctype": "HD Service Level Priority",
            "default_priority": 0,
            "priority": "Urgent",
            "response_time": 60 * 30,
            "resolution_time": 60 * 60 * 2,
        }
    )
    sla_doc.priorities = []
    sla_doc.append("priorities", low_priority)
    sla_doc.append("priorities", medium_priority)
    sla_doc.append("priorities", high_priority)
    sla_doc.append("priorities", urgent_priority)

    sla_doc.save()


def make_holiday_list():
    if not frappe.db.exists("HD Service Holiday List", TEST_HOLIDAY_LIST_NAME):
        # from_date = first date of current year
        from_date = datetime(datetime.today().year, 1, 1).date()
        to_date = datetime(datetime.today().year + 1, 1, 15).date()
        frappe.get_doc(
            {
                "doctype": "HD Service Holiday List",
                "holiday_list_name": TEST_HOLIDAY_LIST_NAME,
                "from_date": from_date,
                "to_date": to_date,
            }
        ).insert()


def make_sla(
    sla_name: str = "Test SLA",
    condition: str = "",
    rank: int = 0,
    priorities: list[str] | None = None,
):
    """Copy the seeded SLA. `priorities` replaces its priority rows, the
    first becoming the default priority, each row slower than the one before."""
    def_sla = frappe.get_doc("HD Service Level Agreement", DEFAULT_SLA)
    sla_doc = frappe.copy_doc(def_sla)
    sla_doc.service_level = sla_name
    sla_doc.condition = condition
    sla_doc.default_sla = 0
    sla_doc.rank = rank
    if priorities:
        sla_doc.priorities = []
        for index, priority in enumerate(priorities):
            sla_doc.append(
                "priorities",
                {
                    "priority": priority,
                    "default_priority": index == 0,
                    "response_time": 60 * 60 * (index + 1),
                    "resolution_time": 60 * 60 * 4 * (index + 1),
                },
            )
    sla_doc.insert(ignore_if_duplicate=True, ignore_permissions=True)
    return sla_doc


def make_priority(name: str):
    """Create an HD Ticket Priority. It is not added to any SLA."""
    if frappe.db.exists("HD Ticket Priority", name):
        return frappe.get_doc("HD Ticket Priority", name)
    return frappe.get_doc({"doctype": "HD Ticket Priority", "name": name}).insert(
        ignore_permissions=True
    )


def make_ticket(
    subject: str = "Test Ticket",
    description: str = "This is a test ticket.",
    save: bool = True,
    **args,
):
    """
    Creates a test HD Ticket with the given subject, description, priority, and ticket type.
    """
    ticket = frappe.get_doc(
        {"doctype": "HD Ticket", "subject": subject, "description": description, **args}
    )
    if save:
        ticket.insert(ignore_if_duplicate=True, ignore_permissions=True)
    return ticket


def create_agent(
    email: str, first_name: str | None = None, last_name: str | None = None
):
    """
    Creates a test agent user with the Agent role.
    """
    if not frappe.db.exists("User", email):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": first_name or email.split("@")[0],
                "last_name": last_name or "Agent",
                "send_welcome_email": 0,
            }
        )
        user.insert(ignore_permissions=True)
    else:
        user = frappe.get_doc("User", email)

    if "Agent" not in frappe.get_roles(email):
        user.add_roles("Agent")

    agent_name = f"{user.first_name} {user.last_name or ''}".strip()
    existing_agent = frappe.db.exists("HD Agent", {"user": email})
    if not existing_agent:
        frappe.get_doc(
            {
                "doctype": "HD Agent",
                "user": email,
                "agent_name": agent_name or email,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True)

    return user


def get_current_week_monday(hours: int = 11):
    """
    Returns the current week's Monday date
    """

    current_date = getdate()
    # Get the current week's Monday
    monday = add_to_date(current_date, days=-current_date.weekday(), hours=hours)
    return monday


def get_priority_response_resolution_time(
    sla: str, priority: str, date=None, add_to_time: bool = True
):
    """
    Returns the expected response or resolution time for a given priority.
    """
    sla = frappe.get_doc("HD Service Level Agreement", sla)
    priorities = sla.get_priorities()
    high_priority = priorities[priority]
    first_response = high_priority.response_time
    resolution_time = high_priority.resolution_time
    if not add_to_time:
        return first_response, resolution_time

    date = date or get_current_week_monday()
    expected_response_by = add_to_date(date, seconds=first_response)

    expected_resolution_by = add_to_date(date, seconds=resolution_time)
    return expected_response_by, expected_resolution_by


def add_holiday(holiday_date, description="_Test Holiday"):
    """
    Adds a holiday to the system.
    """

    holiday_list_doc = frappe.get_doc("HD Service Holiday List", "Test Holiday List")
    holiday_list_doc.append(
        "holidays",
        {
            "holiday_date": holiday_date,
            "description": description,
        },
    )
    holiday_list_doc.save()


def remove_holidays():
    """
    Removes a holiday from the system.
    """
    holiday_list = frappe.get_doc("HD Service Holiday List", TEST_HOLIDAY_LIST_NAME)
    holiday_list.holidays = []
    holiday_list.save()


def create_field_dependency():
    parent_field = "ticket_type"
    child_field = "priority"
    mapping = '{"Unspecified":["Urgent","High"],"Question":["Medium","High"],"Bug":["Medium"],"Incident":["Urgent","High","Medium","Low"]}'
    enabled = 1
    fields_criteria = '{"display":{"enabled":true,"value":[{"label":"Any","value":"Any"}]},"mandatory":{"enabled":true,"value":[{"label":"Question","value":"Question"},{"label":"Bug","value":"Bug"}]}}'

    create_update_field_dependency(
        parent_field, child_field, mapping, enabled, fields_criteria
    )


def make_status(name: str = "Test Status", category: str = "Open"):
    if frappe.db.exists("HD Ticket Status", name):
        return frappe.get_doc("HD Ticket Status", name)

    doc = frappe.get_doc(
        {
            "doctype": "HD Ticket Status",
            "label_agent": name,
            "category": category,
            "is_default": 0,
        }
    )
    return doc.insert(ignore_if_duplicate=True)


def make_agent_status(agent_status: str, category="Away", enabled=1, status_order=None):
    return frappe.get_doc(
        {
            "doctype": "HD Agent Status",
            "agent_status": agent_status,
            "category": category,
            "enabled": enabled,
            "status_order": status_order,
        }
    ).insert()


def make_agent(email: str, first_name: str = "Test Agent"):
    """
    Creates a test user and HD Agent if they don't exist.
    Returns the user email.
    """
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {"doctype": "User", "first_name": first_name, "email": email}
        ).insert(ignore_permissions=True)

    if not frappe.db.exists("HD Agent", {"user": email}):
        frappe.get_doc(
            {"doctype": "HD Agent", "user": email, "agent_name": first_name}
        ).insert(ignore_permissions=True)

    return email


def set_agent_status_enabled(status: str, enabled: bool | int):
    """Toggle a status directly in db, skips the controller checks and the
    agent reset."""
    frappe.db.set_value("HD Agent Status", status, "enabled", int(enabled))


def set_default_agent_status(status: str | None):
    """Set the default agent status directly in db."""
    frappe.db.set_single_value("HD Settings", "default_agent_status", status)


def set_agent_availability(user: str, availability: str | None):
    """Set an agent's availability through the document lifecycle."""
    agent = frappe.get_doc("HD Agent", {"user": user})
    agent.availability = availability
    agent.save(ignore_permissions=True)
    return agent


def get_latest_ticket_communication(ticket_name: str):
    """
    Returns the latest Communication doc linked to the given HD Ticket.
    """
    name = frappe.get_all(
        "Communication",
        filters={
            "reference_doctype": "HD Ticket",
            "reference_name": ticket_name,
        },
        pluck="name",
        limit=1,
    )
    if not name:
        return None
    return frappe.get_doc("Communication", name[0])


def add_message(
    ticket: str, direction: str, sender: str, subject: str = "Test message"
) -> None:
    """Insert a Communication on a ticket at the current (possibly frozen) time."""
    frappe.get_doc(
        {
            "doctype": "Communication",
            "communication_type": "Communication",
            "communication_medium": "Email",
            "sent_or_received": direction,
            "sender": sender,
            "subject": subject,
            "content": subject,
            "reference_doctype": "HD Ticket",
            "reference_name": ticket,
        }
    ).insert(ignore_permissions=True)


def timeline_node(result: dict, key: str) -> dict | None:
    """The milestone with the given key from a ticket analytics response."""
    return next((n for n in result["timeline"] if n["key"] == key), None)


def add_comment(
    ticket: str,
    content: str = "This is a test comment.",
    comment_by: str | None = None,
    save: bool = True,
):
    """
    Creates a test HD Ticket Comment for a given ticket.
    """
    comment = frappe.get_doc(
        {
            "doctype": "HD Ticket Comment",
            "reference_ticket": ticket,
            "content": content,
            "comment_by": comment_by,
        }
    )
    if save:
        return comment.insert()
    return comment


def set_ticket_status_and_communication_date(ticket_name, status, communication_date):
    """Force a ticket's status and the date of all its communications directly in the
    database, bypassing controller side effects. Useful for testing scheduled jobs that
    key off communication_date (auto close, SLA escalation, reminders)."""
    frappe.db.set_value(
        "HD Ticket", ticket_name, "status", status, update_modified=False
    )
    for comm_name in frappe.get_all(
        "Communication",
        filters={"reference_doctype": "HD Ticket", "reference_name": ticket_name},
        pluck="name",
    ):
        frappe.db.set_value(
            "Communication",
            comm_name,
            "communication_date",
            communication_date,
            update_modified=False,
        )


def create_contact(name, email, user=True, role="HD Customer"):
    result = {}

    # Delete any existing contacts with this email so we always start clean
    existing = frappe.db.get_all("Contact", filters={"email_id": email}, pluck="name")
    for c in existing:
        frappe.delete_doc("Contact", c, force=True)

    contact = frappe.get_doc(
        {
            "doctype": "Contact",
            "first_name": name,
            # top-level email_id is what set_contact() queries via
            # frappe.db.get_value("Contact", {"email_id": email_id})
            "email_id": email,
        }
    )
    contact.append("email_ids", {"email_id": email, "is_primary": 1})
    contact.insert()

    result["contact"] = contact.name
    if not user:
        return result

    if frappe.db.exists("User", email):
        # User may have linked docs (tickets) — just strip roles and reuse
        _user = frappe.get_doc("User", email)
        _user.roles = []
        _user.save(ignore_permissions=True)
    else:
        _user = frappe.get_doc({"doctype": "User", "first_name": name, "email": email})
        _user.insert(ignore_permissions=True)

    _user.add_roles(role)

    # link the user to the contact so get_customers(user=email) resolves correctly
    frappe.db.set_value("Contact", contact.name, "user", _user.name)

    result["user"] = _user.name
    return result


def create_customer(name, contacts=[]):
    if frappe.db.exists("HD Customer", name):
        frappe.delete_doc("HD Customer", name, force=True)

    customer = frappe.get_doc({"doctype": "HD Customer", "customer_name": name})

    for c in contacts:
        customer.append("contacts", c)
    return customer.insert()


def create_user(email: str):
    """Create (or fetch) a plain User with no helpdesk roles."""
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    return frappe.get_doc(
        doctype="User",
        email=email,
        first_name=email.split("@")[0],
        send_welcome_email=0,
    ).insert(ignore_permissions=True)


def get_invitation(email: str):
    """Return the helpdesk User Invitation raised for an email, if any."""
    return frappe.db.get_value(
        "User Invitation",
        {"email": email, "app_name": "helpdesk"},
        ["name", "customer", "contact"],
        as_dict=True,
    )


def update_role_in_customer(customer, contact, role="HD Customer", is_primary=False):
    frappe.set_user("Administrator")
    is_manager = True if role == "HD Customer Manager" else False

    for c in customer.get("contacts", []):
        if c.get("contact_name") != contact:
            continue
        c.is_manager = is_manager

    if is_primary:
        customer.primary_contact = contact

    customer.save()


def add_contact_in_customer(customer, contact, is_manager=False, is_primary=False):
    frappe.set_user("Administrator")
    customer.append(
        "contacts",
        {"contact_name": contact, "is_manager": is_manager},
    )
    if is_primary:
        customer.primary_contact = contact

    customer.save()


def cleanup_contact_users(contacts, customers=[]):
    frappe.set_user("Administrator")
    for contact in contacts:
        contact_name = contact.get("contact")
        user_email = contact.get("user")

        # remove from any customer
        linked_customers = get_customers(contact=contact_name)
        for customer in linked_customers:
            customer_doc = frappe.get_doc("HD Customer", customer)
            customer_doc.contacts = [
                c
                for c in customer_doc.contacts
                if c.get("contact_name") != contact_name
            ]
            customer_doc.save()

        if user_email and frappe.db.exists("User", user_email):
            frappe.delete_doc("User", user_email, force=True)

        existing = (
            frappe.db.get_all("Contact", filters={"email_id": user_email}, pluck="name")
            if user_email
            else []
        )
        for c in existing:
            frappe.delete_doc("Contact", c, force=True)

    for c in customers:
        if frappe.db.exists("HD Customer", c):
            frappe.delete_doc("HD Customer", c, force=True)
        if frappe.db.exists("HD Customer", c):
            frappe.delete_doc("HD Customer", c, force=True)
            frappe.delete_doc("HD Customer", c, force=True)
            frappe.delete_doc("HD Customer", c, force=True)
            frappe.delete_doc("HD Customer", c, force=True)
            frappe.delete_doc("HD Customer", c, force=True)


def make_team(team_name, members=[], disabled=False):
    """Create an HD Team with optional members. A default agent is created if no members are provided."""
    if not members:
        members = [make_agent("default_team_agent@example.com")]

    if frappe.db.exists("HD Team", team_name):
        team = frappe.get_doc("HD Team", team_name)
        team.disabled = disabled
        team.users = []
        for member in members:
            team.append("users", {"user": member})
        team.save(ignore_permissions=True)
        return team

    # Create new team - this will trigger after_insert which creates assignment rule
    team = frappe.get_doc(
        {
            "doctype": "HD Team",
            "team_name": team_name,
        }
    )
    for member in members:
        team.append("users", {"user": member})
    team.disabled = disabled
    team.insert(ignore_permissions=True)
    return team


def complete_erpnext_setup():
    """
    Run the ERPNext setup wizard once, so fixtures like Warehouse Type
    exist before test records (e.g. Company) are created.
    """
    if "erpnext" not in frappe.get_installed_apps():
        return
    if frappe.get_all("Company", limit=1):
        return

    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    year = datetime.today().year
    setup_complete(
        {
            "currency": "INR",
            "full_name": "Test User",
            "company_name": "_Test Company",
            "timezone": "Asia/Kolkata",
            "company_abbr": "_TC",
            "industry": "Manufacturing",
            "country": "India",
            "fy_start_date": f"{year}-01-01",
            "fy_end_date": f"{year}-12-31",
            "language": "english",
            "company_tagline": "Testing",
            "email": "test@erpnext.com",
            "password": "test",
            "chart_of_accounts": "Standard",
        }
    )


def upload_test_file(file_name: str) -> str:
    """Upload an image from desk/src/assets/images/ as a standalone private File, returning its name."""
    file_path = frappe.get_app_path(
        "helpdesk", "..", "desk", "src", "assets", "images", file_name
    )
    with open(file_path, "rb") as f:
        content = f.read()
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "is_private": 1,
            "content": content,
        }
    ).insert(ignore_permissions=True)
    return file_doc.name


def create_agent_manager(email: str):
    """Create (or fetch) an agent that also has the Agent Manager role."""
    create_agent(email)
    user = frappe.get_doc("User", email)
    if "Agent Manager" not in frappe.get_roles(email):
        user.add_roles("Agent Manager")
    return user


def make_task_project(project_name: str = "Test Task Project"):
    """Create (or fetch) an HD Task Project and return its name."""
    if frappe.db.exists("HD Task Project", project_name):
        return project_name
    return (
        frappe.get_doc({"doctype": "HD Task Project", "project_name": project_name})
        .insert(ignore_permissions=True)
        .name
    )


def make_task(subject: str = "Test Task", **kwargs):
    """Insert an HD Task as the current user, bypassing permission checks.
    Pass checklist=[{"item": ..., "done": ...}] for checklist rows."""
    return frappe.get_doc({"doctype": "HD Task", "subject": subject, **kwargs}).insert(
        ignore_permissions=True
    )


def make_task_milestone(project: str, milestone_name: str = "Test Milestone"):
    """Create an HD Task Milestone under `project` and return its name."""
    return (
        frappe.get_doc(
            {
                "doctype": "HD Task Milestone",
                "milestone_name": milestone_name,
                "project": project,
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


def make_task_freelancer(freelancer_name: str = "Test Freelancer"):
    """Create (or fetch) an HD Task Freelancer and return its name."""
    if frappe.db.exists("HD Task Freelancer", freelancer_name):
        return freelancer_name
    return (
        frappe.get_doc({"doctype": "HD Task Freelancer", "freelancer_name": freelancer_name})
        .insert(ignore_permissions=True)
        .name
    )


def make_plain_user(email: str):
    """Create (or fetch) an enabled user with no Helpdesk role, to test that task APIs reject non-agents."""
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": email.split("@")[0],
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
    return frappe.get_doc("User", email)


class FakeResponse:
    """Minimal stand-in for requests.Response, used by mock_external_api."""

    def __init__(self, body=None, status_code: int = 200, headers: dict | None = None):
        self.body = body
        self.status_code = status_code
        self.headers = headers or {}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self.body is _INVALID_JSON:
            raise ValueError("not json")
        return self.body


_INVALID_JSON = object()
INVALID_JSON = FakeResponse(_INVALID_JSON)
# Dummy values only; they exist so the clients see a configured integration.
FAKE_EXTERNAL_CONFIG = {
    "HRMS_API_BASE_URL": "http://hrms.invalid",
    "HRMS_API_KEY": "test-hrms-key",
    "PBT_API_BASE_URL": "http://pbt.invalid",
    "PBT_API_KEY": "test-pbt-key",
}


@contextmanager
def mock_external_api(handler, config: dict | None = None):
    """Route every HRMS / PBT request to `handler(url, params, headers)` instead of the network.

    The handler returns a FakeResponse or raises a requests exception. Yields the list of
    (url, params, headers) calls made. `config` replaces the dummy API settings, e.g. {} for
    an unconfigured integration. Retry sleeps are skipped."""
    calls = []

    def fake_get(url, params=None, headers=None, **kwargs):
        calls.append((url, params or {}, headers or {}))
        return handler(url, params or {}, headers or {})

    settings = FAKE_EXTERNAL_CONFIG if config is None else config
    cleared = {k: "" for k in FAKE_EXTERNAL_CONFIG}
    with (
        patch.dict(os.environ, {**cleared, **settings}),
        patch("helpdesk.integrations.external.client.requests.get", fake_get),
        patch("helpdesk.integrations.external.client.time.sleep"),
    ):
        yield calls


def pbt_project(project_id: str = "P-1", project_name: str = "Test PBT Project", **extra):
    """One PBT project row shaped like the documented API, with every field present."""
    return {
        "project_id": project_id,
        "project_name": project_name,
        "client_id": "C-1",
        "client_name": "Test Client",
        "status": "development",
        "status_display": "Development",
        "project_type": "web",
        "project_type_display": "Web",
        "engagement_type": "fixed",
        "engagement_type_display": "Fixed",
        "start_date": "2026-01-01",
        "end_date": None,
        "project_manager_name": None,
        **extra,
    }


def pbt_page(results: list, page: int = 1, total_pages: int = 1, count: int | None = None):
    """A PBT list response in the documented envelope."""
    return FakeResponse(
        {
            "status": "success",
            "message": "Projects retrieved.",
            "data": {
                "count": len(results) if count is None else count,
                "page": page,
                "page_size": len(results),
                "total_pages": total_pages,
                "results": results,
            },
        }
    )


def pbt_milestone(milestone_id="M-1", milestone_name: str = "Test Milestone", **extra):
    """One PBT milestone row shaped like the live API (ids arrive as integers there)."""
    return {
        "milestone_id": milestone_id,
        "milestone_name": milestone_name,
        "sequence": 1,
        "status": "not_started",
        "status_display": "Not Started",
        "start_date": "2026-09-15",
        "end_date": "2026-10-23",
        "completion_percent": 0,
        "updated_at": "2026-10-20T10:15:00Z",
        **extra,
    }


def pbt_milestone_page(results: list, project_id="P-1", page: int = 1, total_pages: int = 1):
    """A PBT milestones response in the live envelope."""
    return FakeResponse(
        {
            "status": "success",
            "message": "Milestones retrieved.",
            "data": {
                "project_id": project_id,
                "project_name": "Test PBT Project",
                "count": len(results),
                "page": page,
                "page_size": 100,
                "total_pages": total_pages,
                "results": results,
            },
        }
    )


def pbt_resource(assignment_id="A-1", resource_type: str = "employee", resource_code="E-1", **extra):
    """One PBT resource assignment row shaped like the live API (ids arrive as integers there)."""
    return {
        "assignment_id": assignment_id,
        "resource_type": resource_type,
        "resource_type_display": resource_type.title(),
        "resource_code": resource_code,
        "resource_name": "Test Resource",
        "role": "Developer",
        "milestone_id": None,
        "milestone_name": None,
        "start_date": "2026-09-15",
        "end_date": None,
        "allocation_percent": 100,
        "status": "active",
        "status_display": "Active",
        "updated_at": "2026-10-20T10:15:00Z",
        **extra,
    }


def pbt_routes(projects: list, milestones: dict, resources: dict | None = None):
    """mock_external_api handler for PBT. The project list serves `projects`;
    /projects/<id>/milestones/ serves `milestones[id]`; /projects/<id>/resources/ serves
    `resources[id]`, narrowed by `milestone_id` like PBT (404 when that milestone is not in
    `milestones[id]`). A project id that is not a key of `milestones` is a 404."""
    resources = resources or {}
    not_found = {"status": "error", "message": "Project not found.", "data": None}

    def handler(url, params, headers):
        assert url.startswith("http://pbt.invalid"), url
        if "/milestones/" not in url and "/resources/" not in url:
            return pbt_page(projects)
        project_id = url.rstrip("/").split("/")[-2]
        if project_id not in milestones:
            return FakeResponse(not_found, 404)
        if "/milestones/" in url:
            return pbt_milestone_page(milestones[project_id], project_id)
        rows = resources.get(project_id, [])
        if milestone_id := params.get("milestone_id"):
            if milestone_id not in {str(m["milestone_id"]) for m in milestones[project_id]}:
                return FakeResponse({**not_found, "message": "Milestone not found in this project."}, 404)
            rows = [r for r in rows if str(r.get("milestone_id")) == milestone_id]
        return pbt_milestone_page(rows, project_id)

    return handler


def pbt_resources_with_hrms(rows: list, employee: dict | None = None, hrms_status: int = 200):
    """mock_external_api handler: PBT knows project "5" with milestone 17 ("M1") and serves `rows`
    as its resources; every HRMS request answers `hrms_status` with `employee` as the detail body."""
    pbt_handler = pbt_routes([pbt_project("5")], {"5": [pbt_milestone(17, "M1")]}, {"5": rows})

    def handler(url, params, headers):
        if url.startswith("http://pbt.invalid"):
            return pbt_handler(url, params, headers)
        return FakeResponse(employee, status_code=hrms_status)

    return handler


PBT_INBOUND_TEST_KEYS = "test-inbound-old,test-inbound-new"


def call_pbt_inbound(key: str | None, keys: str = PBT_INBOUND_TEST_KEYS, **params) -> tuple[int, dict]:
    """Call helpdesk.api.pbt_inbound.get_tasks as PBT would: `key` as the X-API-Key header, `keys`
    as the configured PBT_INBOUND_API_KEYS. Returns (HTTP status, decoded JSON body)."""
    from helpdesk.api.pbt_inbound import get_tasks

    headers = {"X-API-Key": key} if key is not None else {}
    with (
        patch.dict(os.environ, {"PBT_INBOUND_API_KEYS": keys}),
        patch("helpdesk.api.pbt_inbound.frappe.get_request_header", lambda name, default=None: headers.get(name, default)),
    ):
        response = get_tasks(**params)
    return response.status_code, json.loads(response.get_data(as_text=True))


def hrms_employee(
    employee_id: str = "E-1",
    employee_name: str = "Test Employee",
    email: str | None = "test.employee@example.com",
    department: str | None = "Engineering",
    designation: str | None = "Developer",
):
    """One HRMS employee row. The live API sends `full_name`; `employee_name` is the first
    FIELD_CANDIDATES fallback, so both shapes normalize the same way."""
    return {
        "employee_id": employee_id,
        "employee_name": employee_name,
        "email": email,
        "department": department,
        "designation": designation,
    }


def make_article(title: str = "Test Article", status: str = "Published", content: str = "<p>Test content</p>"):
    """Insert an HD Article and return its name. Published articles need content."""
    return frappe.get_doc(
        {"doctype": "HD Article", "title": title, "status": status, "content": content}
    ).insert(ignore_permissions=True).name
