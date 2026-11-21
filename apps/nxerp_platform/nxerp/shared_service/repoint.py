"""Re-pointing the projector at new owner sites (Phase 8, work package 8E), and the check that follows a rebuild. No frappe.

`check_sources` validates a candidate sources file and asks every owner's feed for its head, so a typo or an unreachable owner is found
BEFORE the live file is replaced. It writes nothing. The sources file format (and the refusal of two sources for the same `app_key`)
is `config.parse_sources`.

`rebuild_and_verify` rebuilds every source from its owner (snapshot, then replay: the cursor of a re-pointed source starts from the
rebuild, never from an old cursor) and then compares everything with the owners. It is `ok` only when no drift is left anywhere.

Output is counts and names only: never a key, a token or a payload value.
"""

import json

from nxerp.shared_service import config
from nxerp.shared_service.feedclient import FeedClient, FeedRejected, FeedUnavailable
from nxerp.shared_service.rebuild import RebuildError, rebuild
from nxerp.shared_service.reconcile import Reconciler


def check_sources(path: str, client_factory=None, env=None) -> dict:
	"""{"ok": bool, "sources": {app_key: {"ok": bool, "max_seq"|"error": ...}}}. Raises ConfigError for an unusable file."""
	with open(path, encoding="utf-8") as handle:
		sources = config.parse_sources(json.load(handle), env)
	if not sources:
		raise config.ConfigError(
			"the sources file lists no source: refusing to leave the projector with nothing to read"
		)
	client_factory = client_factory or (lambda source: FeedClient(source, config.read_key(source)))
	report = {"ok": True, "sources": {}}
	for source in sources:
		try:
			head = client_factory(source).head()
			report["sources"][source.app_key] = {
				"ok": True,
				"max_seq": head.get("max_seq", 0),
				"pending_count": head.get("pending_count", 0),
			}
		except (FeedUnavailable, FeedRejected, config.ConfigError, OSError) as exc:
			report["ok"] = False
			report["sources"][source.app_key] = {"ok": False, "error": type(exc).__name__}
	return report


def rebuild_and_verify(
	connect, sources: list, client_factory=None, metrics=None, relay_wait: float = 90.0, page: int = 500
) -> dict:
	"""Rebuild every source, then reconcile in full. `ok` is False if anything is left over: drift, a refused repair, a source that
	did not answer, an unresolved dead letter. A failed rebuild is reported (not raised) so the caller can print it and exit non-zero."""
	client_factory = client_factory or (lambda source: FeedClient(source, config.read_key(source)))
	report = {"ok": False, "rebuild": {}, "reconcile": {}, "drift": None}
	try:
		report["rebuild"] = rebuild(
			connect, sources, client_factory=client_factory, metrics=metrics, relay_wait=relay_wait, page=page
		)
	except RebuildError as exc:
		report["rebuild"] = exc.report
		report["error"] = str(exc)
		return report
	left_after_rebuild = sum(s["drift_after"] for s in report["rebuild"]["sources"].values())
	dead = sum(s.get("dead_letters", 0) for s in report["rebuild"]["sources"].values())
	reconcile_report = Reconciler(
		connect, sources, client_factory=client_factory, metrics=metrics, page=page
	).run("full")
	report["reconcile"] = reconcile_report
	report["drift"] = reconcile_report["drift"] + left_after_rebuild
	not_ok = [k for k, s in reconcile_report["sources"].items() if s["status"] != "ok"]
	report["ok"] = report["drift"] == 0 and reconcile_report["refused"] == 0 and not not_ok and dead == 0
	if not_ok:
		report["error"] = f"sources that did not answer: {sorted(not_ok)}"
	return report
