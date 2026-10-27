"""A committed, fake-data world for the HTTP integration tests: personas, ERPNext and Helpdesk records.

Everything uses example.test addresses and random passwords generated per run; nothing is written to
the repository. `World.teardown()` removes it again. Needs the site to be running (the tests make real
HTTP requests, so the real `auth_hooks`, redirects and session handling are exercised).
"""

import json
import os
import secrets

import frappe

from nxerp.api import access as access_api
from nxerp.tests.utils import (
	ERP_ACCESS,
	PLAIN_DESK_ROLE,
	Client,
	allow_many_test_users,
	delete_users,
	make_user,
	purge_test_users,
	unique_email,
)

PERSONAS = (
	"admin",
	"sysmgr",
	"hd_agent",
	"erp_user",
	"both",
	"customer",
	"noapps",
	"revoked",
	"disabled",
	"guest",
)


def _non_group(doctype: str):
	return frappe.db.get_value(doctype, {"is_group": 0}, "name")


class World:
	def __init__(self):
		self.users = {}  # persona -> email
		self.passwords = {}
		self.clients = {}
		self.data = {}
		self.created = []

	# --- build ---------------------------------------------------------------------------

	def build(self):
		frappe.set_user("Administrator")
		allow_many_test_users()
		purge_test_users()
		self._purge_records()
		self._personas()
		self._records()
		frappe.db.commit()
		self._sessions()
		self._post_login_changes()
		return self

	@staticmethod
	def _purge_records():
		"""Remove records left by an aborted run."""
		frappe.flags.in_patch = True
		try:
			for doctype, field, pattern in (
				("HD Ticket Comment", "content", "NXT-INTERNAL-NOTE%"),
				("HD Ticket", "subject", "NXT ticket %"),
				("File", "file_name", "nxt-%.txt"),
				("Customer", "customer_name", "NXT Customer %"),
			):
				for name in frappe.get_all(doctype, filters={field: ["like", pattern]}, pluck="name"):
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		finally:
			frappe.flags.in_patch = False
		frappe.db.commit()

	def _make(self, persona, roles, **kw):
		password = secrets.token_urlsafe(16)
		doc = make_user(unique_email(persona), roles, password=password, **kw)
		self.users[persona] = doc.name
		self.passwords[persona] = password
		self.created.append(doc.name)

	def _personas(self):
		self._make("sysmgr", ["System Manager"])
		self._make("hd_agent", ["Agent"])
		self._make("erp_user", ["Sales User", "Accounts User", ERP_ACCESS])
		self._make("both", ["Agent Manager", "Sales User", "Accounts User", ERP_ACCESS])
		self._make("customer", ["HD Customer"], user_type="Website User")
		self._make("customer_b", ["HD Customer"], user_type="Website User")
		self._make("noapps", [PLAIN_DESK_ROLE])
		# starts with both apps and the ERPNext business role, then loses both grants
		self._make("revoked", ["Agent", "Sales User", "Accounts User", ERP_ACCESS, PLAIN_DESK_ROLE])
		self._make("disabled", ["Agent", "Sales User", ERP_ACCESS])

	def _records(self):
		suffix = secrets.token_hex(3)
		group = _non_group("Customer Group")
		territory = _non_group("Territory")
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"NXT Customer {suffix}",
				"customer_group": group,
				"territory": territory,
			}
		).insert()
		self.data["customer"] = customer.name

		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"nxt-{suffix}.txt",
				"content": "NXT-PRIVATE-ERP-CONTENT",
				"is_private": 1,
				"attached_to_doctype": "Customer",
				"attached_to_name": customer.name,
			}
		).insert()
		self.data["file_url"] = file.file_url
		self.data["file"] = file.name

		self.data["ticket_a"] = self._ticket(self.users["customer"], f"NXT ticket A {suffix}")
		self.data["ticket_b"] = self._ticket(self.users["customer_b"], f"NXT ticket B {suffix}")

		comment = frappe.get_doc(
			{
				"doctype": "HD Ticket Comment",
				"reference_ticket": self.data["ticket_a"],
				"commented_by": self.users["hd_agent"],
				"content": "NXT-INTERNAL-NOTE-DO-NOT-LEAK",
			}
		).insert()
		self.data["internal_comment"] = comment.name

		# an assignment of ticket A to the agent
		from frappe.desk.form import assign_to

		assign_to.add(
			{"doctype": "HD Ticket", "name": self.data["ticket_a"], "assign_to": [self.users["hd_agent"]]}
		)

	def _ticket(self, raised_by, subject):
		ticket = frappe.get_doc(
			{
				"doctype": "HD Ticket",
				"subject": subject,
				"description": "fake ticket for access tests",
				"raised_by": raised_by,
			}
		).insert()
		return ticket.name

	def _sessions(self):
		admin_password = os.environ.get("NXERP_ADMIN_PASSWORD")
		if admin_password:
			self.clients["admin"] = Client("Administrator", admin_password)
			self.users["admin"] = "Administrator"
		for persona in (
			"sysmgr",
			"hd_agent",
			"erp_user",
			"both",
			"customer",
			"customer_b",
			"noapps",
			"revoked",
			"disabled",
		):
			self.clients[persona] = Client(self.users[persona], self.passwords[persona])
		self.clients["guest"] = Client()
		self.users["guest"] = "Guest"

	def _post_login_changes(self):
		"""Revoke and disable AFTER the sessions exist: the old cookies must stop working at once."""
		frappe.set_user("Administrator")
		access_api.set_app_access(self.users["revoked"], "helpdesk", 0)
		access_api.set_app_access(self.users["revoked"], "erpnext", 0)
		disabled = frappe.get_doc("User", self.users["disabled"])
		disabled.enabled = 0
		disabled.save()
		frappe.db.commit()

	# --- teardown ------------------------------------------------------------------------

	def teardown(self):
		frappe.set_user("Administrator")
		frappe.flags.in_patch = True
		try:
			for name in ("ticket_a", "ticket_b"):
				if self.data.get(name):
					frappe.delete_doc("HD Ticket", self.data[name], force=True, ignore_permissions=True)
			if self.data.get("internal_comment"):
				frappe.delete_doc(
					"HD Ticket Comment", self.data["internal_comment"], force=True, ignore_permissions=True
				)
			if self.data.get("file"):
				frappe.delete_doc("File", self.data["file"], force=True, ignore_permissions=True)
			if self.data.get("customer"):
				frappe.delete_doc("Customer", self.data["customer"], force=True, ignore_permissions=True)
			frappe.db.delete("ToDo", {"allocated_to": ["in", self.created]})
			delete_users(self.created)
		finally:
			frappe.flags.in_patch = False
		frappe.db.commit()


def dump(table: list, path: str | None):
	"""Write the matrix as Markdown when a path is given."""
	if not path:
		return
	with open(path, "w", encoding="utf-8") as f:
		f.write(json.dumps(table) if path.endswith(".json") else "\n".join(table) + "\n")
