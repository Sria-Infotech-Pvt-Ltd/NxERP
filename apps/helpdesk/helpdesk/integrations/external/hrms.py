"""HRMS employee client. Read-only.

UNVERIFIED: only the two URLs and the X-API-Key header are known. The response body has not
been seen yet (the server was unreachable), so every field name below is a guess kept in
FIELD_CANDIDATES and LIST_KEYS. Correct those two once a real response is available.
"""

from frappe import _

from helpdesk.integrations.external.client import ExternalAPIError, get_json

SERVICE = "HRMS"
BASE_URL = "HRMS_API_BASE_URL"
API_KEY = "HRMS_API_KEY"
LIST_PATH = "/api/external/employees/"
DETAIL_PATH = "/api/external/employees/{employee_id}/"

# UNVERIFIED: the first key present wins.
FIELD_CANDIDATES = {
    "employee_id": ("employee_id", "id", "name"),
    "employee_name": ("employee_name", "full_name", "name"),
    "email": ("email", "work_email", "company_email", "user_id"),
    "department": ("department", "department_name"),
    "designation": ("designation", "designation_name"),
}
# UNVERIFIED: wrappers a list or detail body may use.
LIST_KEYS = ("results", "data", "employees")
PAGE_SIZE = 100
# Guards against an upstream that never stops reporting more pages.
MAX_PAGES = 50


def get_employees() -> list[dict]:
    """Every active employee, following `total_pages` (the first page alone is not the whole list)."""
    employees, page = [], 1
    while page <= MAX_PAGES:
        body = get_json(SERVICE, BASE_URL, API_KEY, LIST_PATH, {"page": page, "page_size": PAGE_SIZE})
        rows = [r for r in extract_list(body) if not (isinstance(r, dict) and r.get("is_active") is False)]
        employees += [e for e in (normalize_employee(r) for r in rows) if e]
        if page >= total_pages(body):
            break
        page += 1
    return employees


def total_pages(body) -> int:
    data = body.get("data") if isinstance(body, dict) else None
    for source in (data, body):
        if isinstance(source, dict) and isinstance(source.get("total_pages"), int):
            return source["total_pages"]
    return 1


def get_employee(employee_id: str) -> dict | None:
    employee_id = str(employee_id or "").strip()
    # The id becomes part of a URL path, so only a plain token is allowed.
    if (
        not employee_id
        or employee_id in (".", "..")
        or not all(c.isalnum() or c in "-_." for c in employee_id)
    ):
        raise ExternalAPIError(_("Invalid employee id"))
    body = get_json(SERVICE, BASE_URL, API_KEY, DETAIL_PATH.format(employee_id=employee_id))
    if isinstance(body, dict):
        for key in ("data", "employee"):
            if isinstance(body.get(key), dict):
                body = body[key]
                break
    employee = normalize_employee(body)
    # An answer for some other id must not be accepted as the requested employee.
    return employee if employee and employee["employee_id"] == employee_id else None


def extract_list(body) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in LIST_KEYS:
            value = body.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for inner in LIST_KEYS:
                    if isinstance(value.get(inner), list):
                        return value[inner]
    raise ExternalAPIError(_("{0} returned an invalid response").format(SERVICE))


def normalize_employee(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    out = {field: first_value(raw, keys) for field, keys in FIELD_CANDIDATES.items()}
    if not out["employee_id"] or not out["employee_name"]:
        return None
    email = out["email"]
    out["email"] = email.lower() if email and "@" in email else None
    return out


def first_value(raw: dict, keys: tuple[str, ...]):
    for key in keys:
        value = raw.get(key)
        if isinstance(value, dict):  # a nested {"name": ...} object
            value = value.get("name")
        if value not in (None, ""):
            return str(value).strip()
    return None
