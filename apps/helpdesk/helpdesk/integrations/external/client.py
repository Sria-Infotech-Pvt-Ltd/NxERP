import os
import time

import frappe
import requests
from frappe import _

CONNECT_TIMEOUT = 3
READ_TIMEOUT = 10
MAX_RETRY_WAIT = 5


class ExternalAPIError(Exception):
    """An external API call failed. `message` is safe to show to a user: it never contains
    the request URL, the API key or the upstream response body."""

    def __init__(
        self,
        message: str,
        status: int | None = None,
        retry_after: int | None = None,
        http_status: int = 502,
    ):
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after
        # What our own API answers with, not what the upstream said.
        self.http_status = http_status


def get_setting(name: str) -> str:
    """Environment first, then site_config.json. Secrets are only ever read here."""
    return (os.environ.get(name) or frappe.conf.get(name) or "").strip()


def get_json(service: str, base_url_name: str, key_name: str, path: str, params: dict | None = None):
    """GET `path` from an external API and return the decoded JSON body.

    Each service passes its own variable names, so the two integrations never share a
    key. One retry is made on HTTP 429 when the server asks for a short wait."""
    base_url = get_setting(base_url_name).rstrip("/")
    api_key = get_setting(key_name)
    if not base_url or not api_key:
        raise ExternalAPIError(_("{0} integration is not configured").format(service))

    for attempt in (1, 2):
        try:
            response = requests.get(
                f"{base_url}{path}",
                params={k: v for k, v in (params or {}).items() if v not in (None, "")},
                headers={"X-API-Key": api_key, "Accept": "application/json"},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                # verify stays at the requests default (certificate checking on)
            )
        except requests.exceptions.Timeout:
            raise ExternalAPIError(
                _("{0} did not respond in time").format(service), http_status=504
            ) from None
        except requests.exceptions.RequestException:
            raise ExternalAPIError(_("{0} is unavailable").format(service), http_status=503) from None

        if response.status_code == 429:
            retry_after = parse_retry_after(response)
            if attempt == 1 and retry_after is not None and retry_after <= MAX_RETRY_WAIT:
                time.sleep(retry_after)
                continue
            raise ExternalAPIError(
                _("{0} is rate limiting requests, try again shortly").format(service),
                status=429,
                retry_after=retry_after,
                http_status=503,
            )
        break

    if response.status_code in (401, 403):
        raise ExternalAPIError(_("{0} rejected the configured API key").format(service), status=response.status_code)
    if response.status_code == 400:
        raise ExternalAPIError(_("{0} rejected the request").format(service), status=400)
    if not response.ok:
        raise ExternalAPIError(_("{0} returned an error").format(service), status=response.status_code)

    try:
        return response.json()
    except ValueError:
        raise ExternalAPIError(_("{0} returned an invalid response").format(service)) from None


def parse_retry_after(response) -> int | None:
    # UNVERIFIED: the contract names `retry_after_seconds` but not where it sits, so the
    # body (top level, then inside `data`) and the standard Retry-After header are tried.
    candidates = []
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        data = body.get("data")
        candidates += [body.get("retry_after_seconds"), data.get("retry_after_seconds") if isinstance(data, dict) else None]
    candidates.append(response.headers.get("Retry-After"))
    for value in candidates:
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError):
            continue
    return None
