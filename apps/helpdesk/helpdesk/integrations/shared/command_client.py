"""Asks NXERP to change a customer or a contact through its command API (nxerp.shared.command.apply). Never writes another app's data.

POST {NXDESK_NXERP_URL}/api/method/nxerp.shared.command.apply, authenticated with a service user's API key and secret
(NXDESK_COMMAND_API_KEY, NXDESK_COMMAND_API_SECRET; environment first, then site config). One call per user action:

  * the `Idempotency-Key` (also sent as the `idempotency_key` field the API reads) is made once per user action and REUSED by every retry,
    here and from the browser, so a change is applied at most once however often the request is repeated;
  * the acting user's id is sent (the agent): NXERP applies its own permissions and validations as that person. No password or session;
  * `expected_version` is sent when the row's version is known;
  * a timeout, a connection error or a 5xx is retried once with the same key; any other failure is reported, never swallowed, and never
    applied locally: nothing changes in Helpdesk when NXERP refuses.
"""

import json
import uuid

import frappe
import requests

from helpdesk.integrations.external.client import get_setting

URL_NAME = "NXDESK_NXERP_URL"
KEY_NAME = "NXDESK_COMMAND_API_KEY"
SECRET_NAME = "NXDESK_COMMAND_API_SECRET"
SITE_NAME = "NXDESK_NXERP_SITE"  # optional: sent as X-Frappe-Site-Name when NXERP is called directly on its backend
CONNECT_TIMEOUT = 3
READ_TIMEOUT = 15
METHOD_PATH = "/api/method/nxerp.shared.command.apply"


class CommandFailed(Exception):
    """NXERP did not apply the command. `code` is the owner's error code (or a local one), `message` is safe to show an agent."""

    def __init__(self, code: str, message: str, http_status: int | None = None):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.http_status = code, message, http_status


def new_key() -> str:
    """A fresh idempotency key: one per user action."""
    return f"hd-{uuid.uuid4().hex}"


def apply(
    entity_type: str,
    entity_id: str,
    command: str,
    fields: dict,
    *,
    idempotency_key: str,
    acting_user: str | None = None,
    expected_version: str | None = None,
) -> dict:
    """Send one command. Returns {"ok": True, "source_modified": ...} or raises CommandFailed."""
    base = get_setting(URL_NAME).rstrip("/")
    key, secret = get_setting(KEY_NAME), get_setting(SECRET_NAME)
    if not base or not key or not secret:
        raise CommandFailed(
            "not_configured", "The NXERP command service is not configured"
        )
    if not idempotency_key:
        raise CommandFailed("bad_request", "An idempotency key is required")
    data = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "command": command,
        "fields": json.dumps(fields),
        "idempotency_key": idempotency_key,
        "acting_user": acting_user or frappe.session.user,
    }
    if expected_version:
        data["expected_version"] = expected_version
    headers = {
        "Authorization": f"token {key}:{secret}",
        "Idempotency-Key": idempotency_key,
        "Accept": "application/json",
    }
    if site := get_setting(SITE_NAME):
        headers["X-Frappe-Site-Name"] = site

    response = None
    for attempt in (1, 2):
        try:
            response = requests.post(
                f"{base}{METHOD_PATH}",
                data=data,
                headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            if attempt == 1:
                continue
            raise CommandFailed(
                "timeout",
                "NXERP did not answer in time; nothing was changed. Try again",
            ) from None
        except requests.exceptions.RequestException:
            if attempt == 1:
                continue
            raise CommandFailed(
                "unavailable",
                "NXERP is unavailable; nothing was changed. Try again later",
            ) from None
        if response.status_code >= 500 and attempt == 1:
            continue  # same key: a retry after a 5xx is safe on the owner's side
        break

    try:
        message = response.json().get("message")
    except ValueError:
        message = None
    if isinstance(message, dict) and message.get("error"):
        raise CommandFailed(
            str(message["error"]),
            str(message.get("message") or ""),
            response.status_code,
        )
    if response.status_code == 200 and isinstance(message, dict) and message.get("ok"):
        return message
    if response.status_code in (401, 403):
        raise CommandFailed(
            "forbidden", "NXERP refused the service credentials", response.status_code
        )
    raise CommandFailed(
        "unavailable",
        "NXERP gave no usable answer; nothing was changed",
        response.status_code,
    )
