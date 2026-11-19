"""Identity-site behaviour (Phase 6B): the registry's peers and origins, safe cross-origin redirects, and FIVE apps.

Everything is behind the site config key `nxerp_site_role`. Two things are proved here:
  * with it unset (or anything else) the platform behaves exactly as before, even when NXERP Peer records exist;
  * with it set to "identity", people are sent only to the EXACT origin of an enabled peer, and the gate, the launcher tiles and the
    allowed origins hold for five apps (the two real ones and three TEST ONLY stand-ins that are never installed or shipped,
    registered by substituting `registry.get_registry` for this process, as test_add_app_checklist.py does).

In process, no HTTP. Everything is rolled back.
"""

from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import urlsplit

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import access, launcher, registry, routing
from nxerp.tests.test_routing import HOSTILE
from nxerp.tests.utils import PLAIN_DESK_ROLE, delete_users, make_user, purge_test_users, unique_email

PEER_ORIGINS = {
	"erpnext": "https://erp.example.test",
	"helpdesk": "https://hd.example.test",
	"dummy-a": "https://a.example.test",
	"dummy-b": "https://b.example.test",
	"dummy-c": "https://c.example.test",
}


def _dummy(letter: str, order: int):
	return registry.AppEntry(
		key=f"dummy-{letter}",
		title=f"Dummy {letter.upper()} (test only)",
		logo="",
		route=f"/dummy-{letter}/home",
		order=order,
		app="frappe",
		owns=(f"dummy_{letter}_pkg",),
		access_role=f"NXERP Access: Dummy {letter.upper()}",
		path_prefixes=(f"/dummy-{letter}",),
		test_only=True,
	)


DUMMIES = tuple(_dummy(letter, 60 + i) for i, letter in enumerate("abc"))

# absolute URLs that an attacker (or a typo) might send; none may ever be honoured for a registered peer
CROSS_ORIGIN_HOSTILE = [
	"https://evil.test@hd.example.test/helpdesk/home",  # userinfo: the browser would go to hd.example.test but the text starts with evil
	"https://hd.example.test@evil.test/helpdesk/home",  # userinfo: the browser goes to evil.test
	"https://hd.example.test.evil.test/helpdesk/home",  # suffix trick
	"https://evilhd.example.test/helpdesk/home",
	"https://hd.example.test:8443/helpdesk/home",  # port trick
	"https://hd.example.test:443/helpdesk/home",  # explicit default port is not the registered origin
	"https://hd.example.test./helpdesk/home",  # trailing dot
	"https://hd.exаmple.test/helpdesk/home",  # noqa: RUF001  (Cyrillic a, a look-alike)
	"https://hd.example.test%2f@evil.test/helpdesk/home",
	"https://hd%2eexample.test/helpdesk/home",  # percent-encoded dot in the host
	"https://hd.example.test\\@evil.test/helpdesk/home",  # backslash
	"https://hd.example.test\\evil.test/",
	"http://hd.example.test/helpdesk/home",  # http is refused outside developer_mode
	"ftp://hd.example.test/helpdesk/home",
	"//hd.example.test/helpdesk/home",  # scheme-relative
	"https:hd.example.test/helpdesk/home",
	"https:///hd.example.test/helpdesk/home",
	"https://evil.test/helpdesk/home",
	"https://hd.example.test.evil.test",
	"javascript:alert(1)",
	"JaVaScRiPt://hd.example.test/%0aalert(1)",
	"data:text/html,hd.example.test",
	"https://hd.example.test/helpdesk/home\r\nSet-Cookie: x=1",
	"https://hd.example.test/%0d%0aLocation:%20https://evil.test",
	"https://hd.example.test/helpdesk/\x00",
	"https://",
	"https://@",
	"https://hd.example.test@",
]


def make_peer(app_key: str, origin: str, enabled: int = 1):
	doc = frappe.get_doc(
		{
			"doctype": "NXERP Peer",
			"app_key": app_key,
			"origin": origin,
			"internal_url": f"http://{app_key}-backend:8000",
			"site_name": f"{app_key}.example.test",
			"api_key": "fake-key",
			"enabled": enabled,
		}
	)
	doc.api_secret = "fake-secret"  # fake data
	doc.insert(ignore_permissions=True)
	return doc


