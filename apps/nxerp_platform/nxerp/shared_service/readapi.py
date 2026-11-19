"""The Read API v1: the only way an app reads the shared read layer. A Werkzeug WSGI app served by the image's gunicorn. No frappe.

	GET /v1/health                    liveness and database reachability (no token, no audit)
	GET /v1/metrics                   projector metrics and this process's counters (a valid token, internal network only)
	GET /v1/{entity_type}             a page of rows:  fields, tenant, min_version, limit (max 200), after
	GET /v1/{entity_type}/{id}        one row:         fields, tenant, min_version

Every other method answers 405: there is no write verb. A request is authorised in this order: token (401), entity and grant (404 for
an unknown entity, 403 if the app has no grant), fields (403 for any field outside the grant, never an empty column) and tenant.
It reads only the generated views `v_<app>_<entity>`, through an account with no privilege on any base table, so the rows it can see
are exactly the granted columns of live rows of the granted tenant. A response carries only the granted fields plus `entity_id`,
`tenant_id`, `source_modified` and `synced_at`, even if a view someday had more columns.

Every call is audited (the app, the acting user from `X-Acting-User`, the entity, a hash of the ids returned, the row count, the outcome),
including denied ones, through batched inserts into the audit view so reads stay fast. Error bodies never carry SQL or a stack trace.
Tokens are never logged. The service listens on the private sync network; TLS ends at the edge proxy if it is ever exposed beyond it.
"""

import atexit
import hashlib
import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from datetime import datetime

import pymysql
from werkzeug.wrappers import Request, Response

from nxerp.shared import payload as payload_module
from nxerp.shared import registry
from nxerp.shared_service import credentials, db, sqlutil
from nxerp.shared_service.views import SYSTEM_COLUMNS, view_name

log = logging.getLogger("nxerp.shared.api")

MAX_LIMIT = 200
DEFAULT_LIMIT = 50
MIN_VERSION_WAIT_SECONDS = 2.0
MIN_VERSION_POLL_SECONDS = 0.1
CACHE_SECONDS = 30
DEFAULT_RATE_PER_MINUTE = 600
ENTITY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
ENTITY_ID = re.compile(r"^.{1,140}$", re.S)
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{1,6})?$")
CONNECTION_ERRORS = {2002, 2003, 2006, 2013, 2055, 1045, 1044, 1049}


class ApiError(Exception):
	def __init__(
		self, status: int, code: str, message: str, headers: dict | None = None, outcome: str | None = None
	):
		super().__init__(code)
		self.status, self.code, self.message, self.headers, self.outcome = (
			status,
			code,
			message,
			headers or {},
			outcome or code,
		)


def _is_db_down(exc: Exception) -> bool:
	return type(exc).__module__.startswith("pymysql") and (
		not exc.args or exc.args[0] in CONNECTION_ERRORS or type(exc).__name__ == "InterfaceError"
	)


def json_value(value):
	if isinstance(value, datetime):
		return value.strftime(payload_module.DATETIME_FORMAT)
	if isinstance(value, bytes):
		return value.decode("utf-8", "replace")
	return value


def parse_stamp(text: str) -> datetime:
	return datetime.strptime(text if "." in text else text + ".0", "%Y-%m-%d %H:%M:%S.%f")


class RateLimiter:
	"""A token bucket per credential, in this process (with N gunicorn workers the effective limit is N times the setting)."""

	def __init__(self, per_minute: int, clock=time.monotonic):
		self.capacity = per_minute
		self.rate = per_minute / 60.0
		self._clock = clock
		self._buckets: dict = {}
		self._lock = threading.Lock()

	def allow(self, key: str) -> tuple:
		now = self._clock()
		with self._lock:
			tokens, last = self._buckets.get(key, (float(self.capacity), now))
			tokens = min(float(self.capacity), tokens + (now - last) * self.rate)
			if tokens >= 1:
				self._buckets[key] = (tokens - 1, now)
				return True, 0.0
			self._buckets[key] = (tokens, now)
			return False, (1 - tokens) / self.rate


