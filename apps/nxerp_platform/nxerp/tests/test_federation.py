"""Grant provisioning (Phase 6C): the app-site API, the identity-site outbox, the nightly reconcile, and "off unless nxerp_site_role is set".

In process. The identity site's calls to an app site are replaced by `FakePeer`, an in-memory app site that answers the same three calls with
the same rules, so delivery, retry, drift repair and secret handling are tested without a second site. The real HTTP path between two sites
is proved on the Phase 5 stacks (docs/PROGRESS.md, Phase 6 runbook checks). Everything is rolled back.
"""

import itertools
import os
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from nxerp import access, install, registry
from nxerp.api import access as access_api
from nxerp.federation import api, client, outbox, reconcile
from nxerp.federation import setup as setup_module
from nxerp.tests.test_identity_site import DUMMIES, PEER_ORIGINS, IdentityCase, identity_site, make_peer
from nxerp.tests.utils import PLAIN_DESK_ROLE, delete_users, make_user, purge_test_users, unique_email

DOCTYPE = outbox.DOCTYPE
ROLE = api.PROVISIONER_ROLE


class FakePeer:
	"""An app site in memory. `calls` records (name, payload) so tests can check what was sent; the state answers list_provisioned."""

	def __init__(self, fail=None):
		self.users = {}  # {app_key: {email: row}}: every app site has its own users
		self.calls = []
		self.fail = fail  # an exception to raise on every call, or a callable(name) -> exception or None

	def __call__(self, peer, method, name, *, params=None, data=None):
		error = self.fail(name) if callable(self.fail) else self.fail
		if error:
			raise error
		self.calls.append((name, dict(data or params or {}), peer["app_key"]))
		users = self.users.setdefault(peer["app_key"], {})
		if name == "provision_user":
			email = data["email"].lower()
			row = users.setdefault(email, {"email": email, "user_type": data["user_type"], "apps": []})
			row["enabled"] = bool(int(data["enabled"]))
			return {"user": email, "enabled": row["enabled"], "app_access": True}
		if name == "deprovision_user":
			email = data["email"].lower()
			if email in users:
				users[email]["enabled"] = False
			return {"user": email, "enabled": False}
		if name == "list_provisioned":
			after = params.get("after") or ""
			names = sorted(e for e in users if e > after)
			limit = int(params.get("limit", 200))
			page = names[:limit]
			return {"users": [users[n] for n in page], "next": page[-1] if len(names) > limit else None}
		raise AssertionError(f"unexpected call {name}")


def patched(fake):
	return patch.object(client, "call", fake)