def identity_site():
	"""Context: this site is an identity site and the registry holds the five apps."""
	stack = ExitStack()
	stack.enter_context(patch.dict(frappe.conf, {"nxerp_site_role": "identity"}))
	stack.enter_context(patch.object(registry, "get_registry", return_value=(*registry.APPS, *DUMMIES)))
	return stack


class IdentityCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		purge_test_users()
		cls.created = []

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		delete_users(cls.created)
		frappe.db.rollback()
		super().tearDownClass()

	def setUp(self):
		"""The roles and the five peers, rebuilt for each test (a test run may roll back between tests)."""
		super().setUp()
		frappe.set_user("Administrator")
		for entry in (*registry.APPS, *DUMMIES):
			if not frappe.db.exists("Role", entry.access_role):
				frappe.get_doc({"doctype": "Role", "role_name": entry.access_role, "desk_access": 0}).insert(
					ignore_permissions=True
				)
		with patch.object(registry, "get_registry", return_value=(*registry.APPS, *DUMMIES)):
			for key, origin in PEER_ORIGINS.items():
				if not frappe.db.exists("NXERP Peer", key):
					make_peer(key, origin)

	def user(self, *roles):
		# Frappe makes a user a System User only when one of their roles gives desk access: the access roles do not, so add a plain one
		doc = make_user(unique_email("idp"), [PLAIN_DESK_ROLE, *roles])
		self.created.append(doc.name)
		return doc.name


