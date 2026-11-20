"""Reads shared data (a customer, a contact) through the NXDESK Read API. Never SQL, never another app's tables.

GET {NXDESK_SHARED_API_URL}/v1/customer/{id} and /v1/contact/{id} with a per-app token (NXDESK_SHARED_API_TOKEN). Both settings come
from the environment first, then site config, like every external integration here (integrations/external/client.py get_setting).

  * timeouts: 2 s to connect, 3 s to read; one retry on HTTP 429 or a timeout;
  * a 60 second cache in Helpdesk's own Redis keyed by entity and id; the last good answer is kept 24 hours so that a Read API outage
    still shows the last known details;
  * the answer always says how fresh it is: `synced_at` (when the shared layer last wrote the row, which only moves when the row changes),
    `row_age_seconds`, and `stale`. DECISION: `stale` means the SHARED LAYER is behind, not that the row is old: the projector's lag is over
    5 minutes or the projector has reported no success for 5 minutes (read from /v1/metrics, cached 60 s), or the answer is the cached copy
    served because the Read API could not be reached. A customer nobody has touched for a month is not stale;
  * it never raises into a page: a failure is `{"data": None, "error": "<kind>"}` (or the cached copy with the error kind).

The shared layer is eventually consistent: after a command pass `min_version` (the `source_modified` the command returned) to wait for it.
"""

import time
from datetime import UTC, datetime

import frappe
import requests

from helpdesk.integrations.external.client import get_setting

URL_NAME = "NXDESK_SHARED_API_URL"
TOKEN_NAME = "NXDESK_SHARED_API_TOKEN"
CONNECT_TIMEOUT = 2
READ_TIMEOUT = 3
CACHE_SECONDS = 60
KEEP_SECONDS = 24 * 3600
STALE_AFTER_SECONDS = 300
MAX_RETRY_WAIT = 2
ENTITIES = ("customer", "contact")


