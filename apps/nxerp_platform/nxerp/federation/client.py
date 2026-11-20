"""Server-to-server calls from the identity site to an app site's provisioning API (the app's `nxerp.federation.api`).

A call carries a service token (`Authorization: token <key>:<secret>`) and the app site's name (`X-Frappe-Site-Name`), uses a 5 second
timeout and at most 2 retries (only for connection errors and 502/503/504; every call is idempotent by `idempotency_key`).
Errors name the kind and an HTTP status only: never a header, a URL with credentials, or a response body.
"""

import frappe
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from nxerp.nxerp_platform.doctype.nxerp_peer.nxerp_peer import secret

TIMEOUT_SECONDS = 5
MAX_RETRIES = 2
API_PREFIX = "/api/method/nxerp.federation.api."


class PeerError(Exception):
	"""A call to an app site failed. `str(error)` is safe to store and log."""


def _session() -> requests.Session:
	session = requests.Session()
	retry = Retry(
		total=MAX_RETRIES,
		connect=MAX_RETRIES,
		read=0,  # a timeout after the request was sent is not retried here: the outbox retries it later with the same key
		status=MAX_RETRIES,
		status_forcelist=(502, 503, 504),
		allowed_methods=frozenset({"GET", "POST"}),
		backoff_factor=0.3,
		raise_on_status=False,
	)
	adapter = HTTPAdapter(max_retries=retry)
	session.mount("http://", adapter)
	session.mount("https://", adapter)
	return session


def call(peer: dict, method: str, name: str, *, params: dict | None = None, data: dict | None = None):
	"""Call `nxerp.federation.api.<name>` on the peer. `peer` has app_key, internal_url, site_name, api_key. Returns the `message`."""
	url = f"{peer['internal_url'].rstrip('/')}{API_PREFIX}{name}"
	headers = {
		"Authorization": f"token {peer['api_key']}:{secret(peer['app_key'])}",
		"X-Frappe-Site-Name": peer["site_name"],
		"Accept": "application/json",
	}
	try:
		response = _session().request(
			method,
			url,
			params=params,
			data=data,
			headers=headers,
			timeout=TIMEOUT_SECONDS,
			allow_redirects=False,
		)
	except requests.exceptions.Timeout as exc:
		raise PeerError("timeout") from exc
	except requests.exceptions.ConnectionError as exc:
		raise PeerError("connection failed") from exc
	except requests.exceptions.RequestException as exc:
		raise PeerError(type(exc).__name__) from exc

	if response.status_code in (401, 403):
		raise PeerError(f"HTTP {response.status_code} (the service token was refused)")
	if response.status_code != 200:
		raise PeerError(f"HTTP {response.status_code}")
	try:
		return response.json().get("message")
	except ValueError as exc:
		raise PeerError("answer is not JSON") from exc


def peer_for(app_key: str) -> dict | None:
	"""The enabled peer row as a dict (never the secrets), or None."""
	rows = frappe.get_all(
		"NXERP Peer",
		filters={"app_key": app_key, "enabled": 1},
		fields=["app_key", "internal_url", "site_name", "api_key", "origin"],
		limit=1,
	)
	return rows[0] if rows else None
