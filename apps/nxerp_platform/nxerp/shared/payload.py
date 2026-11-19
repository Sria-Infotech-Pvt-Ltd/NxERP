"""The canonical form and the hash of a contract payload. Pure Python: no frappe, no database.

The owner (`digest.py`, which builds a payload from a document) and the shared service (which rebuilds the same payload
from its own columns to compare) must produce byte-identical canonical JSON, or reconciliation would report drift for
every row. They therefore share this one module. Datetimes are `YYYY-MM-DD HH:MM:SS.ffffff`, dates `YYYY-MM-DD`, booleans 0 or 1.
"""

import hashlib
import json

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
DATE_FORMAT = "%Y-%m-%d"


def canonical_json(payload) -> str:
	return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_hash(payload) -> str:
	"""SHA-256 of the canonical JSON of a payload; reconciliation compares these, never values."""
	return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