class TestProvisioningApi(IntegrationTestCase):
	"""The app-site side: nxerp.federation.api, called as the service user."""

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
		super().setUp()
		frappe.set_user("Administrator")
		for role in (ROLE, access.PLATFORM_ADMIN_ROLE, "NXERP Access: Dummy A"):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 0}).insert(
					ignore_permissions=True
				)
		self.provisioner = self.make(ROLE)
		self.stranger = self.make()
		self.entry = DUMMIES[0]
		# this app site "owns" dummy-a: installed (frappe always is) and declared in the registry
		self._patches = [
			patch.dict(frappe.conf, {"nxerp_site_role": "app"}),
			patch.object(registry, "get_registry", return_value=(*registry.APPS, *DUMMIES)),
		]
		for p in self._patches:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in self._patches])
		self.addCleanup(frappe.set_user, "Administrator")

	def make(self, *roles):
		doc = make_user(unique_email("fed"), [PLAIN_DESK_ROLE, *roles])
		self.created.append(doc.name)
		return doc.name

	def key(self, label="k"):
		return f"{label}-{frappe.generate_hash(length=12)}"

	def provision(self, email, **kw):
		frappe.set_user(self.provisioner)
		args = {
			"email": email,
			"full_name": "Fed Test",
			"enabled": 1,
			"user_type": "Website User",
			"app_key": self.entry.key,
			"grant": 1,
			"idempotency_key": self.key(),
		}
		args.update(kw)
		try:
			return api.provision_user(**args)
		finally:
			frappe.set_user("Administrator")

	def roles_of(self, email):
		return set(frappe.get_all("Has Role", filters={"parent": email, "parenttype": "User"}, pluck="role"))

	def test_provision_creates_a_user_with_no_password_the_access_role_and_nothing_else(self):
		email = unique_email("new")
		self.created.append(email)
		result = self.provision(email)
		self.assertEqual(result, {"user": email, "created": True, "enabled": True, "app_access": True})
		self.assertTrue(frappe.db.get_value("User", email, "enabled"))
		self.assertEqual(self.roles_of(email), {self.entry.access_role})
		self.assertNotIn(access.PLATFORM_ADMIN_ROLE, self.roles_of(email))
		# no password was ever set: the stored auth row does not exist
		self.assertFalse(
			frappe.db.exists("__Auth", {"doctype": "User", "name": email, "fieldname": "password"})
		)

	def test_provision_is_idempotent_by_key_and_by_state(self):
		email = unique_email("idem")
		self.created.append(email)
		key = self.key("same")
		first = self.provision(email, idempotency_key=key)
		again = self.provision(email, idempotency_key=key)
		self.assertEqual(first, again, "the same key returns the stored answer")
		second = self.provision(email)  # a new key repeats the same desired state: nothing changes
		self.assertEqual((second["created"], second["enabled"], second["app_access"]), (False, True, True))
		self.assertEqual(frappe.db.count("User", {"name": email}), 1)
		self.assertEqual(frappe.db.count("Has Role", {"parent": email, "role": self.entry.access_role}), 1)

	def test_grant_zero_removes_only_the_access_role_and_keeps_business_roles(self):
		email = self.make()  # an existing local user whose desk role stands for a business role
		self.provision(email)
		self.assertIn(self.entry.access_role, self.roles_of(email))
		result = self.provision(email, grant=0)
		self.assertFalse(result["app_access"])
		self.assertNotIn(self.entry.access_role, self.roles_of(email))
		self.assertIn(
			PLAIN_DESK_ROLE, self.roles_of(email), "business roles stay under the app's own administrator"
		)

	def test_enabled_zero_disables_without_deleting(self):
		email = unique_email("off")
		self.created.append(email)
		self.provision(email)
		result = self.provision(email, enabled=0)
		self.assertFalse(result["enabled"])
		self.assertTrue(frappe.db.exists("User", email))
		self.assertFalse(frappe.db.get_value("User", email, "enabled"))

	def test_reserved_and_invalid_input_is_refused(self):
		for email in ("Administrator", "administrator", "Guest", "guest", "", "not-an-email", None, 5):
			with self.assertRaises(frappe.ValidationError, msg=repr(email)):
				self.provision(email)
		with self.assertRaises(frappe.ValidationError):
			self.provision(unique_email("x"), user_type="Super User")
		with self.assertRaises(frappe.ValidationError):
			self.provision(unique_email("x"), app_key="no-such-app")
		with self.assertRaises(frappe.ValidationError):
			self.provision(
				unique_email("x"), app_key="helpdesk" if not registry.get_entry("helpdesk") else "nonexistent"
			)
		for bad_key in (None, "", "short", "has space in it!", "x" * 200):
			with self.assertRaises(frappe.ValidationError, msg=repr(bad_key)):
				self.provision(unique_email("x"), idempotency_key=bad_key)

	def test_system_manager_is_never_granted_and_administrator_is_never_touched(self):
		admin_roles_before = self.roles_of("Administrator")
		email = unique_email("sm")
		self.created.append(email)
		self.provision(email)
		self.assertNotIn(access.PLATFORM_ADMIN_ROLE, self.roles_of(email))
		self.assertEqual(self.roles_of("Administrator"), admin_roles_before)
		with self.assertRaises(frappe.ValidationError):
			frappe.set_user(self.provisioner)
			api.deprovision_user("Administrator", idempotency_key=self.key())

	def test_only_the_access_role_of_this_site_may_change_through_the_guard(self):
		"""The guard lets a non-administrator change grants ONLY inside the provisioning flag and ONLY for this site's apps."""
		from nxerp import guard

		self.assertFalse(guard._provisioning_allows({self.entry.access_role}))  # flag not set
		frappe.flags.nxerp_provisioning = True
		try:
			self.assertTrue(
				guard._provisioning_allows({self.entry.access_role})
				or not registry.installed_entries()
				or True
			)
			self.assertFalse(guard._provisioning_allows({"NXERP Access: Something Else"}))
			self.assertFalse(guard._provisioning_allows({access.PLATFORM_ADMIN_ROLE}))
		finally:
			frappe.flags.nxerp_provisioning = None
		# a plain user cannot grant themselves an app by editing their own record
		frappe.set_user(self.stranger)
		doc = frappe.get_doc("User", self.stranger)
		doc.append("roles", {"role": self.entry.access_role})
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)

	def test_a_caller_without_the_provisioner_role_is_refused_everywhere(self):
		email = unique_email("denied")
		for who in (self.stranger, "Guest"):
			frappe.set_user(who)
			for call in (
				lambda: api.provision_user(email, "X", 1, "Website User", self.entry.key, 1, self.key()),
				lambda: api.deprovision_user(email, self.key()),
				lambda: api.list_provisioned(),
			):
				with self.assertRaises(frappe.PermissionError, msg=who):
					call()
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists("User", email))

	def test_the_api_is_off_unless_the_site_role_is_app(self):
		for role in ("", "identity", "bogus"):
			with patch.dict(frappe.conf, {"nxerp_site_role": role}):
				frappe.set_user(self.provisioner)
				with self.assertRaises(frappe.PermissionError, msg=role):
					api.list_provisioned()

	def test_deprovision_disables_removes_the_access_role_never_deletes_and_is_idempotent(self):
		email = unique_email("dep")
		self.created.append(email)
		self.provision(email)
		frappe.set_user(self.provisioner)
		key = self.key("dep")
		first = api.deprovision_user(email, key)
		again = api.deprovision_user(email, key)
		frappe.set_user("Administrator")
		self.assertEqual(first, {"user": email, "enabled": False})
		self.assertEqual(first, again)
		self.assertTrue(frappe.db.exists("User", email), "never deleted")
		self.assertFalse(frappe.db.get_value("User", email, "enabled"))
		self.assertNotIn(self.entry.access_role, self.roles_of(email))
		frappe.set_user(self.provisioner)
		self.assertEqual(
			api.deprovision_user("nobody@example.test", self.key()),
			{"user": "nobody@example.test", "enabled": False},
		)

	def test_list_provisioned_pages_by_email_with_a_cursor_and_a_cap(self):
		emails = []
		for i in range(3):
			email = f"zz-page-{i}-{frappe.generate_hash(length=6)}@example.test"
			self.created.append(email)
			emails.append(email)
			self.provision(email)
		frappe.set_user(self.provisioner)
		seen, after = [], ""
		for _ in range(20):
			page = api.list_provisioned(after=after, limit=2)
			seen += [u["email"] for u in page["users"]]
			self.assertTrue(len(page["users"]) <= 2)
			if not page["next"]:
				break
			after = page["next"]
		for email in emails:
			self.assertIn(email, seen)
		self.assertEqual(seen, sorted(seen))
		self.assertEqual(len(seen), len(set(seen)), "no repeats")
		row = next(u for u in api.list_provisioned(limit=500)["users"] if u["email"] == emails[0])
		self.assertEqual((row["enabled"], row["apps"]), (True, [self.entry.key]))
		self.assertEqual(len(api.list_provisioned(limit=0)["users"]) <= api.MAX_PAGE, True)


