"""An in-process stand-in for an owner's feed API, for the shared-service tests. No frappe, no database.

It serves the six feed methods (`head`, `pull`, `ack`, `digest`, `snapshot`, `snapshot_by_ids`) over real HTTP on 127.0.0.1 with the
same shapes and error statuses as nxerp/shared/feed.py, and keeps the "owner's" documents and event log in memory. The test drives
the owner through `upsert`, `delete` (which write an event, like the capture hooks) and `bypass_change`, `bypass_delete` (which
change the owner's data WITHOUT an event, like `frappe.db.set_value`). Failures can be injected: server errors, a rejected key,
dropped acknowledgements, a skipped sequence number.
"""

import json
import threading
import urllib.parse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nxerp.shared import payload as payload_module
from nxerp.shared import registry

BASE_TIME = datetime(2026, 11, 18, 10, 0, 0)


class FakeOwner:
	def __init__(
		self,
		key: str = "feedkey123:feedsecret456",
		served: tuple = ("customer", "contact", "org_unit", "ticket_summary"),
	):
		self.key = key
		self.served = set(served)
		self.docs: dict = {}  # entity_type -> {id: {"payload": dict, "modified": str}}
		self.events: list = []
		self.next_seq = 1
		self._clock = 0
		self.acked = 0
		self.ack_calls: list = []
		self.pull_calls = 0
		self.head_age = 0
		self.fail_pulls = 0  # answer the next N pulls with HTTP 500
		self.drop_acks = 0  # answer the next N acks with HTTP 500
		self.force_status: int | None = None  # answer every request with this status
		self.last_host: str | None = None  # the Host header of the last request
		self.lock = threading.Lock()
		owner = self

		class Handler(BaseHTTPRequestHandler):
			def log_message(self, *args):  # silence
				pass

			def _send(self, status: int, body: dict):
				raw = json.dumps(body).encode()
				self.send_response(status)
				self.send_header("Content-Type", "application/json")
				self.send_header("Content-Length", str(len(raw)))
				self.end_headers()
				self.wfile.write(raw)

			def _handle(self, params: dict):
				method = self.path.split("?", 1)[0].rsplit(".", 1)[-1]
				owner.last_host = self.headers.get("Host")
				with owner.lock:
					status, body = owner.respond(self.headers.get("Authorization", ""), method, params)
				self._send(status, body)

			def do_GET(self):
				query = urllib.parse.urlsplit(self.path).query
				self._handle({k: v[0] for k, v in urllib.parse.parse_qs(query).items()})

			def do_POST(self):
				length = int(self.headers.get("Content-Length") or 0)
				form = urllib.parse.parse_qs(self.rfile.read(length).decode())
				self._handle({k: v[0] for k, v in form.items()})

		self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

	# ---- lifecycle ----

	def start(self) -> "FakeOwner":
		self._thread.start()
		return self

	def stop(self) -> None:
		self._server.shutdown()
		self._server.server_close()

	@property
	def base_url(self) -> str:
		return f"http://127.0.0.1:{self._server.server_address[1]}"

	# ---- the owner's side ----

	def stamp(self) -> str:
		self._clock += 1
		return (BASE_TIME + timedelta(seconds=self._clock)).strftime(payload_module.DATETIME_FORMAT)

	def payload_for(self, entity_type: str, **fields) -> dict:
		names = [f["shared"] for f in registry.get_contract(entity_type)["fields"]]
		unknown = set(fields) - set(names)
		if unknown:
			raise ValueError(f"not contract fields: {unknown}")
		return {name: fields.get(name) for name in names}

	def _event(self, entity_type, entity_id, op, payload, modified, **overrides) -> dict:
		contract = registry.get_contract(entity_type)
		tenant = contract["tenant"]
		event = {
			"event_id": f"evt-{self.next_seq:06d}",
			"seq": self.next_seq,
			"source_app": contract["owner_app"],
			"entity_type": entity_type,
			"entity_id": entity_id,
			"op": op,
			"contract_version": contract["contract_version"],
			"source_modified": modified,
			"tenant_id": tenant["value"] if tenant["mode"] == "constant" else entity_id,
			"payload": payload,
		}
		event.update(overrides)
		self.next_seq += 1
		self.events.append(event)
		return event

	def upsert(self, entity_type, entity_id, modified=None, **fields) -> dict:
		with self.lock:
			modified = modified or self.stamp()
			payload = self.payload_for(entity_type, **fields)
			self.docs.setdefault(entity_type, {})[entity_id] = {"payload": payload, "modified": modified}
			return self._event(entity_type, entity_id, "upsert", payload, modified)

	def delete(self, entity_type, entity_id, modified=None) -> dict:
		with self.lock:
			self.docs.get(entity_type, {}).pop(entity_id, None)
			return self._event(entity_type, entity_id, "delete", None, modified or self.stamp())

	def add_event(self, entity_type, entity_id, op, payload, modified, **overrides) -> dict:
		"""An event with exactly this content and no change to the owner's documents (for crafted orders and bad payloads)."""
		with self.lock:
			return self._event(entity_type, entity_id, op, payload, modified, **overrides)

	def resync(self, entity_type, entity_id) -> dict:
		with self.lock:
			return self._event(entity_type, entity_id, "resync", None, self.stamp())

	def skip_seq(self, count: int = 1) -> None:
		"""Use up sequence numbers without publishing them: the next event leaves a gap."""
		with self.lock:
			self.next_seq += count

	def bypass_change(self, entity_type, entity_id, keep_modified=True, **fields) -> None:
		"""Change a document without an event (like frappe.db.set_value). With keep_modified the version stamp does not move."""
		with self.lock:
			doc = self.docs[entity_type][entity_id]
			doc["payload"] = {**doc["payload"], **fields}
			if not keep_modified:
				doc["modified"] = self.stamp()

	def bypass_delete(self, entity_type, entity_id) -> None:
		with self.lock:
			self.docs[entity_type].pop(entity_id, None)

	def bypass_create(self, entity_type, entity_id, **fields) -> None:
		with self.lock:
			self.docs.setdefault(entity_type, {})[entity_id] = {
				"payload": self.payload_for(entity_type, **fields),
				"modified": self.stamp(),
			}

	# ---- the feed API ----

	def respond(self, authorization: str, method: str, params: dict) -> tuple:
		if self.force_status:
			return self.force_status, {"exc_type": "ForcedError"}
		if authorization != f"token {self.key}":
			return (
				(401, {"exc_type": "AuthenticationError"})
				if authorization.startswith("token ")
				else (403, {"exc_type": "PermissionError"})
			)
		handler = getattr(self, f"_feed_{method}", None)
		if handler is None:
			return 404, {"exc_type": "DoesNotExistError"}
		try:
			return 200, {"message": handler(params)}
		except _Refused as exc:
			return exc.status, {"exc_type": exc.error_type}

	def _entity(self, params) -> str:
		entity_type = params.get("entity_type")
		if entity_type not in self.served:
			raise _Refused(422, "FeedError")
		return entity_type

	def _feed_head(self, params):
		return {
			"max_seq": self.events[-1]["seq"] if self.events else 0,
			"pending_count": 0,
			"oldest_pending_age_seconds": self.head_age,
			"acked_through": self.acked,
		}

	def _feed_pull(self, params):
		self.pull_calls += 1
		if self.fail_pulls > 0:
			self.fail_pulls -= 1
			raise _Refused(500, "InternalError")
		after, limit = int(params.get("after_seq", 0)), int(params.get("limit", 1000))
		events = [e for e in self.events if e["seq"] > after][:limit]
		return {"events": events, "next_seq": events[-1]["seq"] if events else after}

	def _feed_ack(self, params):
		self.ack_calls.append(int(params["through_seq"]))
		if self.drop_acks > 0:
			self.drop_acks -= 1
			raise _Refused(500, "InternalError")
		through = int(params["through_seq"])
		changed = through - self.acked if through > self.acked else 0
		self.acked = max(self.acked, through)
		return {"acked_through": self.acked, "acked": changed}

	def _page(self, entity_type, params):
		after, limit = params.get("after_id", ""), int(params.get("limit", 500))
		since = params.get("modified_since")
		ids = sorted(i for i in self.docs.get(entity_type, {}) if i > after)
		if since:
			ids = [i for i in ids if self.docs[entity_type][i]["modified"] >= since]
		return ids[:limit], limit

	def _feed_digest(self, params):
		entity_type = self._entity(params)
		ids, limit = self._page(entity_type, params)
		items = [
			{
				"entity_id": i,
				"source_modified": self.docs[entity_type][i]["modified"],
				"deleted": 0,
				"payload_hash": payload_module.payload_hash(self.docs[entity_type][i]["payload"]),
			}
			for i in ids
		]
		return {"items": items, "next_after_id": items[-1]["entity_id"] if len(items) == limit else None}

	def _feed_snapshot(self, params):
		entity_type = self._entity(params)
		ids, limit = self._page(entity_type, params)
		items = [
			{
				"entity_id": i,
				"source_modified": self.docs[entity_type][i]["modified"],
				"payload": self.docs[entity_type][i]["payload"],
			}
			for i in ids
		]
		return {"items": items, "next_after_id": items[-1]["entity_id"] if len(items) == limit else None}

	def _feed_snapshot_by_ids(self, params):
		entity_type = self._entity(params)
		ids = json.loads(params.get("ids", "[]"))
		items, missing = [], []
		for entity_id in ids:
			doc = self.docs.get(entity_type, {}).get(entity_id)
			if doc is None:
				missing.append(entity_id)
			else:
				items.append(
					{"entity_id": entity_id, "source_modified": doc["modified"], "payload": doc["payload"]}
				)
		return {"items": items, "missing": missing}


class _Refused(Exception):
	def __init__(self, status: int, error_type: str):
		self.status = status
		self.error_type = error_type
