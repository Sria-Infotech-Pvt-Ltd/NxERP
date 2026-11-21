"""Re-pointing, rebuild-and-verify, the text metrics and the alert rules (Phase 8E). The database tests skip without a reachable server.

Run: deploy/scripts/shared.sh test -p "test_repoint*"
"""

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared_service import __main__ as cli
from nxerp.shared_service import config, metrics, repoint
from nxerp.shared_service.feedclient import FeedClient, FeedUnavailable
from nxerp.shared_service.tests.support import OwnerTestCase

REPO = PLATFORM.parents[1]
ALERTS = REPO / "deploy" / "env" / "shared" / "alerts.example.yaml"


def write_sources(directory: str, sources: list) -> str:
	path = str(Path(directory) / "sources.json")
	Path(path).write_text(json.dumps({"sources": sources}), encoding="utf-8")
	return path


def entry(app_key="erpnext", key_file="/run/none/feed.key"):
	return {"app_key": app_key, "base_url": "https://owner.example.test", "key_file": key_file}


class FakeClient:
	def __init__(self, fails: bool):
		self.fails = fails

	def head(self):
		if self.fails:
			raise FeedUnavailable("unreachable")
		return {"max_seq": 7, "pending_count": 2}


class TestCheckSources(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)

	def test_an_unreachable_owner_is_refused_and_named(self):
		path = write_sources(self.tmp.name, [entry("erpnext"), entry("helpdesk")])
		report = repoint.check_sources(
			path, client_factory=lambda s: FakeClient(fails=s.app_key == "helpdesk")
		)
		self.assertFalse(report["ok"])
		self.assertTrue(report["sources"]["erpnext"]["ok"])
		self.assertEqual(report["sources"]["helpdesk"], {"ok": False, "error": "FeedUnavailable"})

	def test_every_owner_answering_is_ok_and_reports_counts_only(self):
		path = write_sources(self.tmp.name, [entry("erpnext")])
		report = repoint.check_sources(path, client_factory=lambda s: FakeClient(fails=False))
		self.assertEqual(
			report, {"ok": True, "sources": {"erpnext": {"ok": True, "max_seq": 7, "pending_count": 2}}}
		)

	def test_two_sources_for_one_app_and_an_empty_file_are_refused(self):
		with self.assertRaises(config.ConfigError):
			repoint.check_sources(
				write_sources(self.tmp.name, [entry("erpnext"), entry("erpnext")]),
				lambda s: FakeClient(False),
			)
		with self.assertRaises(config.ConfigError):
			repoint.check_sources(write_sources(self.tmp.name, []), lambda s: FakeClient(False))

	def test_the_command_exits_non_zero_for_an_unreadable_key_and_prints_no_secret(self):
		path = write_sources(
			self.tmp.name, [entry("erpnext", key_file=str(Path(self.tmp.name) / "missing.key"))]
		)
		out = io.StringIO()
		with contextlib.redirect_stdout(out):
			code = cli.main(["check-sources", "--file", path])
		self.assertEqual(code, 1)
		self.assertIn('"ok": false', out.getvalue())
		self.assertNotIn("missing.key", out.getvalue())


