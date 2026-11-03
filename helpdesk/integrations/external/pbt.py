"""Project Budgeting Tool (PBT) client. Read-only; projects, milestones and resources are never copied
into HD Task Project / HD Task Milestone / HD Task Freelancer.

Response envelope (from the integration contract, not yet checked against the live server):
    {"status": "success", "message": "...", "data": {"count", "page", "page_size", "total_pages", "results": []}}
"""

from frappe import _

from helpdesk.integrations.external.client import ExternalAPIError, get_json

SERVICE = "PBT"
BASE_URL = "PBT_API_BASE_URL"
API_KEY = "PBT_API_KEY"
PROJECTS_PATH = "/api/v1/projects/"
MILESTONES_PATH = "/api/v1/projects/{project_id}/milestones/"
RESOURCES_PATH = "/api/v1/projects/{project_id}/resources/"
PAGE_SIZE = 100
# Guards against an upstream that never stops reporting more pages.
MAX_PAGES = 50
STATUSES = (
    "planning",
    "development",
    "testing",
    "uat",
    "ready_for_deployment",
    "deployed",
    "on_hold",
)
MILESTONE_STATUSES = ("not_started", "in_progress", "completed", "on_hold", "cancelled")
RESOURCE_TYPES = ("employee", "freelancer", "vendor", "external")
RESOURCE_STATUSES = ("active", "completed", "on_hold", "removed")