class TestIdentitySiteRegistry(IdentityCase):
	def test_with_no_site_role_nothing_changes_even_when_peers_exist(self):
		self.assertEqual(registry.site_role(), "")
		self.assertEqual(registry.active_entries(), registry.installed_entries())
		self.assertEqual(registry.allowed_origins(), frozenset())
		self.assertTrue(all(e.origin == "" for e in registry.active_entries()))
		for entry in (
			registry.installed_entries()
		):  # none on a site where only the platform is installed; fine either way
			self.assertEqual(access.app_url(entry), entry.route)
		self.assertEqual(access.app_url(DUMMIES[0]), DUMMIES[0].route)

	def test_an_unknown_site_role_is_the_same_as_none(self):
		for value in ("Identity", "admin", 1, None, ["identity"], ""):
			with patch.dict(frappe.conf, {"nxerp_site_role": value}):
				self.assertEqual(registry.site_role(), "", repr(value))
				self.assertEqual(registry.allowed_origins(), frozenset(), repr(value))
				self.assertEqual(registry.active_entries(), registry.installed_entries(), repr(value))

	def test_an_app_site_offers_its_installed_apps_only(self):
		with patch.dict(frappe.conf, {"nxerp_site_role": "app"}):
			self.assertEqual(registry.active_entries(), registry.installed_entries())

	def test_an_identity_site_offers_exactly_the_apps_with_an_enabled_peer_and_their_origins(self):
		with identity_site():
			active = {e.key: e for e in registry.active_entries()}
			self.assertEqual(set(active), set(PEER_ORIGINS))
			self.assertEqual({k: e.origin for k, e in active.items()}, PEER_ORIGINS)
			self.assertEqual(registry.allowed_origins(), frozenset(PEER_ORIGINS.values()))
			orders = [e.order for e in registry.active_entries()]
			self.assertEqual(orders, sorted(orders))
			self.assertEqual(registry.active_entry("dummy-b").origin, "https://b.example.test")
			self.assertEqual(registry.entry_for_origin("https://b.example.test").key, "dummy-b")
			self.assertIsNone(registry.entry_for_origin("https://b.example.test.evil.test"))
			self.assertIsNone(registry.entry_for_origin(""))

	def test_a_disabled_peer_is_not_active_and_its_origin_is_not_allowed(self):
		with identity_site():
			frappe.db.set_value("NXERP Peer", "dummy-b", "enabled", 0)
			try:
				self.assertNotIn("dummy-b", {e.key for e in registry.active_entries()})
				self.assertNotIn("https://b.example.test", registry.allowed_origins())
				self.assertEqual(len(registry.allowed_origins()), 4)
			finally:
				frappe.db.set_value("NXERP Peer", "dummy-b", "enabled", 1)

	def test_origins_are_normalised_strictly(self):
		cases = {
			"https://hd.example.test": "https://hd.example.test",
			"HTTPS://HD.Example.TEST": "https://hd.example.test",
			"https://hd.example.test/": "https://hd.example.test",
			"https://hd.example.test:8443": "https://hd.example.test:8443",
			"http://hd.example.test": "",  # http only under developer_mode
			"https://hd.example.test/path": "",
			"https://hd.example.test?x=1": "",
			"https://user@hd.example.test": "",
			"https://hd.example.test.": "",
			"https://hd.example.test:99999": "",
			"https://hd.exаmple.test": "",  # noqa: RUF001  (Cyrillic a)
			"https://hd%2eexample.test": "",
			"//hd.example.test": "",
			"javascript:alert(1)": "",
			" https://hd.example.test": "",
			"": "",
			None: "",
			7: "",
		}
		for raw, expected in cases.items():
			self.assertEqual(registry.normalise_origin(raw), expected, repr(raw))
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			self.assertEqual(registry.normalise_origin("http://hd.example.test"), "http://hd.example.test")

	def test_a_peer_must_name_a_known_app_and_a_clean_origin(self):
		for app_key, origin in (
			("nonexistent-app", "https://x.example.test"),
			("helpdesk", "https://user@x.example.test"),
		):
			with self.assertRaises(frappe.ValidationError, msg=f"{app_key} {origin}"):
				frappe.get_doc({"doctype": "NXERP Peer", "app_key": app_key, "origin": origin}).insert(
					ignore_permissions=True
				)

	def test_the_peer_secrets_are_passwords_read_only_with_get_decrypted_password(self):
		from nxerp.nxerp_platform.doctype.nxerp_peer.nxerp_peer import secret

		with patch.object(registry, "get_registry", return_value=(*registry.APPS, *DUMMIES)):
			self.assertEqual(secret("dummy-a"), "fake-secret")
		self.assertEqual(secret("no-such-peer"), "")
		fields = {f.fieldname: f.fieldtype for f in frappe.get_meta("NXERP Peer").fields}
		self.assertEqual((fields["api_secret"], fields["webhook_secret"]), ("Password", "Password"))
		self.assertNotEqual(frappe.db.get_value("NXERP Peer", "dummy-a", "api_secret"), "fake-secret")

	def test_five_apps_the_gate_the_tiles_and_the_landing(self):
		a_and_c = self.user("NXERP Access: Dummy A", "NXERP Access: Dummy C")
		hd = self.user("NXERP Access: Helpdesk")
		nothing = self.user()
		with identity_site():
			tiles = access.get_user_apps(a_and_c)
			self.assertEqual([e.key for e in tiles], ["dummy-a", "dummy-c"])
			landing = access.resolve_landing(a_and_c)
			self.assertEqual(landing["mode"], "launcher")
			self.assertEqual(landing["destination"], access.LAUNCHER_ROUTE)
			self.assertEqual(
				[x["route"] for x in landing["apps"]],
				["https://a.example.test/dummy-a/home", "https://c.example.test/dummy-c/home"],
			)
			self.assertEqual(
				access.resolve_landing(hd)["destination"], "https://hd.example.test/helpdesk/home"
			)
			self.assertEqual(access.get_user_apps(nothing), [])
			self.assertEqual(access.resolve_landing(nothing)["mode"], "none")
			self.assertTrue(access.can_access_app(a_and_c, "dummy-c"))
			self.assertFalse(access.can_access_app(a_and_c, "dummy-b"))
			self.assertFalse(access.can_access_app(hd, "dummy-a"))
			self.assertEqual(len(access.get_user_apps("Administrator")), 5)
			frappe.set_user(a_and_c)
			try:
				self.assertEqual(
					[t["route"] for t in launcher.get_apps()],
					["https://a.example.test/dummy-a/home", "https://c.example.test/dummy-c/home"],
				)
			finally:
				frappe.set_user("Administrator")