class TestTextMetrics(unittest.TestCase):
	ROWS: ClassVar[list] = [
		{"source": "erpnext", "name": "lag_seconds", "value": 12},
		{"source": "erpnext", "name": "outbox_pending", "value": 3},
		{"source": "erpnext", "name": "errors", "value": 1},
		{"source": "erpnext", "name": "dead_letters", "value": 0},
		{"source": "erpnext", "name": "reconcile_drift", "value": 0},
		{"source": "erpnext", "name": "last_success", "value": 1000.5},
		{"source": "erpnext", "name": "rebuilt_at", "value": 900},
	]

	def render(self, rows=None, outcomes=None):
		return metrics.render_text(
			self.ROWS if rows is None else rows,
			outcomes or {"ok": 5, "denied_field": 2, "denied_unauthorized": 1},
			0,
			now=1000,
		)

	def test_every_metric_the_alerts_and_the_prompt_name_is_exposed(self):
		text = self.render()
		for name in (
			"outbox_lag_seconds",
			"outbox_pending",
			"projector_errors",
			"dead_letters",
			"reconcile_drift",
			"rebuild_age_seconds",
			"read_api_requests",
			"read_api_denied",
		):
			self.assertIn(f"# TYPE {name} ", text, name)

	def test_values_and_derived_numbers(self):
		text = self.render()
		self.assertIn('outbox_lag_seconds{source="erpnext"} 12', text)
		self.assertIn('outbox_pending{source="erpnext"} 3', text)
		self.assertIn('rebuild_age_seconds{source="erpnext"} 100', text)
		self.assertIn("read_api_requests 8", text)
		self.assertIn("read_api_denied 3", text)

	def test_names_are_declared_even_with_no_data_and_no_value_text_leaks(self):
		text = self.render(rows=[], outcomes={})
		self.assertIn("# TYPE outbox_lag_seconds gauge", text)
		self.assertNotIn("{source=", text)
		self.assertTrue(
			all(
				re.match(r"^(#|[a-z_]+(\{source=\"[a-z0-9_-]+\"\})? [0-9.]+$)", line)
				for line in text.strip().split("\n")
			)
		)


class TestAlertRules(unittest.TestCase):
	def setUp(self):
		if not ALERTS.exists():
			self.skipTest("the rules file is outside the test container: run these on the host")

	def rules(self):
		import yaml

		return yaml.safe_load(ALERTS.read_text(encoding="utf-8"))["groups"][0]["rules"]

	def test_the_file_parses_and_holds_the_five_rules(self):
		try:
			import yaml
		except ImportError:
			self.skipTest("PyYAML is not installed")
		names = {r["alert"] for r in self.rules()}
		self.assertEqual(
			names,
			{
				"SharedLayerLag",
				"SharedLayerDeadLetter",
				"SharedLayerDrift",
				"SharedProjectorLoginFailure",
				"SharedProjectorNoPull",
			},
		)

	def test_the_thresholds_and_metric_names_match_the_exporter(self):
		try:
			import yaml
		except ImportError:
			self.skipTest("PyYAML is not installed")
		exposed = set(metrics.TEXT_METRICS) | {metrics.REBUILD_AGE}
		by_name = {r["alert"]: r["expr"] for r in self.rules()}
		self.assertIn("> 300", by_name["SharedLayerLag"])
		self.assertIn("> 900", by_name["SharedProjectorNoPull"])
		for expr in by_name.values():
			used = set(re.findall(r"\b([a-z_]+)(?=[\[)\s{]|$)", expr)) & (exposed | {"time"})
			self.assertTrue(used, expr)
		for rule in self.rules():
			text = json.dumps(rule["annotations"])
			self.assertNotIn("password", text.lower())
			self.assertNotIn("token", text.lower())


class TestRebuildAndVerify(OwnerTestCase):
	def seed(self):
		for index in range(1, 5):
			self.owner.upsert(
				"customer", f"C{index}", display_name=f"Name {index}", customer_type="Company", territory="T1"
			)
		self.projector.run_once()

	def verify(self):
		return repoint.rebuild_and_verify(
			lambda: self.connect("projector"),
			[self.source],
			client_factory=lambda source: FeedClient(source, self.owner.key),
			metrics=self.metrics,
			relay_wait=0,
			page=2,
		)

	def test_a_consistent_layer_verifies_with_drift_zero(self):
		self.seed()
		report = self.verify()
		self.assertTrue(report["ok"], report)
		self.assertEqual(report["drift"], 0)
		self.assertIsNotNone(self.metric("rebuilt_at"))

	def test_an_injected_drift_fails_the_verification(self):
		self.seed()
		self.owner.bypass_change("customer", "C3", territory="Changed behind the event")
		stub = {"sources": {"stub": {"drift_after": 0, "dead_letters": 0}}}
		with patch("nxerp.shared_service.repoint.rebuild", return_value=stub):
			report = self.verify()
		self.assertFalse(report["ok"])
		self.assertGreater(report["drift"], 0)


if __name__ == "__main__":
	unittest.main()