class ReadFailed(Exception):
    """The Read API could not answer. `kind` is a short word safe to show: never a URL, a token or a response body."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def _retry_after(response) -> float:
    try:
        return max(
            0.0, min(float(response.headers.get("Retry-After", 1)), MAX_RETRY_WAIT)
        )
    except TypeError, ValueError:
        return 1.0


def _fetch(path: str, params: dict | None = None) -> dict:
    """One GET with one retry on 429 or a timeout. Returns the row; raises ReadFailed."""
    base = get_setting(URL_NAME).rstrip("/")
    token = get_setting(TOKEN_NAME)
    if not base or not token:
        raise ReadFailed("not_configured")
    response = None
    for attempt in (1, 2):
        try:
            response = requests.get(
                f"{base}{path}",
                params={k: v for k, v in (params or {}).items() if v not in (None, "")},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            if attempt == 1:
                continue
            raise ReadFailed("timeout") from None
        except requests.exceptions.RequestException:
            raise ReadFailed("unavailable") from None
        if response.status_code == 429 and attempt == 1:
            time.sleep(_retry_after(response))
            continue
        break
    status = response.status_code
    if status == 202:
        raise ReadFailed("pending")
    if status == 404:
        raise ReadFailed("not_found")
    if status in (401, 403):
        raise ReadFailed("denied")
    if status == 429:
        raise ReadFailed("rate_limited")
    if status != 200:
        raise ReadFailed("unavailable")
    try:
        row = response.json().get("data")
    except ValueError:
        raise ReadFailed("bad_answer") from None
    if not isinstance(row, dict):
        raise ReadFailed("bad_answer")
    return row


def _age_seconds(synced_at) -> float | None:
    """Seconds since the shared layer wrote the row. `synced_at` is UTC without a zone, as the Read API sends it."""
    try:
        written = datetime.strptime(
            str(synced_at)[:26], "%Y-%m-%d %H:%M:%S.%f"
        ).replace(tzinfo=UTC)
    except ValueError:
        try:
            written = datetime.strptime(
                str(synced_at)[:19], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=UTC)
        except ValueError:
            return None
    return (datetime.now(UTC) - written).total_seconds()


def _fetch_json(path: str) -> dict:
    """GET a Read API path whose answer is the whole JSON object (like /v1/metrics). Raises ReadFailed."""
    base = get_setting(URL_NAME).rstrip("/")
    token = get_setting(TOKEN_NAME)
    if not base or not token:
        raise ReadFailed("not_configured")
    try:
        response = requests.get(
            f"{base}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise ReadFailed("unavailable")
        body = response.json()
    except requests.exceptions.RequestException:
        raise ReadFailed("unavailable") from None
    except ValueError:
        raise ReadFailed("bad_answer") from None
    if not isinstance(body, dict):
        raise ReadFailed("bad_answer")
    return body


def layer_is_behind() -> bool | None:
    """True when the shared layer is behind (projector lag over 5 minutes, or no projector success for 5 minutes); None when unknown.

    Read from /v1/metrics and cached for CACHE_SECONDS, so a page does not call it twice."""
    key = "nxdesk_shared:health"
    cached = frappe.cache.get_value(key)
    if cached and time.time() - cached["fetched_at"] < CACHE_SECONDS:
        return cached["behind"]
    try:
        gauges = _fetch_json("/v1/metrics").get("projector") or {}
    except ReadFailed:
        return None
    lags = [v for k, v in gauges.items() if k.endswith(".lag_seconds")]
    successes = [v for k, v in gauges.items() if k.endswith(".last_success")]
    if not lags and not successes:
        behind = None
    else:
        behind = bool(
            (lags and max(lags) > STALE_AFTER_SECONDS)
            or (successes and time.time() - max(successes) > STALE_AFTER_SECONDS)
        )
    frappe.cache.set_value(
        key, {"behind": behind, "fetched_at": time.time()}, expires_in_sec=KEEP_SECONDS
    )
    return behind


def _result(
    row: dict | None,
    *,
    stale: bool = False,
    error: str | None = None,
    from_cache: bool = False,
    check_health: bool = False,
) -> dict:
    synced_at = row.get("synced_at") if row else None
    age = _age_seconds(synced_at) if row else None
    if row and not stale and check_health:
        stale = bool(layer_is_behind())
    return {
        "data": row,
        "synced_at": synced_at,
        "row_age_seconds": age,
        "stale": bool(stale),
        "error": error,
        "from_cache": from_cache,
    }


def get_entity(entity: str, entity_id: str, min_version: str | None = None) -> dict:
    """The row of a shared entity with its age: {"data", "synced_at", "stale", "error", "from_cache"}. Never raises."""
    if entity not in ENTITIES or not isinstance(entity_id, str) or not entity_id:
        return _result(None, error="bad_request")
    key = f"nxdesk_shared:{entity}:{entity_id}"
    cached = frappe.cache.get_value(key)
    if (
        cached
        and not min_version
        and time.time() - cached["fetched_at"] < CACHE_SECONDS
    ):
        return _result(cached["data"], from_cache=True, check_health=True)
    try:
        row = _fetch(f"/v1/{entity}/{entity_id}", {"min_version": min_version})
    except ReadFailed as failure:
        if cached:  # the last known details, flagged: better than nothing, and never presented as current
            return _result(
                cached["data"], stale=True, error=failure.kind, from_cache=True
            )
        return _result(None, error=failure.kind)
    frappe.cache.set_value(
        key, {"data": row, "fetched_at": time.time()}, expires_in_sec=KEEP_SECONDS
    )
    return _result(row, check_health=True)


def get_customer(customer_id: str, min_version: str | None = None) -> dict:
    return get_entity("customer", customer_id, min_version)


def get_contact(contact_id: str, min_version: str | None = None) -> dict:
    return get_entity("contact", contact_id, min_version)


def forget(entity: str, entity_id: str) -> None:
    """Drop the cached row (after a command, so the next read is fresh)."""
    frappe.cache.delete_value(f"nxdesk_shared:{entity}:{entity_id}")
