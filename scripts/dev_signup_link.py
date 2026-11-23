"""Local test sites only: skip the verification email of the sign-up flow.

Run through scripts/dev-signup-link.sh. It makes sure the account exists (the same way the sign-up form does, falling back to a plain
customer-level account when the site has no mail account), then either prints the set-password link (the link the email would carry) or,
with DEV_PASSWORD, sets the password directly. It refuses to run unless the site has `allow_tests` or `developer_mode` on, which a
production site never has. The address comes from the environment (DEV_EMAIL, DEV_NAME, DEV_APP, optional DEV_PASSWORD).
"""

import os

import frappe
from frappe.utils.password import update_password


def run():
	if not (frappe.conf.get("allow_tests") or frappe.conf.get("developer_mode")):
		raise SystemExit("refused: this is not a local test site (neither allow_tests nor developer_mode is on)")
	frappe.set_user("Administrator")
	email = os.environ["DEV_EMAIL"].strip().lower()
	name = os.environ.get("DEV_NAME", "Test User").strip() or "Test User"
	app = os.environ.get("DEV_APP", "").strip()
	password = os.environ.get("DEV_PASSWORD", "")

	if not frappe.db.exists("User", email):
		try:
			from nxerp.api.account import create_account

			create_account(email, name, app)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": name,
					"user_type": "Website User",
					"send_welcome_email": 0,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()
	user = frappe.get_doc("User", email)
	if password:
		update_password(user.name, password)
		frappe.db.commit()
		print(f"DEV set the password of the account {email}")
	else:
		print("DEV-LINK " + str(user._reset_password(send_email=False)))
		frappe.db.commit()
