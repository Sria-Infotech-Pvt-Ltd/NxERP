"""The relay: gives committed outbox rows a sequence number, in order, and prunes acknowledged rows.

`assign_sequence` runs from the scheduler every minute. It takes one database-wide lock (`GET_LOCK`, so two relays
never run at once, and a second run is a no-op), claims committed `pending` rows in `(creation, name)` order in
batches of at most 1000, and gives them consecutive `seq` values, one transaction per batch. Rows written by a
transaction that has not committed are not visible to the relay, so a sequence number is only ever given to a
committed row and numbers follow the order rows were claimed. A failed batch rolls back and its rows stay pending.

The lock belongs to the database connection, not the transaction, and worker connections persist, so the lock is
always released explicitly in a `finally`.

Everything returns at its first line unless the site sets `nxerp_shared_publish`. Log lines carry counts only.
"""

import frappe
from frappe.utils import add_days, cint, now_datetime

from nxerp.shared import outbox

LOCK_NAME = "nxerp_outbox_relay"
BATCH_SIZE = 1000
DEFAULT_RETENTION_DAYS = 14
PRUNE_BATCH = 10000


class RelayBusy(frappe.ValidationError):
	"""Another relay holds the lock (HTTP 503 if it ever reaches a caller)."""

	http_status_code = 503


def _claim_batch(limit: int | None = None) -> int:
	"""Sequence up to `limit` pending rows in the current transaction; the caller commits."""
	limit = limit or BATCH_SIZE
	last = frappe.db.sql("SELECT COALESCE(MAX(seq), 0) FROM `tabNXERP Outbox Event`")[0][0]
	names = frappe.db.sql_list(
		"SELECT name FROM `tabNXERP Outbox Event` WHERE status = 'pending' ORDER BY creation, name LIMIT %s",
		(limit,),
	)
	claimed_at = now_datetime()
	for offset, name in enumerate(names, start=1):
		frappe.db.sql(
			"UPDATE `tabNXERP Outbox Event` SET seq = %s, status = 'claimed', claimed_at = %s "
			"WHERE name = %s AND status = 'pending'",
			(last + offset, claimed_at, name),
		)
	return len(names)


def assign_sequence(raise_if_busy: bool = False) -> int:
	"""Give every committed pending row the next sequence number. Returns how many rows were sequenced."""
	if not outbox.is_enabled():
		return 0
	if not frappe.db.sql("SELECT GET_LOCK(%s, 0)", (LOCK_NAME,))[0][0]:
		if raise_if_busy:
			raise RelayBusy("the outbox relay is already running")
		return 0
	total = 0
	try:
		while True:
			try:
				count = _claim_batch()
			except Exception:
				frappe.db.rollback()
				raise
			frappe.db.commit()  # one transaction per batch: a crash leaves the next batch pending, never half-numbered
			total += count
			if count < BATCH_SIZE:  # read at call time so a test can shrink the batch
				break
	finally:
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
	if total:
		frappe.logger("nxerp_shared", allow_site=True).info("relay sequenced %s outbox row(s)", total)
	return total


def prune() -> int:
	"""Delete acknowledged rows older than `nxerp_outbox_retention_days` (default 14). Unacknowledged rows are never deleted."""
	if not outbox.is_enabled():
		return 0
	days = cint(frappe.conf.get("nxerp_outbox_retention_days")) or DEFAULT_RETENTION_DAYS
	cutoff = add_days(now_datetime(), -max(days, 1))
	total = 0
	while True:
		frappe.db.sql(
			"DELETE FROM `tabNXERP Outbox Event` WHERE status = 'acked' AND acked_at < %s LIMIT %s",
			(cutoff, PRUNE_BATCH),
		)
		count = frappe.db.sql("SELECT ROW_COUNT()")[0][0]
		frappe.db.commit()
		total += count
		if count < PRUNE_BATCH:
			break
	if total:
		frappe.logger("nxerp_shared", allow_site=True).info("pruned %s acknowledged outbox row(s)", total)
	return total