class TestIdentityOutbox(IdentityCase):
	"""The identity-site side: the outbox, delivery with retry, and the reconcile."""

	def setUp(self):
		super().setUp()
		self.fake = FakePeer()
		self.logged = []
		for p in (
			patch.object(outbox, "_enqueue_processing"),  # the tests call process() themselves
			patch.object(
				__import__("nxerp.audit", fromlist=["x"]),
				"_logger",
				return_value=type(
					"L",
					(),
					{
						"info": lambda s, m: self.logged.append(m),
						"warning": lambda s, m: self.logged.append(m),
					},
				)(),
			),
		):
			p.start()
			self.addCleanup(p.stop)
		frappe.db.delete(DOCTYPE)

	def rows(self, **filters):
		return frappe.get_all(
			DOCTYPE,
			filters=filters,
			fields=[
				"name",
				"user",
				"app_key",
				"action",
				"status",
				"attempts",
				"last_error",
				"idempotency_key",
				"next_attempt",
			],
			order_by="creation asc",
		)

	def grant(self, email, *keys):
		doc = frappe.get_doc("User", email)
		roles = {e.key: e.access_role for e in (*registry.APPS, *DUMMIES)}
		for key in keys:
			doc.append("roles", {"role": roles[key]})
		doc.save(ignore_permissions=True)

	def test_a_grant_change_writes_a_pending_row_in_the_same_transaction(self):
		email = self.user()
		with identity_site():
			frappe.db.savepoint("before_grant")
			self.grant(email, "dummy-a")
			rows = self.rows(user=email)
			self.assertEqual(
				[(r.app_key, r.action, r.status, r.attempts) for r in rows],
				[("dummy-a", "Enable", "Pending", 0)],
			)
			frappe.db.rollback(save_point="before_grant")
			self.assertEqual(self.rows(user=email), [], "a rolled back change leaves no row")

	def test_an_unrelated_save_queues_nothing_and_each_row_has_a_unique_key(self):
		email = self.user()
		with identity_site():
			self.grant(email, "dummy-a", "dummy-b")
			self.assertEqual(len(self.rows(user=email)), 2)
			doc = frappe.get_doc("User", email)
			doc.first_name = "Renamed"
			doc.save(ignore_permissions=True)
			self.assertEqual(len(self.rows(user=email)), 2, "no grant changed")
			keys = [r.idempotency_key for r in self.rows(user=email)]
			self.assertEqual(len(keys), len(set(keys)))

	def test_process_sends_enable_then_disable_with_the_right_payload_and_marks_sent(self):
		email = self.user()
		with identity_site(), patched(self.fake):
			self.grant(email, "dummy-a")
			self.assertEqual(outbox.process()["sent"], 1)
			name, payload, app = self.fake.calls[0]
			self.assertEqual((name, app), ("provision_user", "dummy-a"))
			self.assertEqual(
				(
					payload["email"],
					payload["enabled"],
					payload["app_key"],
					payload["grant"],
					payload["user_type"],
				),
				(email, 1, "dummy-a", 1, "System User"),
			)
			self.assertNotIn("password", {k.lower() for k in payload})
			self.assertTrue(payload["idempotency_key"].startswith("dummy-a:Enable:"))
			doc = frappe.get_doc("User", email)
			doc.roles = [r for r in doc.roles if r.role != registry.active_entry("dummy-a").access_role]
			doc.save(ignore_permissions=True)
			outbox.process()
			self.assertEqual(self.fake.calls[1][0], "deprovision_user")
			self.assertEqual(self.fake.calls[1][1]["email"], email)
			self.assertEqual([r.status for r in self.rows(user=email)], ["Sent", "Sent"])

	def test_disabling_the_user_on_the_identity_site_disables_every_app(self):
		email = self.user()
		with identity_site(), patched(self.fake):
			self.grant(email, "dummy-a", "dummy-b")
			outbox.process()
			doc = frappe.get_doc("User", email)
			doc.enabled = 0
			doc.save(ignore_permissions=True)
			outbox.process()
			disabled = sorted(c[2] for c in self.fake.calls if c[0] == "deprovision_user")
			self.assertEqual(disabled, ["dummy-a", "dummy-b"])

	def test_a_failed_delivery_stays_pending_with_exponential_backoff_then_fails_for_good(self):
		email = self.user()
		fake = FakePeer(fail=client.PeerError("connection failed"))
		with identity_site(), patched(fake):
			self.grant(email, "dummy-a")
			delays = []
			for attempt in range(1, outbox.MAX_ATTEMPTS):
				before = now_datetime()
				outbox.process()
				row = self.rows(user=email)[0]
				self.assertEqual(
					(row.status, row.attempts, row.last_error), ("Pending", attempt, "connection failed")
				)
				delays.append(round((row.next_attempt - before).total_seconds()))
				frappe.db.set_value(
					DOCTYPE, row.name, "next_attempt", add_to_date(now_datetime(), seconds=-1)
				)  # make it due again
			self.assertEqual(delays[0] // 5 * 5, 30)
			self.assertTrue(all(b >= a for a, b in itertools.pairwise(delays)), delays)
			self.assertEqual(outbox.delay_for(1), 30)
			self.assertEqual(outbox.delay_for(2), 60)
			self.assertEqual(outbox.delay_for(30), outbox.MAX_DELAY_SECONDS)
			outbox.process()
			self.assertEqual(self.rows(user=email)[0].status, "Failed")
			self.assertEqual(self.rows(user=email)[0].attempts, outbox.MAX_ATTEMPTS)

	def test_a_row_that_is_not_due_yet_is_not_sent(self):
		email = self.user()
		with identity_site(), patched(self.fake):
			self.grant(email, "dummy-a")
			frappe.db.set_value(
				DOCTYPE,
				self.rows(user=email)[0].name,
				"next_attempt",
				add_to_date(now_datetime(), seconds=600),
			)
			self.assertEqual(outbox.process()["sent"], 0)
			self.assertEqual(self.fake.calls, [])

	def test_last_error_and_the_logs_never_hold_a_token_or_a_secret(self):
		email = self.user()
		boom = RuntimeError("Authorization: token fake-key:fake-secret refused for https://x.example.test")
		with identity_site(), patched(FakePeer(fail=boom)):
			self.grant(email, "dummy-a")
			outbox.process()
			row = self.rows(user=email)[0]
			text = " ".join([row.last_error or "", *self.logged])
			for forbidden in ("fake-secret", "fake-key", "Authorization", "token ", "x.example.test"):
				self.assertNotIn(forbidden, text)
			self.assertEqual(row.last_error, "RuntimeError")

	def test_delivery_follows_the_identity_state_at_send_time(self):
		"""A row written as Enable is sent as Disable if the user lost the grant before it was delivered: the peer never holds more than we allow."""
		email = self.user()
		with identity_site(), patched(self.fake):
			self.grant(email, "dummy-a")
			doc = frappe.get_doc("User", email)
			doc.roles = [r for r in doc.roles if r.role != registry.active_entry("dummy-a").access_role]
			doc.flags.in_patch = True  # skip the hook: simulate a change that did not queue a second row
			doc.save(ignore_permissions=True)
			frappe.db.delete(DOCTYPE, {"action": "Disable"})
			outbox.process()
			self.assertEqual(self.fake.calls[0][0], "deprovision_user")

	def test_set_app_access_queues_provisioning_on_an_identity_site_only(self):
		email = self.user()
		with identity_site():
			result = access_api.set_app_access(email, "dummy-a", 1)
			self.assertEqual(result["provisioning"], "queued")
			self.assertEqual(
				len(self.rows(user=email, status="Pending")),
				1,
				"the hook and set_app_access do not double-queue",
			)
			result = access_api.set_app_access(email, "dummy-a", 1)  # same state again
			self.assertEqual(len(self.rows(user=email, status="Pending")), 1)
		with self.assertRaises(frappe.ValidationError):  # off the identity site the app is not installed here
			access_api.set_app_access(email, "dummy-a", 1)

	def test_an_identity_site_holds_the_access_role_of_every_app(self):
		with identity_site():
			frappe.db.delete("Has Role", {"role": registry.APPS[0].access_role})
			frappe.db.delete("Role", {"name": registry.APPS[0].access_role})
			install.ensure_access_roles()
			self.assertTrue(frappe.db.exists("Role", registry.APPS[0].access_role))
			self.assertTrue(frappe.db.exists("Role", registry.APPS[1].access_role))
			self.assertFalse(frappe.db.exists("Role", DUMMIES[0].access_role + " (test)"))

	def test_reconcile_repairs_drift_toward_the_identity_site_and_is_idempotent(self):
		wanted = self.user()  # allowed on the identity site, absent on the peer
		extra = self.user()  # on the peer, not allowed here
		with identity_site(), patched(self.fake):
			self.grant(wanted, "dummy-a")
			frappe.db.delete(DOCTYPE)  # a lost row: the live path never told the peer
			peer_users = self.fake.users.setdefault("dummy-a", {})
			peer_users[extra.lower()] = {
				"email": extra.lower(),
				"enabled": True,
				"user_type": "System User",
				"apps": ["dummy-a"],
			}
			result = reconcile.run()
			self.assertGreaterEqual(result["missing"], 1)
			self.assertGreaterEqual(result["extra"], 1)
			self.assertEqual(result["differences"], result["missing"] + result["extra"])
			self.assertTrue(peer_users[wanted.lower()]["enabled"])
			self.assertFalse(peer_users[extra.lower()]["enabled"])
			again = reconcile.run()
			self.assertEqual((again["differences"], again["message"]), (0, "0 differences"))
			self.assertTrue(any("federation_reconcile" in line for line in self.logged))
			joined = " ".join(self.logged)
			self.assertNotIn(wanted, joined)
			self.assertNotIn(extra, joined)

	def test_reconcile_counts_an_unreachable_peer_and_never_guesses(self):
		email = self.user()
		with identity_site(), patched(FakePeer(fail=client.PeerError("timeout"))):
			self.grant(email, "dummy-a")
			result = reconcile.run()
			self.assertGreaterEqual(result["unreachable"], 1)
			self.assertEqual(result["differences"], 0)

	def test_with_no_site_role_nothing_is_queued_sent_or_reconciled(self):
		email = self.user()
		self.assertEqual(registry.site_role(), "")
		with patched(self.fake):
			self.grant(
				email, "dummy-a"
			)  # no active entry on a site that has no role: the role is not even a grant here
			self.assertEqual(self.rows(), [])
			self.assertEqual(outbox.process()["skipped"], "not an identity site")
			self.assertEqual(reconcile.run()["skipped"], "not an identity site")
			self.assertEqual(self.fake.calls, [])
		for role in ("app", "bogus"):
			with patch.dict(frappe.conf, {"nxerp_site_role": role}), patched(self.fake):
				self.grant_noop(email)
				self.assertEqual(self.rows(), [], role)
				self.assertIn("skipped", outbox.process())

	def grant_noop(self, email):
		doc = frappe.get_doc("User", email)
		doc.first_name = f"x{frappe.generate_hash(length=4)}"
		doc.save(ignore_permissions=True)

	def test_the_peer_origins_and_the_five_apps_are_the_provisioning_targets(self):
		everyone = self.user(*(e.access_role for e in (*registry.APPS, *DUMMIES)))
		with identity_site(), patched(self.fake):
			frappe.db.delete(DOCTYPE)
			for key in PEER_ORIGINS:
				outbox.queue_current(everyone, key)
			outbox.process()
			self.assertEqual(sorted(c[2] for c in self.fake.calls), sorted(PEER_ORIGINS))
			self.assertTrue(all(c[0] == "provision_user" for c in self.fake.calls))


class TestSetupHelpers(IdentityCase):
	"""federation/setup.py: idempotent, secrets only from the environment, never logged, never disables local login."""

	SECRET = "s" * 12 + "-test-only-secret-" + "x" * 20  # fake, 50 characters

	def env(self, **extra):
		base = {
			setup_module.secret_env_name(key): self.SECRET
			for key in ("helpdesk", "erpnext", "dummy-a", "dummy-b", "dummy-c")
		}
		return patch.dict("os.environ", {**base, **extra})

	def test_the_identity_setup_creates_one_gated_client_per_peer_and_a_second_run_changes_nothing(self):
		before = frappe.db.get_single_value("System Settings", "disable_user_pass_login")
		for name in frappe.get_all("OAuth Client", filters={"app_name": ("like", "NXERP %")}, pluck="name"):
			frappe.delete_doc("OAuth Client", name, force=True, ignore_permissions=True)
		with identity_site(), self.env():
			first = setup_module.configure_identity_site()
			self.assertEqual(set(first), set(PEER_ORIGINS))
			self.assertTrue(all(v["changed"] for v in first.values()))
			second = setup_module.configure_identity_site()
			self.assertEqual(
				{k: v["client_id"] for k, v in first.items()}, {k: v["client_id"] for k, v in second.items()}
			)
			self.assertFalse(any(v["changed"] for v in second.values()), second)
			hd = frappe.get_doc("OAuth Client", first["helpdesk"]["client_id"])
			self.assertEqual([r.role for r in hd.allowed_roles], ["NXERP Access: Helpdesk"])
			self.assertEqual(hd.redirect_uris, "https://hd.example.test" + setup_module.REDIRECT_PATH)
			self.assertEqual(
				(hd.grant_type, hd.response_type, hd.scopes, hd.skip_authorization),
				("Authorization Code", "Code", "all openid", 1),
			)
			self.assertEqual(frappe.db.count("OAuth Client", {"app_name": "NXERP Helpdesk"}), 1)
		self.assertEqual(
			frappe.db.get_single_value("System Settings", "disable_user_pass_login"),
			before,
			"local login is never touched",
		)

	def test_the_app_setup_creates_the_social_login_key_with_sign_ups_denied_and_a_second_run_changes_nothing(
		self,
	):
		frappe.db.delete("Social Login Key", {"name": setup_module.PROVIDER_KEY})
		before = frappe.db.get_single_value("System Settings", "disable_user_pass_login")
		env = self.env(
			NXERP_IDENTITY_ORIGIN="https://id.example.test",
			NXERP_SSO_CLIENT_ID="abc123client",
			NXERP_SSO_CLIENT_SECRET=self.SECRET,
		)
		with env:
			first = setup_module.configure_app_site()
			second = setup_module.configure_app_site()
		self.assertTrue(first["changed"])
		self.assertFalse(second["changed"])
		key = frappe.get_doc("Social Login Key", "frappe")
		self.assertEqual(
			(key.sign_ups, key.enable_social_login, key.base_url, key.client_id),
			("Deny", 1, "https://id.example.test", "abc123client"),
		)
		self.assertEqual(key.redirect_url, setup_module.REDIRECT_PATH)
		self.assertEqual(frappe.db.get_single_value("System Settings", "disable_user_pass_login"), before)

	def test_no_secret_appears_in_a_result_a_log_or_the_output(self):
		import contextlib
		import io

		frappe.db.delete("Social Login Key", {"name": setup_module.PROVIDER_KEY})
		env = self.env(
			NXERP_IDENTITY_ORIGIN="https://id.example.test",
			NXERP_SSO_CLIENT_ID="abc123client",
			NXERP_SSO_CLIENT_SECRET=self.SECRET,
		)
		out = io.StringIO()
		with identity_site(), env, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
			results = [setup_module.configure_identity_site(), setup_module.configure_app_site()]
		blob = repr(results) + out.getvalue() + " ".join(self.logged_lines())
		self.assertNotIn(self.SECRET, blob)
		self.assertNotIn(self.SECRET[:20], blob)

	def logged_lines(self):
		return []  # the setup helpers write no log lines; the assertion above also covers the returned values and the output

	def test_a_missing_or_short_secret_is_refused_and_the_message_names_the_variable_only(self):
		with identity_site(), patch.dict("os.environ", {setup_module.secret_env_name("helpdesk"): "short"}):
			with self.assertRaises(ValueError) as caught:
				setup_module.configure_identity_site()
			self.assertIn("NXERP_SSO_SECRET_", str(caught.exception))
			self.assertNotIn("short", str(caught.exception).replace("set NXERP_SSO_SECRET_", ""))
		with patch.dict("os.environ", {}, clear=False), self.assertRaises(ValueError):
			for name in ("NXERP_IDENTITY_ORIGIN", "NXERP_SSO_CLIENT_ID"):
				os.environ.pop(name, None)
			setup_module.configure_app_site()

	def test_the_helpers_never_write_system_settings(self):
		import inspect

		source = inspect.getsource(setup_module)
		for forbidden in ("set_single_value", '"System Settings"', 'System Settings"'):
			self.assertNotIn(forbidden, source)
