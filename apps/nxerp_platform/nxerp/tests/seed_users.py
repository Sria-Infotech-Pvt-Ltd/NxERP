"""Seed clearly fake users for local development and manual QA.

Run (inside the bench container):
	bench --site nxerp.localhost execute nxerp.tests.seed_users.seed

Refuses to run unless developer_mode is on, so it cannot create test accounts on a real site.
Passwords come from NXERP_SEED_PASSWORD, otherwise one is generated per run and printed once.
Nothing here is committed with a secret.
"""

import os
import secrets

import frappe

SEED_DOMAIN = "example.test"

# role names are Frappe/ERPNext/Helpdesk standard roles plus the NXERP access roles (nxerp.registry);
# app presence is checked at runtime. "Agent" and "Agent Manager" already confer Helpdesk access.
SEED_USERS = {
	"admin": {"first_name": "Seed Admin", "roles": ["System Manager"], "user_type": "System User"},
	"agent": {"first_name": "Seed Agent", "roles": ["Agent"], "user_type": "System User"},
	"manager": {"first_name": "Seed Manager", "roles": ["Agent Manager"], "user_type": "System User"},
	"erpuser": {
		"first_name": "Seed ERP User",
		"roles": ["Sales User", "Accounts User", "NXERP Access: ERPNext"],
		"user_type": "System User",
	},
	"customer": {"first_name": "Seed Customer", "roles": ["HD Customer"], "user_type": "Website User"},
}


def seed():
	if not frappe.conf.developer_mode:
		frappe.throw("Seeding test users is only allowed when developer_mode is enabled.")

	password = os.environ.get("NXERP_SEED_PASSWORD")
	generated = not password
	password = password or secrets.token_urlsafe(14)

	for key, spec in SEED_USERS.items():
		email = f"{key}@{SEED_DOMAIN}"
		roles = [role for role in spec["roles"] if frappe.db.exists("Role", role)]
		missing = sorted(set(spec["roles"]) - set(roles))

		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
		else:
			user = frappe.new_doc("User")
			user.email = email

		user.first_name = spec["first_name"]
		user.user_type = spec["user_type"]
		user.enabled = 1
		user.send_welcome_email = 0
		user.new_password = password
		user.set("roles", [])
		for role in roles:
			user.append("roles", {"role": role})
		user.flags.ignore_permissions = True
		user.save()

		print(
			f"{email}: type={user.user_type} roles={roles}"
			+ (f" (roles not on site: {missing})" if missing else "")
		)

	frappe.db.commit()
	if generated:
		print(f"Generated password for this run (shown once, not stored): {password}")