class TestCrossOriginRouting(IdentityCase):
	def test_a_registered_origin_is_kept_and_normalised_on_an_identity_site(self):
		with identity_site():
			self.assertEqual(
				routing.safe_target("https://hd.example.test/helpdesk/home"),
				"https://hd.example.test/helpdesk/home",
			)
			self.assertEqual(
				routing.safe_target("HTTPS://HD.EXAMPLE.TEST/helpdesk/tickets/1?view=open"),
				"https://hd.example.test/helpdesk/tickets/1?view=open",
			)
			self.assertEqual(routing.safe_target("https://hd.example.test"), "https://hd.example.test/")
			self.assertEqual(
				routing.safe_target("https://hd.example.test/helpdesk/../desk"),
				"https://hd.example.test/desk",
			)

	def test_every_cross_origin_payload_is_refused_even_for_a_registered_peer(self):
		with identity_site():
			for raw in CROSS_ORIGIN_HOSTILE:
				self.assertIsNone(routing.safe_target(raw), repr(raw))

	def test_the_original_hostile_payloads_are_still_refused_with_peers_registered(self):
		with identity_site():
			for raw in HOSTILE:
				result = routing.safe_target(raw)
				if result is None:
					continue
				parts = urlsplit(result)
				self.assertEqual((parts.scheme, parts.netloc), ("", ""), repr(raw))
				self.assertTrue(result.startswith("/") and not result.startswith("//"), repr(raw))

	def test_with_no_site_role_no_absolute_url_is_ever_honoured(self):
		for origin in PEER_ORIGINS.values():
			self.assertIsNone(routing.safe_target(f"{origin}/helpdesk/home"), origin)
		with patch.dict(frappe.conf, {"nxerp_site_role": "bogus"}):
			self.assertIsNone(routing.safe_target("https://hd.example.test/helpdesk/home"))

	def test_http_is_accepted_only_for_a_registered_origin_under_developer_mode(self):
		with identity_site():
			self.assertIsNone(routing.safe_target("http://hd.example.test/helpdesk/home"))
			frappe.db.set_value(
				"NXERP Peer", "helpdesk", "origin", "http://hd.example.test", update_modified=False
			)
			try:
				with patch.dict(frappe.conf, {"developer_mode": 1}):
					self.assertEqual(
						routing.safe_target("http://hd.example.test/helpdesk/home"),
						"http://hd.example.test/helpdesk/home",
					)
					self.assertIsNone(routing.safe_target("http://evil.test/helpdesk/home"))
			finally:
				frappe.db.set_value(
					"NXERP Peer", "helpdesk", "origin", "https://hd.example.test", update_modified=False
				)

	def test_an_absolute_target_is_authorised_only_for_the_apps_the_user_holds(self):
		hd = self.user("NXERP Access: Helpdesk")
		with identity_site():
			ok = routing.safe_target("https://hd.example.test/helpdesk/home")
			self.assertEqual(routing.authorised_target(hd, ok), ok)
			self.assertIsNone(
				routing.authorised_target(hd, routing.safe_target("https://erp.example.test/desk/home"))
			)
			self.assertIsNone(
				routing.authorised_target(hd, routing.safe_target("https://hd.example.test/desk/home"))
			)
			self.assertIsNone(routing.authorised_target("Guest", ok))
			self.assertEqual(
				routing.route(hd, "https://erp.example.test/desk/home"),
				"https://hd.example.test/helpdesk/home",
			)
			self.assertEqual(
				routing.route(hd, "https://hd.example.test/helpdesk/tickets"),
				"https://hd.example.test/helpdesk/tickets",
			)

	def test_the_five_apps_all_route_to_their_own_origin(self):
		everyone = self.user(*(e.access_role for e in (*registry.APPS, *DUMMIES)))
		with identity_site():
			for entry in registry.active_entries():
				target = f"{PEER_ORIGINS[entry.key]}{entry.route}"
				self.assertEqual(routing.route(everyone, target), target, entry.key)
			self.assertEqual(access.resolve_landing(everyone)["mode"], "launcher")
			self.assertEqual(len(access.resolve_landing(everyone)["apps"]), 5)