class AuditWriter:
	"""Batched audit inserts through the audit view, so a read never waits for its own audit row."""

	def __init__(
		self,
		connect,
		flush_seconds: float = 0.5,
		batch: int = 100,
		max_queue: int = 10000,
		background: bool = True,
	):
		self._connect = connect
		self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
		self._batch = batch
		self._flush_seconds = flush_seconds
		self._conn = None
		self._lock = threading.Lock()
		self.dropped = 0
		self._wake = threading.Event()
		if background:
			threading.Thread(target=self._loop, daemon=True, name="read-audit").start()
		atexit.register(self.flush)

	def record(self, **row) -> None:
		try:
			self._queue.put_nowait(row)
		except queue.Full:  # never block or fail a read because the audit backlog is full
			self.dropped += 1
			log.error("read audit queue is full: a row was dropped")
		if self._queue.qsize() >= self._batch:
			self._wake.set()

	def _loop(self) -> None:
		while True:
			self._wake.wait(self._flush_seconds)
			self._wake.clear()
			self.flush()

	def flush(self) -> int:
		"""Write everything queued now. Returns the number of rows written; a failure puts the rows back for the next try."""
		with self._lock:
			rows = []
			while len(rows) < 1000:
				try:
					rows.append(self._queue.get_nowait())
				except queue.Empty:
					break
			if not rows:
				return 0
			try:
				if self._conn is None:
					self._conn = self._connect()
				with self._conn.cursor() as cur:
					cur.executemany(
						"INSERT INTO ctl_read_audit (read_at, consumer_app, entity_type, entity_id, tenant_id, fields_returned, row_count, "
						"request_id, outcome, acting_user, ids_hash) VALUES (NOW(6), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
						[
							(
								r["app"],
								r["entity_type"],
								r.get("entity_id"),
								r.get("tenant"),
								json.dumps(r.get("fields")) if r.get("fields") is not None else None,
								r.get("rows", 0),
								r.get("request_id"),
								r["outcome"],
								r.get("acting_user"),
								r.get("ids_hash"),
							)
							for r in rows
						],
					)
				self._conn.commit()
				return len(rows)
			except (
				pymysql.err.DataError
			) as exc:  # rows the table cannot hold would fail every retry: drop them, never loop
				self.dropped += len(rows)
				log.error(
					"read audit rows dropped (%s): %s", len(rows), exc.args[0] if exc.args else "data error"
				)
				return 0
			except Exception as exc:
				self._conn = None
				for r in rows:
					try:
						self._queue.put_nowait(r)
					except queue.Full:
						self.dropped += 1
				log.warning("could not write the read audit: %s", type(exc).__name__)
				return 0


