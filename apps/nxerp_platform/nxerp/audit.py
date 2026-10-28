"""Structured denial log. One JSON line per denial, no personal data and no secrets.

A user is recorded as a short salted hash (`user_ref`), never as an email or name; the record name of
a document is never logged, only the DocType; query strings and request bodies are never logged.
The hash lets an operator correlate repeated denials for one account without exposing who it is.
"""

import hashlib
import json

import frappe

LOGGER_NAME = "nxerp.access"


def user_ref(user: str | None) -> str:
	salt = frappe.local.site or ""
	digest = hashlib.sha256(f"{salt}:{user or ''}".encode()).hexdigest()
	return f"u:{digest[:10]}"


def _logger():
	return frappe.logger(LOGGER_NAME, allow_site=True, file_count=10)


def log_denial(surface: str, app_key: str | None, user: str | None, **detail):
	"""surface: desk | spa | api_method | api_resource | doc | query | discovery | resolver_error."""
	record = {
		"event": "nxerp.access.denied",
		"surface": surface,
		"app": app_key,
		"user_ref": user_ref(user),
		**{k: v for k, v in detail.items() if v is not None},
	}
	try:
		_logger().warning(json.dumps(record, sort_keys=True, default=str))
	except Exception:  # nosec B110
		# intentional: a logging failure must never turn a denial into an error
		pass
	return record
