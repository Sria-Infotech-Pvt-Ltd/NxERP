"""Project Budgeting Tool (PBT) client. Read-only; projects are never copied into HD Task Project.

Response envelope (from the integration contract, not yet checked against the live server):
    {"status": "success", "message": "...", "data": {"count", "page", "page_size", "total_pages", "results": []}}
"""

from frappe import _

from helpdesk.integrations.external.client import ExternalAPIError, get_json

SERVICE = "PBT"
BASE_URL = "PBT_API_BASE_URL"
API_KEY = "PBT_API_KEY"
PROJECTS_PATH = "/api/v1/projects/"
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