def get_projects_page(
    search: str | None = None,
    status: str | None = None,
    client_id: str | None = None,
    project_id: str | None = None,
    updated_since: str | None = None,
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict:
    """One page of projects: {"count", "page", "page_size", "total_pages", "results"}."""
    if status and status not in STATUSES:
        raise ExternalAPIError(_("Unknown project status {0}").format(status))
    body = get_json(
        SERVICE,
        BASE_URL,
        API_KEY,
        PROJECTS_PATH,
        {
            "search": search,
            "status": status,
            "client_id": client_id,
            "project_id": project_id,
            "updated_since": updated_since,
            "page": page,
            "page_size": page_size,
        },
    )
    data = unwrap(body)
    results = data.get("results")
    if not isinstance(results, list):
        raise ExternalAPIError(_("{0} returned an invalid response").format(SERVICE))
    return {
        "count": data.get("count") or len(results),
        "page": data.get("page") or page,
        "page_size": data.get("page_size") or page_size,
        "total_pages": data.get("total_pages") or 1,
        "results": [p for p in (normalize_project(r) for r in results) if p],
    }


def get_all_projects(**filters) -> list[dict]:
    """Every project matching `filters`, following total_pages (page 1 is not assumed complete)."""
    projects, page = [], 1
    while page <= MAX_PAGES:
        result = get_projects_page(page=page, **filters)
        projects += result["results"]
        if page >= result["total_pages"]:
            break
        page += 1
    return projects


def get_project(project_id: str) -> dict | None:
    """The project whose id is exactly `project_id`, or None. The contract has no detail endpoint."""
    project_id = str(project_id)
    result = get_projects_page(project_id=project_id)
    return next((p for p in result["results"] if p["project_id"] == project_id), None)


def get_milestones(project_id: str, status: str | None = None) -> list[dict] | None:
    """Every active milestone of a project in PBT's order (all pages), or None when PBT does not
    know the project. Archived milestones are never returned by PBT. `status` is a comma-separated
    subset of MILESTONE_STATUSES."""
    project_id = plain_id(project_id, _("Invalid project id"))
    if status and any(s not in MILESTONE_STATUSES for s in status.split(",")):
        raise ExternalAPIError(_("Unknown milestone status {0}").format(status))
    return get_project_rows(MILESTONES_PATH.format(project_id=project_id), {"status": status}, normalize_milestone)


def get_milestone(project_id: str, milestone_id: str) -> dict | None:
    """The milestone `milestone_id` of `project_id`, or None. The API has no detail endpoint."""
    milestone_id = str(milestone_id)
    return next(
        (m for m in get_milestones(project_id) or [] if m["milestone_id"] == milestone_id), None
    )


def get_resources(
    project_id: str,
    milestone_id: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
) -> list[dict] | None:
    """Every resource assignment of a project (all pages), or None when PBT does not know the project
    or the milestone is not in it. Rows without a milestone come first; the same person appears once
    per assignment. PBT leaves out `removed` assignments unless `status` asks for them."""
    project_id = plain_id(project_id, _("Invalid project id"))
    if milestone_id not in (None, ""):
        milestone_id = plain_id(milestone_id, _("Invalid milestone id"))
    if resource_type and resource_type not in RESOURCE_TYPES:
        raise ExternalAPIError(_("Unknown resource type {0}").format(resource_type))
    if status and any(s not in RESOURCE_STATUSES for s in status.split(",")):
        raise ExternalAPIError(_("Unknown resource status {0}").format(status))
    return get_project_rows(
        RESOURCES_PATH.format(project_id=project_id),
        {"milestone_id": milestone_id, "resource_type": resource_type, "status": status},
        normalize_resource,
    )


def get_resource(project_id: str, assignment_id: str, milestone_id: str | None = None) -> dict | None:
    """The assignment `assignment_id` of `project_id` (on `milestone_id` when given), or None."""
    assignment_id = str(assignment_id)
    return next(
        (
            r
            for r in get_resources(project_id, milestone_id=milestone_id) or []
            if r["assignment_id"] == assignment_id
        ),
        None,
    )


def plain_id(value, error: str) -> str:
    """An id that goes into a URL path or query must be a plain token."""
    value = str(value or "").strip()
    if not value or not all(c.isalnum() or c in "-_" for c in value):
        raise ExternalAPIError(error)
    return value


def get_project_rows(path: str, params: dict, normalize) -> list[dict] | None:
    """Every page of a per-project list. PBT answers an unknown project (or a milestone outside it)
    with 404, returned as None; every other failure still raises."""
    rows, page = [], 1
    while page <= MAX_PAGES:
        try:
            body = get_json(SERVICE, BASE_URL, API_KEY, path, {**params, "page": page, "page_size": PAGE_SIZE})
        except ExternalAPIError as e:
            if e.status == 404:
                return None
            raise
        data = unwrap(body)
        results = data.get("results")
        if not isinstance(results, list):
            raise ExternalAPIError(_("{0} returned an invalid response").format(SERVICE))
        rows += [r for r in (normalize(raw) for raw in results) if r]
        if page >= (data.get("total_pages") or 1):
            break
        page += 1
    return rows


def unwrap(body) -> dict:
    if (
        not isinstance(body, dict)
        or body.get("status") != "success"
        or not isinstance(body.get("data"), dict)
    ):
        raise ExternalAPIError(_("{0} returned an invalid response").format(SERVICE))
    return body["data"]


def normalize_project(raw) -> dict | None:
    """Keep the documented fields; nullable ones become None. Rows without an id or name are dropped."""
    if (
        not isinstance(raw, dict)
        or raw.get("project_id") in (None, "")
        or not raw.get("project_name")
    ):
        return None
    return {
        "project_id": str(raw["project_id"]),
        "project_name": raw["project_name"],
        "client_id": raw.get("client_id"),
        "client_name": raw.get("client_name"),
        "status": raw.get("status"),
        "status_display": raw.get("status_display") or raw.get("status"),
        "project_type": raw.get("project_type"),
        "project_type_display": raw.get("project_type_display"),
        "engagement_type": raw.get("engagement_type"),
        "engagement_type_display": raw.get("engagement_type_display"),
        "start_date": raw.get("start_date"),
        "end_date": raw.get("end_date"),
        "project_manager_name": raw.get("project_manager_name"),
    }


def normalize_milestone(raw) -> dict | None:
    """Keep the documented fields; the id becomes a string like project_id. Rows without an id or name are dropped."""
    if (
        not isinstance(raw, dict)
        or raw.get("milestone_id") in (None, "")
        or not raw.get("milestone_name")
    ):
        return None
    return {
        "milestone_id": str(raw["milestone_id"]),
        "milestone_name": raw["milestone_name"],
        "sequence": raw.get("sequence"),
        "status": raw.get("status"),
        "status_display": raw.get("status_display") or raw.get("status"),
        "start_date": raw.get("start_date"),
        "end_date": raw.get("end_date"),
        "completion_percent": raw.get("completion_percent"),
    }


def normalize_resource(raw) -> dict | None:
    """Keep the documented fields; ids become strings. `resource_code` is the AIRA employee id for an
    employee (it can be missing in PBT), the freelancer code for a freelancer, None for external people.
    Rows without an assignment id, type or name are dropped."""
    if (
        not isinstance(raw, dict)
        or raw.get("assignment_id") in (None, "")
        or not raw.get("resource_type")
        or not raw.get("resource_name")
    ):
        return None
    milestone_id = raw.get("milestone_id")
    return {
        "assignment_id": str(raw["assignment_id"]),
        "resource_type": raw["resource_type"],
        "resource_type_display": raw.get("resource_type_display") or raw["resource_type"],
        "resource_code": raw.get("resource_code") or None,
        "resource_name": raw["resource_name"],
        "role": raw.get("role"),
        "milestone_id": None if milestone_id in (None, "") else str(milestone_id),
        "milestone_name": raw.get("milestone_name"),
        "start_date": raw.get("start_date"),
        "end_date": raw.get("end_date"),
        "allocation_percent": raw.get("allocation_percent"),
        "status": raw.get("status"),
        "status_display": raw.get("status_display") or raw.get("status"),
    }