class ReadApi:
	def __init__(
		self,
		connect=None,
		rate_per_minute: int = DEFAULT_RATE_PER_MINUTE,
		cache_seconds: float = CACHE_SECONDS,
		audit_background: bool = True,
		clock=time.time,
		sleep=time.sleep,
	):
		self._connect = connect or (lambda: db.connect(db.settings_from_env("readapi"), autocommit=True))
		self._local = threading.local()
		self.limiter = RateLimiter(rate_per_minute)
		self.audit = AuditWriter(self._connect, background=audit_background)
		self.cache_seconds = cache_seconds
		self._clock = clock
		self._sleep = sleep
		self._grants: tuple | None = None
		self._tokens: dict = {}
		self.stats: dict = {}

	# ---- WSGI ----------------------------------------------------------------------------------------

	def __call__(self, environ, start_response):
		request = Request(environ)
		request_id = request.headers.get("X-Request-Id", "")[:64] or uuid.uuid4().hex
		call = {"app": "-", "entity_type": "-", "request_id": request_id, "outcome": "error", "rows": 0}
		call["acting_user"] = (request.headers.get("X-Acting-User") or "")[:140] or None
		try:
			response = self.dispatch(request, call)
		except ApiError as exc:
			call["outcome"] = exc.outcome
			response = self._error(exc)
		except Exception as exc:
			if _is_db_down(exc):
				self._local.conn = None
				call["outcome"] = "unavailable"
				response = self._error(
					ApiError(503, "database_unavailable", "The shared database is not reachable")
				)
			else:
				log.error("read api error: %s", type(exc).__name__)
				call["outcome"] = "error"
				response = self._error(ApiError(500, "internal_error", "Something went wrong"))
		response.headers["X-Request-Id"] = request_id
		self.stats[call["outcome"]] = self.stats.get(call["outcome"], 0) + 1
		if not request.path.startswith("/v1/health"):
			self.audit.record(**call)
		return response(environ, start_response)

	@staticmethod
	def _json(payload, status: int = 200) -> Response:
		response = Response(
			json.dumps(payload, default=json_value, separators=(",", ":")),
			status=status,
			mimetype="application/json",
		)
		response.headers["Cache-Control"] = "private, max-age=0"
		return response

	def _error(self, exc: ApiError) -> Response:
		response = self._json({"error": {"code": exc.code, "message": exc.message}}, exc.status)
		for name, value in exc.headers.items():
			response.headers[name] = value
		return response

	# ---- database ------------------------------------------------------------------------------------

	def conn(self):
		connection = getattr(self._local, "conn", None)
		if connection is None:
			connection = self._local.conn = self._connect()
		else:
			try:
				connection.ping(reconnect=True)
			except Exception:
				self._local.conn = None
				connection = self._local.conn = self._connect()
		return connection

	def query(self, sql: str, params=None) -> list:
		with self.conn().cursor() as cur:
			cur.execute(sql, params)
			return list(cur.fetchall())

	# ---- routing and authorisation ---------------------------------------------------------------------

	def dispatch(self, request: Request, call: dict) -> Response:
		path = request.path.rstrip("/") or "/"
		if not path.startswith("/v1"):
			raise ApiError(404, "not_found", "No such path")
		if request.method != "GET":
			call["outcome"] = "denied_method"
			app = self._authenticate_quietly(request)
			call["app"] = app or "-"
			raise ApiError(
				405, "method_not_allowed", "Only GET is allowed", {"Allow": "GET"}, "denied_method"
			)
		parts = [p for p in path.split("/")[1:] if p]
		if parts == ["v1", "health"] or parts == ["health"]:
			self.query("SELECT 1 AS ok")
			call["outcome"] = "ok"
			return self._json({"status": "ok"})
		if len(parts) < 2:
			raise ApiError(404, "not_found", "No such path")
		app, credential_id = self._authenticate(request)
		call["app"] = app
		self._rate_limit(credential_id)
		if parts[1] == "metrics" and len(parts) == 2:
			call["entity_type"] = "-metrics"
			call["outcome"] = "ok"
			return self._metrics()
		entity_type = parts[1]
		call["entity_type"] = entity_type if ENTITY.match(entity_type) else "-invalid"
		grant = self._grant_for(app, entity_type)
		if len(parts) == 2:
			return self._list(request, call, app, entity_type, grant)
		if len(parts) == 3:
			return self._one(request, call, app, entity_type, grant, parts[2])
		raise ApiError(404, "not_found", "No such path")

	def _authenticate_quietly(self, request: Request) -> str | None:
		try:
			return self._authenticate(request)[0]
		except ApiError:
			return None
		except Exception:
			return None

	def _authenticate(self, request: Request) -> tuple:
		header = request.headers.get("Authorization", "")
		scheme, _, token = header.partition(" ")
		parts = credentials.split_token(token.strip()) if scheme.lower() == "bearer" else None
		if parts is None:
			raise ApiError(
				401,
				"unauthorized",
				"A valid token is required",
				{"WWW-Authenticate": "Bearer"},
				"denied_unauthorized",
			)
		key = hashlib.sha256(token.strip().encode("ascii")).hexdigest()
		cached = self._tokens.get(key)
		if cached and self._clock() - cached[2] < self.cache_seconds:
			return cached[0], cached[1]
		credential_id, secret = parts
		rows = self.query(
			"SELECT credential_id, consumer_app, salt, secret_hash, scrypt_n, scrypt_r, scrypt_p, "
			"(expires_at IS NULL OR expires_at > NOW(6)) AS active FROM ctl_consumer_credential WHERE credential_id = %s",
			(credential_id,),
		)
		row = rows[0] if rows else None
		if not credentials.verify_secret(secret, row) or not row["active"]:
			raise ApiError(
				401,
				"unauthorized",
				"A valid token is required",
				{"WWW-Authenticate": "Bearer"},
				"denied_unauthorized",
			)
		self._tokens[key] = (row["consumer_app"], credential_id, self._clock())
		return row["consumer_app"], credential_id

	def _rate_limit(self, credential_id: str) -> None:
		allowed, retry_after = self.limiter.allow(credential_id)
		if not allowed:
			raise ApiError(
				429,
				"rate_limited",
				"Too many requests",
				{"Retry-After": str(max(1, int(retry_after + 0.999)))},
				"rate_limited",
			)

	def _grant_for(self, app: str, entity_type: str) -> dict:
		if not ENTITY.match(entity_type):
			raise ApiError(404, "unknown_entity", "No such entity", outcome="not_found")
		contract = registry.get_contract(entity_type)
		if contract is None or contract["status"] != "active":
			raise ApiError(404, "unknown_entity", "No such entity", outcome="not_found")
		grants = self._load_grants()
		grant = grants.get((app, entity_type))
		if grant is None:
			raise ApiError(
				403, "not_granted", "This app has no grant on this entity", outcome="denied_not_granted"
			)
		order = [f["shared"] for f in contract["fields"]]
		return {"fields": [f for f in order if f in grant["fields"]], "tenant": grant["tenant"]}

	def _load_grants(self) -> dict:
		now = self._clock()
		if self._grants and now - self._grants[0] < self.cache_seconds:
			return self._grants[1]
		grants = {}
		for row in self.query(
			"SELECT consumer_app, entity_type, granted_fields, tenant_id FROM ctl_consumer_grant"
		):
			fields = row["granted_fields"]
			grants[(row["consumer_app"], row["entity_type"])] = {
				"fields": set(json.loads(fields) if isinstance(fields, str | bytes) else fields),
				"tenant": row["tenant_id"],
			}
		self._grants = (now, grants)
		return grants

	def clear_caches(self) -> None:
		self._grants = None
		self._tokens.clear()

	# ---- reads ---------------------------------------------------------------------------------------

	def _fields(self, request: Request, call: dict, grant: dict) -> list:
		raw = request.args.get("fields")
		if not raw:
			return grant["fields"]
		requested = [f.strip() for f in raw.split(",") if f.strip()]
		outside = [f for f in requested if f not in grant["fields"]]
		if outside:
			call["outcome"] = "denied_field"
			raise ApiError(
				403,
				"field_not_granted",
				"A requested field is not granted to this app: " + ", ".join(sorted(set(outside))[:5])[:200],
				outcome="denied_field",
			)
		return [f for f in grant["fields"] if f in set(requested)]

	@staticmethod
	def _tenant(request: Request, grant: dict) -> str | None:
		asked = request.args.get("tenant")
		if grant["tenant"]:
			if asked and asked != grant["tenant"]:
				raise ApiError(
					403,
					"tenant_not_granted",
					"The grant is limited to another tenant",
					outcome="denied_tenant",
				)
			return grant["tenant"]
		return asked or None

	@staticmethod
	def _min_version(request: Request):
		raw = request.args.get("min_version")
		if raw is None:
			return None
		if not STAMP.match(raw):
			raise ApiError(
				422,
				"bad_parameter",
				"min_version must be a datetime like 2026-11-18 10:21:04.512311",
				outcome="bad_request",
			)
		return parse_stamp(raw)

	def _shape(self, row: dict, columns: list) -> dict:
		return {name: json_value(row.get(name)) for name in columns}

	def _one(self, request, call, app, entity_type, grant, entity_id) -> Response:
		if not ENTITY_ID.match(entity_id):
			raise ApiError(404, "not_found", "No such record", outcome="not_found")
		fields = self._fields(request, call, grant)
		tenant = self._tenant(request, grant)
		minimum = self._min_version(request)
		call["entity_id"] = entity_id
		call["tenant"] = tenant
		call["fields"] = fields
		call["ids_hash"] = hashlib.sha256(entity_id.encode()).hexdigest()
		columns = [*SYSTEM_COLUMNS, *fields]
		where, params = "`entity_id` = %s", [entity_id]
		if tenant:
			where, params = where + " AND `tenant_id` = %s", [*params, tenant]
		sql = sqlutil.select(view_name(app, entity_type), columns, where=where)
		deadline = self._clock() + MIN_VERSION_WAIT_SECONDS
		while True:
			rows = self.query(sql, params)
			fresh = bool(rows) and (minimum is None or rows[0]["source_modified"] >= minimum)
			if fresh or minimum is None or self._clock() >= deadline:
				break
			self._sleep(MIN_VERSION_POLL_SECONDS)
		if minimum is not None and not fresh:
			call["outcome"] = "pending"
			return self._json({"status": "pending", "retry_after_ms": 1000}, 202)
		if not rows:
			raise ApiError(
				404, "not_found", "No such record", outcome="not_found"
			)  # unknown, a tombstone and another tenant look the same
		call["outcome"] = "ok"
		call["rows"] = 1
		return self._json({"data": self._shape(rows[0], columns)})

	def _list(self, request, call, app, entity_type, grant) -> Response:
		fields = self._fields(request, call, grant)
		tenant = self._tenant(request, grant)
		minimum = self._min_version(request)
		try:
			limit = int(request.args.get("limit", DEFAULT_LIMIT))
		except ValueError:
			limit = 0
		if not 1 <= limit <= MAX_LIMIT:
			raise ApiError(
				422, "bad_parameter", f"limit must be an integer from 1 to {MAX_LIMIT}", outcome="bad_request"
			)
		after = request.args.get("after", "")
		if len(after) > 140:
			raise ApiError(422, "bad_parameter", "after is too long", outcome="bad_request")
		call["tenant"] = tenant
		call["fields"] = fields
		columns = [*SYSTEM_COLUMNS, *fields]
		view = view_name(app, entity_type)
		filters, params = ["`entity_id` > %s"], [after]
		if tenant:
			filters.append("`tenant_id` = %s")
			params.append(tenant)
		if minimum is not None:
			deadline = self._clock() + MIN_VERSION_WAIT_SECONDS
			while True:
				newest = self.query(
					sqlutil.select(
						view,
						["source_modified"],
						where=" AND ".join(filters[1:]) or "1 = 1",
						order_by="`source_modified` DESC",
						limit=True,
					),
					[*params[1:], 1],
				)
				if newest and newest[0]["source_modified"] >= minimum:
					break
				if self._clock() >= deadline:
					call["outcome"] = "pending"
					return self._json({"status": "pending", "retry_after_ms": 1000}, 202)
				self._sleep(MIN_VERSION_POLL_SECONDS)
		rows = self.query(
			sqlutil.select(view, columns, where=" AND ".join(filters), order_by="`entity_id`", limit=True),
			[*params, limit + 1],
		)
		more = len(rows) > limit
		rows = rows[:limit]
		call["outcome"] = "ok"
		call["rows"] = len(rows)
		call["ids_hash"] = (
			hashlib.sha256("\n".join(r["entity_id"] for r in rows).encode()).hexdigest() if rows else None
		)
		body = {
			"data": [self._shape(r, columns) for r in rows],
			"next_after": rows[-1]["entity_id"] if more and rows else None,
		}
		return self._json(body)

	def _metrics(self) -> Response:
		rows = self.query("SELECT source, name, value, updated_at FROM ctl_sync_metric ORDER BY source, name")
		return self._json(
			{
				"projector": {f"{r['source']}.{r['name']}": r["value"] for r in rows},
				"api": {"outcomes": dict(sorted(self.stats.items())), "audit_dropped": self.audit.dropped},
			}
		)


def create_app() -> ReadApi:
	return ReadApi(rate_per_minute=int(os.environ.get("SHARED_API_RATE_PER_MINUTE", DEFAULT_RATE_PER_MINUTE)))


app = create_app()
