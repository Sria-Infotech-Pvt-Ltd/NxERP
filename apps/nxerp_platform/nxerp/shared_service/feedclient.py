"""HTTP client for an owner's feed API (docs/architecture/feed-api-v1.md). Standard library only; no frappe.

Timeouts: connect 3 seconds, read 20 seconds. Two failure classes tell the caller what to do:

- `FeedUnavailable`: a network error, a timeout, a 5xx or a 429. Back off and try again; nothing about the request is wrong.
- `FeedRejected`: any other error status (a wrong key is 401, a missing role 403, a bad argument 422). Do not retry in a loop:
  stop that source and alert, so a wrong key cannot spin.

The key is sent as `Authorization: token key:secret` and is never logged or put in an error message.
"""

import http.client
import json
import ssl
import urllib.parse

from nxerp.shared_service.config import Source

CONNECT_TIMEOUT = 3
READ_TIMEOUT = 20
METHOD_PREFIX = "/api/method/nxerp.shared.feed."


class FeedUnavailable(RuntimeError):
	"""Network error, timeout, 5xx or 429: retry later."""


class FeedRejected(RuntimeError):
	"""The owner refused the request (4xx other than 429): do not retry in a loop."""

	def __init__(self, status: int, error_type: str | None, message: str = ""):
		super().__init__(
			f"the feed answered HTTP {status} ({error_type or 'no error type'}){': ' + message if message else ''}"
		)
		self.status = status
		self.error_type = error_type


class FeedClient:
	def __init__(
		self,
		source: Source,
		key: str,
		connect_timeout: float = CONNECT_TIMEOUT,
		read_timeout: float = READ_TIMEOUT,
	):
		self.source = source
		self._key = key
		self.connect_timeout = connect_timeout
		self.read_timeout = read_timeout
		parts = urllib.parse.urlsplit(source.base_url)
		self._https = parts.scheme == "https"
		self._host = parts.hostname
		self._port = parts.port or (443 if self._https else 80)

	def _connection(self):
		if self._https:
			return http.client.HTTPSConnection(
				self._host, self._port, timeout=self.connect_timeout, context=ssl.create_default_context()
			)
		return http.client.HTTPConnection(self._host, self._port, timeout=self.connect_timeout)

	def _request(self, http_method: str, method: str, params: dict | None = None):
		params = {k: v for k, v in (params or {}).items() if v is not None}
		query = urllib.parse.urlencode(params)
		headers = {"Authorization": f"token {self._key}", "Accept": "application/json"}
		if self.source.host_header:
			headers["Host"] = self.source.host_header
		path = METHOD_PREFIX + method
		body = None
		if http_method == "GET":
			if query:
				path += "?" + query
		else:
			body = query
			headers["Content-Type"] = "application/x-www-form-urlencoded"
		conn = self._connection()
		try:
			conn.connect()
			conn.sock.settimeout(self.read_timeout)  # connect used 3 s; reading may take 20 s
			conn.request(http_method, path, body=body, headers=headers)
			response = conn.getresponse()
			raw = response.read()
			status = response.status
		except (
			OSError,
			http.client.HTTPException,
		) as exc:  # OSError includes timeouts and refused connections
			raise FeedUnavailable(
				f"{type(exc).__name__} talking to the feed of {self.source.app_key}"
			) from exc
		finally:
			conn.close()
		try:
			data = json.loads(raw) if raw else {}
		except ValueError:
			data = {}
		if status == 200 and isinstance(data, dict) and "message" in data:
			return data["message"]
		if status >= 500 or status == 429:
			raise FeedUnavailable(f"the feed of {self.source.app_key} answered HTTP {status}")
		error_type = data.get("exc_type") if isinstance(data, dict) else None
		raise FeedRejected(status, error_type)

	def head(self) -> dict:
		return self._request("GET", "head")

	def pull(self, after_seq: int, limit: int = 500) -> dict:
		return self._request("GET", "pull", {"after_seq": after_seq, "limit": limit})

	def ack(self, through_seq: int) -> dict:
		return self._request("POST", "ack", {"through_seq": through_seq})

	def digest(
		self, entity_type: str, modified_since: str | None = None, after_id: str = "", limit: int = 500
	) -> dict:
		return self._request(
			"GET",
			"digest",
			{
				"entity_type": entity_type,
				"modified_since": modified_since,
				"after_id": after_id,
				"limit": limit,
			},
		)

	def snapshot(self, entity_type: str, after_id: str = "", limit: int = 500) -> dict:
		return self._request(
			"GET", "snapshot", {"entity_type": entity_type, "after_id": after_id, "limit": limit}
		)

	def snapshot_by_ids(self, entity_type: str, ids: list) -> dict:
		return self._request(
			"POST", "snapshot_by_ids", {"entity_type": entity_type, "ids": json.dumps(list(ids))}
		)
