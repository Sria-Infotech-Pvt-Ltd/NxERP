"""Source configuration and the feed client: unit tests, no database.

python -m unittest discover apps/nxerp_platform/nxerp/shared_service/tests -t apps/nxerp_platform
"""

import sys
import tempfile
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLATFORM))

from nxerp.shared_service import config
from nxerp.shared_service.config import ConfigError, Source
from nxerp.shared_service.feedclient import FeedClient, FeedRejected, FeedUnavailable
from nxerp.shared_service.tests.fakeowner import FakeOwner

GOOD = {
	"app_key": "nxerp",
	"base_url": "https://nxerp.example.test",
	"key_file": "/run/nxerp-shared/feed.key",
}


class TestSourcesFile(unittest.TestCase):
	def parse(self, *entries, env=None):
		return config.parse_sources({"sources": list(entries)}, env or {})

	def test_a_valid_https_source_is_accepted(self):
		(source,) = self.parse(GOOD)
		self.assertEqual(
			(source.app_key, source.base_url, source.host_header),
			("nxerp", "https://nxerp.example.test", None),
		)

	def test_http_is_refused_unless_the_throwaway_stack_flag_is_set(self):
		insecure = {**GOOD, "base_url": "http://owner:8000"}
		with self.assertRaises(ConfigError):
			self.parse(insecure)
		self.assertEqual(
			self.parse(insecure, env={"SHARED_ALLOW_INSECURE_FEED": "1"})[0].base_url, "http://owner:8000"
		)

	def test_bad_entries_are_refused(self):
		for entry in (
			{**GOOD, "app_key": "Bad Key"},
			{**GOOD, "base_url": "https://owner.example.test/api"},
			{**GOOD, "base_url": "ftp://owner"},
			{**GOOD, "key_file": ""},
			{**GOOD, "host_header": "bad host!"},
			{**GOOD, "surprise": 1},
			"not an object",
		):
			with self.assertRaises(ConfigError, msg=str(entry)):
				self.parse(entry)
		with self.assertRaises(ConfigError):
			self.parse(GOOD, GOOD)
		with self.assertRaises(ConfigError):
			config.parse_sources({"sources": "no"}, {})

	def test_a_key_file_holds_one_key_secret_line(self):
		with tempfile.TemporaryDirectory() as tmp:
			good = Path(tmp, "good.key")
			good.write_text("abcd1234:efgh5678\n", encoding="utf-8")
			self.assertEqual(
				config.read_key(Source("nxerp", "https://x.test", str(good))), "abcd1234:efgh5678"
			)
			for content in ("", "just-a-secret", "a:b:c", "ab:cd"):
				bad = Path(tmp, "bad.key")
				bad.write_text(content, encoding="utf-8")
				with self.assertRaises(ConfigError, msg=repr(content)):
					config.read_key(Source("nxerp", "https://x.test", str(bad)))
			with self.assertRaises(ConfigError):
				config.read_key(Source("nxerp", "https://x.test", str(Path(tmp, "missing.key"))))

	def test_an_error_message_never_contains_the_key(self):
		with tempfile.TemporaryDirectory() as tmp:
			bad = Path(tmp, "bad.key")
			bad.write_text("topsecretvalue", encoding="utf-8")
			with self.assertRaises(ConfigError) as caught:
				config.read_key(Source("nxerp", "https://x.test", str(bad)))
			self.assertNotIn("topsecretvalue", str(caught.exception))


class TestFeedClient(unittest.TestCase):
	def setUp(self):
		self.owner = FakeOwner().start()
		self.addCleanup(self.owner.stop)
		self.source = Source("stub", self.owner.base_url, "unused", None)

	def client(self, key=None):
		return FeedClient(self.source, key or self.owner.key)

	def test_the_six_methods_round_trip(self):
		self.owner.upsert("customer", "C1", display_name="One")
		client = self.client()
		self.assertEqual(client.head()["max_seq"], 1)
		self.assertEqual([e["seq"] for e in client.pull(0, 10)["events"]], [1])
		self.assertEqual(client.ack(1)["acked_through"], 1)
		self.assertEqual(client.digest("customer")["items"][0]["entity_id"], "C1")
		self.assertEqual(client.snapshot("customer")["items"][0]["payload"]["display_name"], "One")
		answer = client.snapshot_by_ids("customer", ["C1", "nope"])
		self.assertEqual((len(answer["items"]), answer["missing"]), (1, ["nope"]))

	def test_a_wrong_key_is_rejected_with_its_status_and_not_retried(self):
		with self.assertRaises(FeedRejected) as caught:
			self.client("wrongkey:wrongsecret").head()
		self.assertEqual(caught.exception.status, 401)
		self.assertNotIn("wrongsecret", str(caught.exception))
		self.owner.force_status = 403
		with self.assertRaises(FeedRejected) as caught:
			self.client().head()
		self.assertEqual((caught.exception.status, caught.exception.error_type), (403, "ForcedError"))

	def test_an_unserved_entity_is_a_422_rejection(self):
		with self.assertRaises(FeedRejected) as caught:
			self.client().snapshot("employee_ref")
		self.assertEqual((caught.exception.status, caught.exception.error_type), (422, "FeedError"))

	def test_server_errors_and_rate_limits_are_unavailable_not_rejected(self):
		for status in (500, 502, 503, 429):
			self.owner.force_status = status
			with self.assertRaises(FeedUnavailable, msg=str(status)):
				self.client().head()

	def test_a_closed_port_and_a_dead_host_are_unavailable(self):
		self.owner.stop()
		with self.assertRaises(FeedUnavailable):
			self.client().head()
		dead = FeedClient(Source("x", "http://127.0.0.1:1", "unused", None), "k:s", connect_timeout=0.5)
		with self.assertRaises(FeedUnavailable):
			dead.head()
		self.owner = FakeOwner().start()  # so tearDown can stop it

	def test_the_host_header_overrides_the_address(self):
		self.assertEqual(self.client().head()["max_seq"], 0)
		self.assertTrue(self.owner.last_host.startswith("127.0.0.1"))
		source = Source("stub", self.owner.base_url, "unused", "helpdesk.example.test")
		FeedClient(source, self.owner.key).head()
		self.assertEqual(self.owner.last_host, "helpdesk.example.test")


if __name__ == "__main__":
	unittest.main()
