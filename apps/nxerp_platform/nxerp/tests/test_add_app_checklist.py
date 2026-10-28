"""The "add an app" checklist (docs/guides/how-to-add-an-app.md), exercised against the real registry code.

A dummy entry, clearly marked TEST ONLY and never shipped, is registered by substituting `registry.get_registry`
for this process (not through site config: that is cached by the web workers for up to 60 s and is for HTTP
tests). Each test asserts one promise the guide makes to someone adding HRMS, Project Management or Budget
Management, so that if the platform stops keeping a promise the guide fails loudly instead of going stale.

In process, no HTTP. Everything is rolled back; the dummy roles are deleted again.
"""

from dataclasses import replace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from nxerp import access, enforcement, install, launcher, registry, routing
from nxerp.api import access as access_api
from nxerp.tests.utils import (
	PLAIN_DESK_ROLE,
	delete_users,
	make_user,
	purge_test_users,
	unique_email,
)

KEY = "dummy-checklist"
ACCESS_ROLE = "NXERP Access: Dummy Checklist"
IMPLIED_ROLE = "Dummy Checklist Staff"  # the app's own staff role (the guide's "implied role")
PORTAL_ROLE = "Dummy Checklist Customer"  # the app's own customer role (the guide's "portal role")

# TEST ONLY: stands in for an app that is installed ("frappe" always is) and fully declared
DUMMY = registry.AppEntry(
	key=KEY,
	title="Dummy Checklist App (test only)",
	logo="/assets/frappe/images/frappe-framework-logo.svg",
	route="/dummy-checklist",
	order=90,
	app="frappe",
	owns=("dummy_checklist_pkg",),
	access_role=ACCESS_ROLE,
	implied_roles=(IMPLIED_ROLE,),
	path_prefixes=("/dummy-checklist",),
	portal_roles=(PORTAL_ROLE,),
	portal_prefixes=("/dummy-checklist/portal",),
	portal_route="/dummy-checklist/portal",
	test_only=True,
)

# TEST ONLY: declared, but its Frappe app is not installed on this site, so it must be invisible everywhere
NOT_INSTALLED = registry.AppEntry(
	key="dummy-not-installed",
	title="Dummy Not Installed (test only)",
	logo="",
	route="/dummy-not-installed",
	order=91,
	app="dummy_checklist_app_that_is_not_installed",
	owns=("dummy_not_installed_pkg",),
	access_role="NXERP Access: Dummy Not Installed",
	path_prefixes=("/dummy-not-installed",),
	test_only=True,
)


def checklist_problems(entry, others=()) -> list:
	"""The shape rules in section 2 of the guide, as code. An empty list means the entry is well formed."""
	problems = []
	if not entry.key or entry.key != entry.key.strip() or " " in entry.key:
		problems.append("key must be a stable identifier without spaces")
	if not entry.access_role.startswith("NXERP Access: "):
		problems.append("access_role must be named 'NXERP Access: <Title>'")
	if not entry.route.startswith("/"):
		problems.append("route must be a site-relative path")
	if not entry.path_prefixes or not registry.under(entry.route, entry.path_prefixes):
		problems.append(
			"route must sit under one of path_prefixes, or the gate does not cover the landing page"
		)
	if not entry.owns:
		problems.append(
			"owns must name the python package(s) of the app, or its DocTypes and methods are ungated"
		)
	if "frappe" in entry.owns or (entry.app == "frappe" and not entry.test_only):
		problems.append("Frappe Framework is not an NXERP app")
	if entry.portal_roles and not (entry.portal_prefixes and entry.portal_route):
		problems.append("portal_roles need portal_prefixes and portal_route")
	if entry.portal_route and not registry.under(entry.portal_route, entry.portal_prefixes):
		problems.append("portal_route must sit under portal_prefixes")
	for other in others:
		if other.key == entry.key:
			problems.append(f"key already used by {other.title}")
		if other.access_role == entry.access_role:
			problems.append(f"access_role already used by {other.title}")
		if set(other.owns) & set(entry.owns):
			problems.append(f"owns overlaps {other.title}")
		for prefix in entry.path_prefixes:
			if registry.under(prefix, other.path_prefixes) or registry.under(other.route, (prefix,)):
				problems.append(f"path prefix {prefix} overlaps {other.title}")
	return problems


