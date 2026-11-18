"""Grant migration: suggest the access roles users need now that access is a grant (ADR-003).

Before the access layer, any System User holding an ERPNext role could use ERPNext. Now ERPNext needs the
`NXERP Access: ERPNext` role, so on an existing site those users would be turned away until they are granted it.
This reads who holds roles that matter to an app and suggests the matching grant. It is a DRY RUN: it writes
nothing unless called with `apply=True`, and it never touches Administrator, disabled users or website users.

	bench --site SITE execute nxerp.migration.suggest_grants                              # dry run, prints a table
	bench --site SITE execute nxerp.migration.suggest_grants --kwargs '{"apply": true}'   # grants them
	bench --site SITE execute nxerp.migration.suggest_grants --kwargs '{"apply": true, "only": ["a@x.com"]}'

Review the table before applying: a role can be held for reasons that are not "uses this app".
"""

import frappe

from nxerp import access, registry

# roles every desk user holds, or that confer administration rather than use of an app
GENERIC_ROLES = frozenset({"All", "Guest", "Administrator", "Desk User", access.PLATFORM_ADMIN_ROLE})


def _app_roles(entry) -> set:
	"""Roles that carry permissions on the DocTypes the app owns, minus generic ones."""
	doctypes = []
	for package in entry.owns:
		modules = frappe.get_all("Module Def", filters={"app_name": package}, pluck="name")
		if modules:
			doctypes += frappe.get_all("DocType", filters={"module": ["in", modules]}, pluck="name")
	if not doctypes:
		return set()
	roles = set()
	for table in ("DocPerm", "Custom DocPerm"):
		roles |= set(frappe.get_all(table, filters={"parent": ["in", doctypes]}, pluck="role"))
	return roles - GENERIC_ROLES - set(entry.grant_roles)


def find_suggestions(only: list | None = None) -> list:
	"""[{user, app, role, because}], one per user and app that has no grant today. Reads only.
	`only` limits the people considered (used to scope a run and by the tests)."""
	suggestions = []
	entries = [e for e in registry.installed_entries() if not e.test_only]
	filters = {"enabled": 1, "user_type": "System User", "name": ["not in", ("Administrator", "Guest")]}
	if only is not None:
		filters["name"] = ["in", [u for u in only if u not in ("Administrator", "Guest")] or [""]]
	users = frappe.get_all("User", filters=filters, pluck="name")
	roles_by_user = {}
	for row in frappe.get_all("Has Role", filters={"parenttype": "User"}, fields=["parent", "role"]):
		roles_by_user.setdefault(row.parent, set()).add(row.role)

	for entry in entries:
		relevant = _app_roles(entry)
		for user in users:
			held = roles_by_user.get(user, set())
			if held & entry.grant_roles:
				continue  # already granted (explicitly or through an implied role)
			because = sorted(held & relevant)
			if because:
				suggestions.append(
					{"user": user, "app": entry.key, "role": entry.access_role, "because": because}
				)
	return suggestions


def suggest_grants(apply: bool = False, only: list | None = None):
	"""Print the suggestions; with `apply`, grant them. Returns the list for scripting."""
	frappe.set_user("Administrator")
	suggestions = find_suggestions(only)
	if not suggestions:
		print("No grants to suggest: every user who needs an app already holds its access role.")
		return suggestions

	print(f"{'APPLIED' if apply else 'DRY RUN'}: {len(suggestions)} suggested grant(s)")
	for s in suggestions:
		print(f"  {s['user']}  ->  {s['role']}   (holds: {', '.join(s['because'])})")

	if not apply:
		print("Nothing was changed. Re-run with --kwargs '{\"apply\": true}' after review.")
		return suggestions

	for s in suggestions:
		doc = frappe.get_doc("User", s["user"])
		doc.append("roles", {"role": s["role"]})
		doc.flags.ignore_permissions = True
		doc.save()
	frappe.db.commit()
	print("Granted. Each change is on the user's version history.")
	return suggestions
