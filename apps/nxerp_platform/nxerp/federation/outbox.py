"""The provisioning outbox (identity site): grant changes become rows, rows become calls to the app sites.

Same reliability pattern as the shared layer: the row is written in the SAME transaction as the grant change (the `User` save), so a rolled
back change leaves no row; delivery happens afterwards, retried with exponential backoff and an idempotency key, and a nightly reconcile
(`nxerp.federation.reconcile`) repairs whatever a lost row or an outage left behind. Off unless `nxerp_site_role` is "identity".

Rows hold ids and a short error kind only (never a token, a secret or a response body).
"""

import secrets

import frappe
from frappe.utils import add_to_date, now_datetime

from nxerp import audit, registry
from nxerp.federation import client

DOCTYPE = "NXERP Provisioning Outbox"
MAX_ATTEMPTS = 8
BASE_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 3600
BATCH = 50
LOCK = "nxerp_federation_process"
SKIP_USERS = ("Administrator", "Guest")


def enabled() -> bool:
	return registry.site_role() == "identity"


def _roles(doc) -> set:
	return {row.role for row in (doc.get("roles") or [])}


def allowed(user_doc, entry) -> bool:
	"""The identity site's grant: the user is enabled and holds the app's access role (or one it implies)."""
	return bool(user_doc and user_doc.enabled and entry.grant_roles & _roles(user_doc))


def delay_for(attempts: int) -> int:
	return min(BASE_DELAY_SECONDS * 2 ** max(attempts - 1, 0), MAX_DELAY_SECONDS)


def queue(user: str, app_key: str, action: str, key: str | None = None):
	"""Write one Pending row. Same transaction as the caller's change."""
	return frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"user": user,
			"app_key": app_key,
			"action": action,
			"status": "Pending",
			"attempts": 0,
			"next_attempt": now_datetime(),
			"idempotency_key": key or f"{app_key}:{action}:{secrets.token_hex(12)}",
		}
	).insert(ignore_permissions=True)


def _enqueue_processing():
	frappe.enqueue(
		f"{__name__}.process",
		queue="short",
		enqueue_after_commit=True,
		deduplicate=True,
		job_id="nxerp_federation_process",
	)


def on_user_change(doc, method=None):
	"""doc_events["User"]["on_update"]. Queues a row for every active app whose grant for this user changed."""
	if not enabled() or doc.name in SKIP_USERS:
		return
	before = doc.get_doc_before_save()
	queued = 0
	for entry in registry.active_entries():
		had = allowed(before, entry)
		has = allowed(doc, entry)
		if had != has:
			queue(doc.name, entry.key, "Enable" if has else "Disable")
			queued += 1
	if queued:
		_enqueue_processing()


def queue_current(user: str, app_key: str) -> bool:
	"""Queue the user's CURRENT state for an app unless an identical Pending row is already waiting. Used by `set_app_access`."""
	entry = registry.active_entry(app_key)
	if not enabled() or not entry or user in SKIP_USERS:
		return False
	action = "Enable" if allowed(frappe.get_doc("User", user), entry) else "Disable"
	if frappe.db.exists(DOCTYPE, {"user": user, "app_key": app_key, "action": action, "status": "Pending"}):
		return False
	queue(user, app_key, action)
	_enqueue_processing()
	return True


def _safe_error(exc: Exception) -> str:
	"""Short, secret-free text: the exception's own message (PeerError texts carry a kind and a status only)."""
	text = str(exc) if isinstance(exc, client.PeerError) else type(exc).__name__
	return text[:140]


def _deliver(row):
	"""Send one row. Returns True when the peer acknowledged it."""
	peer = client.peer_for(row.app_key)
	entry = registry.active_entry(row.app_key)
	if not peer or not entry:
		return _fail(row, "no enabled peer for this app", final=True)
	user = frappe.db.exists("User", row.user)
	if not user:
		return _fail(row, "user no longer exists", final=True)
	user_doc = frappe.get_doc("User", row.user)
	# decide from the identity site's state NOW, not from when the row was written: the peer never ends up with more than we allow
	action = "Enable" if allowed(user_doc, entry) else "Disable"
	if action != row.action:
		row.action = action
	try:
		if action == "Enable":
			client.call(
				peer,
				"POST",
				"provision_user",
				data={
					"email": user_doc.name,
					"full_name": user_doc.full_name or user_doc.name,
					"enabled": 1,
					"user_type": user_doc.user_type,
					"app_key": row.app_key,
					"grant": 1,
					"idempotency_key": row.idempotency_key,
				},
			)
		else:
			client.call(
				peer,
				"POST",
				"deprovision_user",
				data={"email": user_doc.name, "idempotency_key": row.idempotency_key},
			)
	except Exception as exc:
		return _fail(row, _safe_error(exc))
	row.status = "Sent"
	row.attempts = (row.attempts or 0) + 1
	row.last_error = ""
	row.save(ignore_permissions=True)
	return True


def _fail(row, error: str, final: bool = False) -> bool:
	row.attempts = (row.attempts or 0) + 1
	row.last_error = error
	if final or row.attempts >= MAX_ATTEMPTS:
		row.status = "Failed"
	else:
		row.next_attempt = add_to_date(now_datetime(), seconds=delay_for(row.attempts))
	row.save(ignore_permissions=True)
	return False


def process() -> dict:
	"""Send due rows (scheduler "all", and once after each grant change). One run at a time; a no-op unless this is an identity site."""
	if not enabled():
		return {"sent": 0, "failed": 0, "skipped": "not an identity site"}
	lock = frappe.cache.lock(LOCK, timeout=300)
	if not lock.acquire(blocking=False):
		return {"sent": 0, "failed": 0, "skipped": "another run is in progress"}
	sent = failed = 0
	try:
		names = frappe.get_all(
			DOCTYPE,
			filters={"status": "Pending", "next_attempt": ("<=", now_datetime())},
			pluck="name",
			order_by="creation asc",
			limit=BATCH,
		)
		for name in names:
			row = frappe.get_doc(DOCTYPE, name)
			if _deliver(row):
				sent += 1
			else:
				failed += 1
			frappe.db.commit()
	finally:
		lock.release()
	audit.log_event("federation_process", None, None, sent=sent, failed=failed)
	return {"sent": sent, "failed": failed}
