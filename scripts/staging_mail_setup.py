"""Give a local test site a real Gmail outgoing account, turn mail on and send what is waiting. Test sites only.

Copied into a site's container as nxerp/staging_mail.py and run with
  bench --site <site> execute nxerp.staging_mail.run
The address and the App password come from the environment (SMTP_EMAIL, SMTP_APP_PASSWORD), never from the command line or the output.
"""

import os

import frappe

ACCOUNT = "Gmail test"


def run():
	frappe.set_user("Administrator")
	email, password = os.environ["SMTP_EMAIL"].strip(), os.environ["SMTP_APP_PASSWORD"].replace(" ", "").strip()
	if not email or not password:
		raise SystemExit("SMTP_EMAIL and SMTP_APP_PASSWORD must both be filled in deploy/env/isolated/smtp.env")
	frappe.db.sql("UPDATE `tabEmail Account` SET default_outgoing = 0, enable_outgoing = 0, enable_incoming = 0")
	values = {
		"email_id": email,
		"email_account_name": ACCOUNT,
		"password": password,
		"smtp_server": "smtp.gmail.com",
		"smtp_port": 587,
		"use_tls": 1,
		"use_ssl": 0,
		"enable_outgoing": 1,
		"default_outgoing": 1,
		"enable_incoming": 0,
		"always_use_account_email_id_as_sender": 1,
		"awaiting_password": 0,
	}
	if frappe.db.exists("Email Account", ACCOUNT):
		doc = frappe.get_doc("Email Account", ACCOUNT)
		doc.update(values)
	else:
		doc = frappe.get_doc({"doctype": "Email Account", **values})
	doc.save(ignore_permissions=True)  # Frappe tests the SMTP login here: a wrong App password fails now
	frappe.db.commit()
	frappe.conf.mute_emails = 0
	from frappe.email.queue import flush

	flush()
	frappe.db.commit()
	waiting = frappe.db.count("Email Queue", {"status": ["in", ["Not Sent", "Sending"]]})
	sent = frappe.db.count("Email Queue", {"status": "Sent"})
	print(f"MAIL READY account saved and login tested; queue: sent {sent}, still waiting {waiting}")
