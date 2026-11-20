"""Nightly reconcile (identity site): compare each app site's provisioned users with the identity site's grants and repair toward the identity site.

For every enabled NXERP Peer it pages through the peer's `list_provisioned`, then:
  * missing: the identity site allows the user (enabled, holds the app's access role) but the peer has no enabled user -> queue Enable;
  * extra:   the peer has an enabled user holding the access role that the identity site does not allow -> queue Disable.
Repairs go through the same outbox as live changes (retried, idempotent), and are delivered at the end of the run. Idempotent: a second
run right after the first queues nothing new once the first run's repairs were delivered. Logs counts only, never an address.
Off unless `nxerp_site_role` is "identity". An unreachable peer is skipped and counted, never repaired by guessing.
"""

import frappe

from nxerp import audit, registry
from nxerp.federation import client, outbox

PAGE = 200
MAX_PAGES = 500  # 100 000 users per app: far above any real site; a runaway peer cannot loop forever


def _remote_users(peer: dict) -> dict:
	"""{email: {"enabled": bool, ...}} for everything the peer lists, following the cursor."""
	users, after = {}, ""
	for _ in range(MAX_PAGES):
		page = client.call(peer, "GET", "list_provisioned", params={"after": after, "limit": PAGE}) or {}
		for row in page.get("users") or []:
			users[(row.get("email") or "").lower()] = row
		after = page.get("next")
		if not after:
			return users
	raise client.PeerError("the peer's list did not end")


def _allowed_emails(entry) -> set:
	holders = set(
		frappe.get_all(
			"Has Role",
			filters={"role": ("in", sorted(entry.grant_roles)), "parenttype": "User"},
			pluck="parent",
		)
	)
	if not holders:
		return set()
	enabled = set(
		frappe.get_all("User", filters={"name": ("in", sorted(holders)), "enabled": 1}, pluck="name")
	)
	return {user.lower() for user in enabled if user not in outbox.SKIP_USERS}


def run() -> dict:
	"""Compare and repair every enabled peer. Returns counts; `bench execute nxerp.federation.reconcile.run` prints them."""
	if not outbox.enabled():
		return {"skipped": "not an identity site", "message": "nothing to do"}
	totals = {"peers": 0, "unreachable": 0, "missing": 0, "extra": 0, "differences": 0}
	for entry in registry.active_entries():
		peer = client.peer_for(entry.key)
		if not peer:
			continue
		totals["peers"] += 1
		try:
			remote = _remote_users(peer)
		except Exception as exc:
			totals["unreachable"] += 1
			audit.log_event(
				"federation_reconcile_unreachable", entry.key, None, error=outbox._safe_error(exc)
			)
			continue
		allowed = _allowed_emails(entry)
		on_peer = {email for email, row in remote.items() if row.get("enabled")}
		missing = sorted(allowed - on_peer)
		extra = sorted(on_peer - allowed)
		for email in missing:
			outbox.queue(email, entry.key, "Enable")
		for email in extra:
			outbox.queue(email, entry.key, "Disable")
		totals["missing"] += len(missing)
		totals["extra"] += len(extra)
		audit.log_event(
			"federation_reconcile",
			entry.key,
			None,
			missing=len(missing),
			extra=len(extra),
			on_peer=len(on_peer),
		)
	totals["differences"] = totals["missing"] + totals["extra"]
	if totals["differences"]:
		totals["delivery"] = outbox.process()
	totals["message"] = f"{totals['differences']} differences"
	return totals
