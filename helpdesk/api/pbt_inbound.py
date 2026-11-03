"""Read-only API the Project Budgeting Tool (PBT) calls to fetch the Help Desk tasks of its projects.

The mirror of PBT's own external API: an `X-API-Key` header checked against PBT_INBOUND_API_KEYS
(comma-separated, so a key can be rotated), and PBT's response envelope
{"status", "message", "data": {..., "count", "page", "page_size", "total_pages", "results"}}.
"""

import hmac
import json
import math

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import get_datetime, get_system_timezone, get_url
from werkzeug.wrappers import Response

from helpdesk.integrations.external.client import ExternalAPIError, get_setting
from helpdesk.integrations.external.pbt import plain_id

DOCTYPE = "HD Task"
INBOUND_KEYS = "PBT_INBOUND_API_KEYS"
STATUSES = ("Planned", "In Progress", "In Review", "Completed", "Blocked", "Cancelled")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
FIELDS = [
    "name",
    "subject",
    "status",
    "priority",
    "progress",
    "pbt_project_id",
    "pbt_project_name",
    "pbt_milestone_id",
    "pbt_milestone_name",
    "pbt_assignment_id",
    "pbt_resource_type",
    "pbt_resource_code",
    "pbt_resource_name",
    "hrms_employee_id",
    "hrms_employee_name",
    "start_date",
    "due_date",
    "completed_on",
    "creation",
    "modified",
]


class BadRequest(Exception):
    """A filter PBT sent is invalid; the message is safe to return."""


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def get_tasks(
    project_id: str | None = None,
    milestone_id: str | None = None,
    status: str | None = None,
    updated_since: str | None = None,
    page: int | str = 1,
    page_size: int | str = DEFAULT_PAGE_SIZE,
):
    """Tasks linked to a PBT project (every PBT project when `project_id` is omitted), oldest
    change first so `updated_since` + paging is a stable sync. Answers 401 on a missing or wrong key."""
    if not is_valid_key(frappe.get_request_header("X-API-Key")):
        return envelope(401, _("Invalid or inactive API key."))
    try:
        filters = task_filters(project_id, milestone_id, status, updated_since)
        page, page_size = paging(page, page_size)
    except BadRequest as e:
        return envelope(400, str(e))

    count = frappe.db.count(DOCTYPE, filters)
    rows = frappe.qb.get_query(
        DOCTYPE,
        fields=FIELDS,
        filters=filters,
        order_by="modified asc",
        limit=page_size,
        offset=(page - 1) * page_size,
    ).run(as_dict=True)
    return envelope(
        200,
        _("Tasks retrieved."),
        {
            "project_id": project_id or None,
            "time_zone": get_system_timezone(),
            "count": count,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, math.ceil(count / page_size)),
            "results": [task_row(row) for row in rows],
        },
    )


def is_valid_key(key: str | None) -> bool:
    keys = [k.strip() for k in get_setting(INBOUND_KEYS).split(",") if k.strip()]
    # Every key is compared, in constant time, so the answer time does not reveal a near match.
    return bool(key) and any([hmac.compare_digest(key.encode(), k.encode()) for k in keys])


def task_filters(project_id, milestone_id, status, updated_since) -> list[list]:
    filters = [["pbt_project_id", "is", "set"]]
    try:
        if project_id not in (None, ""):
            filters.append(["pbt_project_id", "=", plain_id(project_id, _("Invalid project_id"))])
        if milestone_id not in (None, ""):
            filters.append(["pbt_milestone_id", "=", plain_id(milestone_id, _("Invalid milestone_id"))])
    except ExternalAPIError as e:
        raise BadRequest(e.message) from None
    if status:
        statuses = [s.strip() for s in status.split(",")]
        if any(s not in STATUSES for s in statuses):
            raise BadRequest(_("status must be one or more (comma-separated) of: {0}").format(", ".join(STATUSES)))
        filters.append(["status", "in", statuses])
    if updated_since:
        try:
            filters.append(["modified", ">=", get_datetime(updated_since)])
        except Exception:
            raise BadRequest(_("updated_since must be an ISO date or date-time")) from None
    return filters


def paging(page, page_size) -> tuple[int, int]:
    try:
        page, page_size = int(page), int(page_size)
    except (TypeError, ValueError):
        raise BadRequest(_("page and page_size must be whole numbers")) from None
    if page < 1 or page_size < 1:
        raise BadRequest(_("page and page_size must be 1 or more"))
    return page, min(page_size, MAX_PAGE_SIZE)


def task_row(row) -> dict:
    return {
        "task_id": row.name,
        "subject": row.subject,
        "status": row.status,
        "priority": row.priority,
        "progress": row.progress,
        "project_id": row.pbt_project_id,
        "project_name": row.pbt_project_name,
        "milestone_id": row.pbt_milestone_id,
        "milestone_name": row.pbt_milestone_name,
        "assignment_id": row.pbt_assignment_id,
        "resource_type": row.pbt_resource_type,
        "resource_code": row.pbt_resource_code,
        "resource_name": row.pbt_resource_name,
        "hrms_employee_id": row.hrms_employee_id,
        "hrms_employee_name": row.hrms_employee_name,
        "start_date": row.start_date,
        "end_date": row.due_date,
        "completed_on": row.completed_on,
        "created_at": row.creation,
        "updated_at": row.modified,
        "url": get_url(f"/helpdesk/tasks/{row.name}"),
    }


def envelope(status_code: int, message: str, data=None) -> Response:
    """PBT's envelope, returned as-is (a Response is not wrapped in Frappe's {"message": ...})."""
    body = {"status": "success" if status_code < 400 else "error", "message": message, "data": data}
    return Response(
        json.dumps(body, default=json_value),
        status=status_code,
        mimetype="application/json",
    )


def json_value(value):
    # Dates and date-times as ISO 8601, in the Help Desk time zone reported as data.time_zone.
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