class TestAddAppChecklist(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		purge_test_users()
		cls.real = registry.get_registry()
		cls.patcher = patch.object(registry, "get_registry", return_value=(*cls.real, DUMMY, NOT_INSTALLED))
		cls.patcher.start()

		# checklist step "the roles exist": the app's own roles are the app's business; the access role is ours
		for name, desk_access in (
			(IMPLIED_ROLE, 1),
			(PORTAL_ROLE, 0),
		):  # staff roles open Desk, customer roles do not
			if not frappe.db.exists("Role", name):
				frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": desk_access}).insert()
		install.ensure_access_roles()  # what `bench migrate` does after_migrate

		cls.created = []

		def mk(prefix, roles, **kw):
			doc = make_user(unique_email(prefix), roles, **kw)
			cls.created.append(doc.name)
			return doc.name

		cls.holder = mk("c-holder", [PLAIN_DESK_ROLE, ACCESS_ROLE])
		cls.implied = mk("c-implied", [PLAIN_DESK_ROLE, IMPLIED_ROLE])
		cls.plain = mk("c-plain", [PLAIN_DESK_ROLE])
		cls.both = mk("c-both", ["Agent Manager", ACCESS_ROLE])
		cls.portal = mk("c-portal", [PORTAL_ROLE], user_type="Website User")
		cls.website_holder = mk("c-web", [ACCESS_ROLE], user_type="Website User")
		cls.disabled_holder = mk("c-off", [PLAIN_DESK_ROLE, ACCESS_ROLE], enabled=0)
		cls.revocable = mk("c-rev", [PLAIN_DESK_ROLE, ACCESS_ROLE])

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.patcher.stop()
		delete_users(cls.created)
		frappe.db.rollback()
		for name in (ACCESS_ROLE, IMPLIED_ROLE, PORTAL_ROLE):
			if frappe.db.exists("Role", name):
				frappe.delete_doc("Role", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def keys(self, user) -> list:
		return [e.key for e in access.get_user_apps(user)]

	def route(self, user, redirect_to=None):
		with patch.object(frappe, "is_setup_complete", return_value=True):
			return routing.route(user, redirect_to)

	# --- step 2: the registry entry ------------------------------------------------------------

	def test_the_dummy_entry_follows_the_shape_rules_and_does_not_clash_with_real_apps(self):
		self.assertEqual(checklist_problems(DUMMY, others=self.real), [])

	def test_the_shape_rules_reject_the_mistakes_they_exist_for(self):
		bad = registry.AppEntry(
			key="has space",
			title="Bad",
			logo="",
			route="no-slash",
			order=1,
			app="frappe",
			owns=(),
			access_role="Dummy",
		)
		problems = " | ".join(checklist_problems(bad))
		for fragment in (
			"key must be",
			"access_role must be",
			"route must be a site-relative",
			"owns must name",
		):
			self.assertIn(fragment, problems)
		clash = " | ".join(
			checklist_problems(replace(DUMMY, order=5), others=(DUMMY,))
		)  # same key, role, owns
		for fragment in (
			"key already used",
			"access_role already used",
			"owns overlaps",
			"path prefix /dummy-checklist overlaps",
		):
			self.assertIn(fragment, clash)

	def test_the_registry_lookups_find_the_new_app(self):
		self.assertEqual(registry.get_entry(KEY), DUMMY)
		self.assertEqual(registry.entry_for_package("dummy_checklist_pkg"), DUMMY)
		self.assertEqual(registry.entry_for_path("/dummy-checklist/anything"), (DUMMY, "staff"))
		self.assertEqual(registry.entry_for_path("/dummy-checklist"), (DUMMY, "staff"))
		self.assertEqual(registry.entry_for_path("/dummy-checklistx"), (None, None))  # whole segments only

	def test_installed_entries_keep_launcher_order_with_the_new_app_last(self):
		keys = [e.key for e in registry.installed_entries()]
		self.assertEqual(keys[-1], KEY)
		orders = [e.order for e in registry.installed_entries()]
		self.assertEqual(orders, sorted(orders))

	# --- step: `bench migrate` creates the access role -----------------------------------------

	def test_ensure_access_roles_creates_the_role_once_and_without_desk_access(self):
		self.assertTrue(frappe.db.exists("Role", ACCESS_ROLE))
		install.ensure_access_roles()  # idempotent: a second migrate changes nothing
		self.assertEqual(frappe.db.count("Role", {"name": ACCESS_ROLE}), 1)
		role = frappe.db.get_value("Role", ACCESS_ROLE, ["desk_access", "is_custom"], as_dict=True)
		self.assertEqual(
			role.desk_access, 0, "holding an access role must never make a website user a system user"
		)
		self.assertEqual(role.is_custom, 1)

	def test_a_newly_declared_app_gets_its_role_on_the_next_sync(self):
		extra = replace(
			DUMMY, key="dummy-extra", access_role="NXERP Access: Dummy Extra", owns=("dummy_extra_pkg",)
		)
		self.assertFalse(frappe.db.exists("Role", extra.access_role))
		with patch.object(registry, "get_registry", return_value=(*self.real, DUMMY, extra)):
			install.ensure_access_roles()
		try:
			self.assertTrue(frappe.db.exists("Role", extra.access_role))
		finally:
			frappe.delete_doc("Role", extra.access_role, force=True, ignore_permissions=True)

	def test_an_app_that_is_not_installed_gets_no_role_and_no_visibility(self):
		self.assertFalse(frappe.db.exists("Role", NOT_INSTALLED.access_role))
		self.assertIsNone(registry.get_entry(NOT_INSTALLED.key))
		self.assertNotIn(NOT_INSTALLED.key, [e.key for e in registry.installed_entries()])
		self.assertIsNone(registry.entry_for_package("dummy_not_installed_pkg"))
		self.assertEqual(registry.entry_for_path("/dummy-not-installed/x"), (None, None))

	# --- step 3: grants ------------------------------------------------------------------------

	def test_the_resolver_grants_the_access_role_and_denies_everyone_else(self):
		self.assertIn(KEY, self.keys(self.holder))
		self.assertTrue(access.can_access_app(self.holder, KEY))
		for user in (self.plain, self.portal, self.website_holder, self.disabled_holder, "Guest"):
			self.assertNotIn(KEY, self.keys(user), user)
			self.assertFalse(access.can_access_app(user, KEY), user)

	def test_administrator_holds_every_installed_app_and_never_an_uninstalled_one(self):
		admin = self.keys("Administrator")
		self.assertIn(KEY, admin)
		self.assertNotIn(NOT_INSTALLED.key, admin)

	def test_an_implied_role_counts_as_staff_access(self):
		self.assertIn(KEY, self.keys(self.implied))

	def test_a_portal_role_is_not_staff_access(self):
		self.assertNotIn(KEY, self.keys(self.portal))
		self.assertTrue(access.can_use_portal(self.portal, KEY))
		self.assertTrue(access.is_portal_only(self.portal))
		self.assertFalse(access.can_use_portal(self.holder, KEY))

	def test_a_website_user_never_holds_staff_access_even_with_the_role(self):
		self.assertEqual(self.keys(self.website_holder), [])

	def test_granting_through_the_api_and_revoking_removes_every_role_that_confers_the_app(self):
		frappe.set_user("Administrator")
		self.assertNotIn(KEY, self.keys(self.plain))
		result = access_api.set_app_access(self.plain, KEY, 1)
		self.assertIn(KEY, result["apps"])
		self.assertIn(KEY, self.keys(self.plain))
		result = access_api.set_app_access(self.plain, KEY, 0)
		self.assertNotIn(KEY, result["apps"])

		access_api.set_app_access(self.implied, KEY, 0)  # revoking also strips the implied role
		self.assertNotIn(KEY, self.keys(self.implied))
		self.assertNotIn(IMPLIED_ROLE, frappe.get_roles(self.implied))

	def test_the_grant_api_refuses_an_uninstalled_app(self):
		with self.assertRaises(frappe.ValidationError):
			access_api.set_app_access(self.plain, NOT_INSTALLED.key, 1)

	def test_revocation_is_effective_without_a_new_login(self):
		self.assertIn(KEY, self.keys(self.revocable))
		doc = frappe.get_doc("User", self.revocable)
		doc.remove_roles(ACCESS_ROLE)
		self.assertNotIn(KEY, self.keys(self.revocable))

	def test_only_a_platform_administrator_may_change_the_grant(self):
		frappe.set_user(self.plain)
		with self.assertRaises(frappe.PermissionError):
			access_api.set_app_access(self.plain, KEY, 1)

	# --- the gate: path prefixes and `owns` -----------------------------------------------------

	def decide(self, user, path, form=None):
		return enforcement.evaluate_request(user, path, "GET", form or {})

	def test_the_gate_lets_holders_into_the_pages_and_turns_others_away(self):
		self.assertTrue(self.decide(self.holder, "/dummy-checklist").allow)
		self.assertTrue(self.decide(self.holder, "/dummy-checklist/deep/page").allow)
		for user in (self.plain, self.website_holder, self.portal):
			refused = self.decide(user, "/dummy-checklist/staff-page")
			self.assertFalse(refused.allow, user)
			self.assertEqual(refused.redirect, f"/nxerp/no-access?app={KEY}", user)
		guest = self.decide("Guest", "/dummy-checklist")
		self.assertFalse(guest.allow)
		self.assertTrue(guest.redirect.startswith("/login?redirect-to="))

	def test_the_portal_prefix_is_open_to_portal_roles_only(self):
		self.assertTrue(self.decide(self.portal, "/dummy-checklist/portal/orders").allow)
		self.assertFalse(self.decide(self.portal, "/dummy-checklist/admin").allow)
		self.assertFalse(self.decide(self.plain, "/dummy-checklist/portal/orders").allow)

	def test_the_gate_covers_whitelisted_methods_of_the_owned_package(self):
		path = "/api/method/dummy_checklist_pkg.api.do_something"
		self.assertTrue(self.decide(self.holder, path).allow)
		self.assertTrue(
			self.decide(self.portal, path).allow
		)  # a portal user reaches the app's API; DocPerms still apply
		refused = self.decide(self.plain, path)
		self.assertFalse(refused.allow)
		self.assertEqual((refused.surface, refused.app, refused.reason), ("api_method", KEY, "no_access"))
		self.assertIsNone(refused.redirect, "an API call gets JSON, not a redirect")

	def test_methods_outside_owns_stay_shared(self):
		self.assertTrue(
			self.decide(self.plain, "/api/method/frappe.client.get_count", {"doctype": "ToDo"}).allow
		)
		self.assertTrue(self.decide(self.plain, "/api/method/other_pkg.api.x").allow)

	# --- the launcher ---------------------------------------------------------------------------

	def test_get_apps_lists_the_app_only_for_holders(self):
		def names(user):
			frappe.set_user(user)
			return [row["name"] for row in launcher.get_apps()]

		self.assertIn(KEY, names(self.holder))
		self.assertIn(KEY, names(self.implied))
		self.assertIn(KEY, names("Administrator"))
		for user in (self.plain, self.portal, self.website_holder):
			self.assertNotIn(KEY, names(user), user)

	def test_an_uninstalled_app_is_never_listed_not_even_for_administrator(self):
		frappe.set_user("Administrator")
		self.assertNotIn(NOT_INSTALLED.key, [row["name"] for row in launcher.get_apps()])

	def test_the_tile_carries_the_registry_identity(self):
		frappe.set_user(self.holder)
		(tile,) = [row for row in launcher.get_apps() if row["name"] == KEY]
		self.assertEqual((tile["title"], tile["route"]), (DUMMY.title, DUMMY.route))

	def test_the_boot_info_names_the_app_only_for_holders(self):
		def boot(user):
			frappe.set_user(user)
			info = frappe._dict(app_data=[{"app_name": "frappe", "on_apps_screen": True}])
			launcher.extend_bootinfo(info)
			return info.nxerp

		self.assertIn(KEY, [a["key"] for a in boot(self.holder)["apps"]])
		self.assertNotIn(KEY, [a["key"] for a in boot(self.plain)["apps"]])
		self.assertIsNone(boot(self.holder)["launcher"], "one app: no launcher")

	# --- landing rules --------------------------------------------------------------------------

	def test_a_user_with_only_the_new_app_lands_straight_in_it(self):
		landing = access.resolve_landing(self.holder)
		self.assertEqual((landing["mode"], landing["destination"]), ("direct", "/dummy-checklist"))
		self.assertEqual(self.route(self.holder), "/dummy-checklist")

	def test_a_user_with_two_apps_gets_the_launcher_listing_both_in_order(self):
		if not registry.get_entry("helpdesk"):
			self.skipTest("Helpdesk is not installed on this site")
		landing = access.resolve_landing(self.both)
		self.assertEqual((landing["mode"], landing["destination"]), ("launcher", "/nxerp/apps"))
		self.assertEqual([a["key"] for a in landing["apps"]], ["helpdesk", KEY])
		self.assertEqual(self.route(self.both), "/nxerp/apps")

	def test_a_user_with_no_app_lands_on_the_no_access_page(self):
		self.assertEqual(self.route(self.plain), "/nxerp/no-access")

	def test_a_portal_user_lands_on_the_portal_route(self):
		landing = access.resolve_landing(self.portal)
		self.assertEqual((landing["mode"], landing["destination"]), ("direct", "/dummy-checklist/portal"))
		self.assertEqual(landing["apps"], [], "portal use never appears in a launcher")

	def test_the_router_honours_a_redirect_into_the_app_only_for_those_who_may_use_it(self):
		self.assertEqual(self.route(self.holder, "/dummy-checklist/page?x=1"), "/dummy-checklist/page?x=1")
		self.assertEqual(self.route(self.plain, "/dummy-checklist/page"), "/nxerp/no-access")
		self.assertEqual(self.route(self.portal, "/dummy-checklist/portal/x"), "/dummy-checklist/portal/x")
		self.assertEqual(self.route(self.portal, "/dummy-checklist/admin"), "/dummy-checklist/portal")
		self.assertEqual(self.route("Guest", "/dummy-checklist"), "/login")

	def test_a_real_app_user_is_unaffected_by_the_new_entry(self):
		# adding an app changes nothing for people who do not hold it
		agent = make_user(unique_email("c-agent"), ["Agent"]).name
		self.created.append(agent)
		self.assertNotIn(KEY, self.keys(agent))
		if registry.get_entry("helpdesk"):
			self.assertEqual(self.route(agent), "/helpdesk/home")

	# --- the entry disappears with the patch ----------------------------------------------------

	def test_the_dummy_is_only_registered_while_this_class_runs(self):
		self.assertIn(KEY, [e.key for e in registry.get_registry()])
		self.patcher.stop()
		try:
			self.assertNotIn(KEY, [e.key for e in registry.get_registry()])
			self.assertNotIn(KEY, [e.key for e in registry.APPS])
		finally:
			self.patcher.start()
