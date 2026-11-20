"""Phase 7 staging fixtures: FAKE data on the staging stacks only (never production).

Run inside a stack's backend container, one function per site (the file is copied next to the platform app):

    bench --site erp.example.test execute nxerp.phase7_fixtures.run_erp
    bench --site hd.example.test  execute nxerp.phase7_fixtures.run_hd --kwargs "{'customer_ref_id': '<customer name>'}"

`run_erp` creates (idempotently) the customer masters, two fake customers with a primary contact, a fake NXERP agent who may edit customers, and two
service users: the Helpdesk command caller (role NXERP Command Caller) and the feed reader (role NXERP Shared Feed Reader). Their API keys are written
to /tmp/phase7_keys.json INSIDE the container (key names `command` and `feed`, each `api_key:api_secret`); the caller moves them into mode-600 files and
removes that file. Nothing here prints a secret.
"""

import json

import frappe

COMMAND_USER = "helpdesk-commands@example.test"
FEED_USER = "feed-reader@example.test"
AGENT = "agent-nxerp@example.test"
CUSTOMERS = ("NXT Fixture Customer A", "NXT Fixture Customer B")


def _ensure(doctype: str, name: str, values: dict):
	if frappe.db.exists(doctype, name):
		return frappe.get_doc(doctype, name)
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert(ignore_permissions=True)
	return doc


def _user(email: str, first: str, roles: list, user_type: str = "System User"):
	if frappe.db.exists("User", email):
		doc = frappe.get_doc("User", email)
		held = {r.role for r in doc.roles}
		for role in roles:
			if role not in held:
				doc.append("roles", {"role": role})
		doc.save(ignore_permissions=True)
		return doc
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first,
			"send_welcome_email": 0,
			"user_type": user_type,
			"roles": [{"role": r} for r in roles],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _keys(email: str) -> str:
	from frappe.core.doctype.user.user import generate_keys

	secret = generate_keys(email)["api_secret"]
	return f"{frappe.db.get_value('User', email, 'api_key')}:{secret}"


def run_erp():
	frappe.set_user("Administrator")
	_ensure(
		"Customer Group", "All Customer Groups", {"customer_group_name": "All Customer Groups", "is_group": 1}
	)
	_ensure("Territory", "All Territories", {"territory_name": "All Territories", "is_group": 1})
	for name in ("NXT Commercial", "NXT Individual"):
		_ensure(
			"Customer Group",
			name,
			{"customer_group_name": name, "is_group": 0, "parent_customer_group": "All Customer Groups"},
		)
	for name in ("NXT North", "NXT South"):
		_ensure(
			"Territory", name, {"territory_name": name, "is_group": 0, "parent_territory": "All Territories"}
		)
	made = []
	for index, name in enumerate(CUSTOMERS):
		customer = _ensure(
			"Customer",
			name,
			{
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": "NXT Commercial",
				"territory": "NXT North",
			},
		)
		contact_name = f"Ada{index} Fixture{index}"
		contact = frappe.db.exists("Contact", {"first_name": f"Ada{index}", "last_name": f"Fixture{index}"})
		if not contact:
			doc = frappe.get_doc(
				{
					"doctype": "Contact",
					"first_name": f"Ada{index}",
					"last_name": f"Fixture{index}",
					"email_ids": [{"email_id": f"ada{index}@example.test", "is_primary": 1}],
					"phone_nos": [{"phone": f"+1000000000{index}", "is_primary_phone": 1}],
					"links": [{"link_doctype": "Customer", "link_name": customer.name}],
				}
			).insert(ignore_permissions=True)
			contact = doc.name
		frappe.db.set_value(
			"Customer", customer.name, "customer_primary_contact", contact, update_modified=False
		)
		made.append({"customer": customer.name, "contact": contact, "label": contact_name})
	_user(AGENT, "NXERP Agent", ["Desk User", "Sales User", "Sales Manager", "NXERP Access: ERPNext"])
	_user(COMMAND_USER, "Helpdesk Commands", ["NXERP Command Caller"])
	_user(FEED_USER, "Feed Reader", ["NXERP Shared Feed Reader"])
	keys = {"command": _keys(COMMAND_USER), "feed": _keys(FEED_USER)}
	with open("/tmp/phase7_keys.json", "w", encoding="ascii") as handle:
		json.dump(keys, handle)
	frappe.db.commit()
	print(json.dumps({"fixtures": made, "agent": AGENT, "keys_written": sorted(keys)}))


def run_hd(customer_ref_id: str, contact_id: str = ""):
	"""A fake HD Customer linked to the NXERP customer, a fake agent with the Agent role, and a fake ticket."""
	frappe.set_user("Administrator")
	name = "NXT Support Customer"
	if not frappe.db.exists("HD Customer", name):
		doc = frappe.get_doc(
			{"doctype": "HD Customer", "customer_name": name, "customer_ref_id": customer_ref_id}
		)
		doc.flags.ignore_erpnext_sync = True
		doc.insert(ignore_permissions=True)
	frappe.db.set_value("HD Customer", name, "customer_ref_id", customer_ref_id, update_modified=False)
	agent = "agent-helpdesk@example.test"
	if not frappe.db.exists("User", agent):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": agent,
				"first_name": "Support Agent",
				"send_welcome_email": 0,
				"user_type": "System User",
				"roles": [{"role": "Agent"}, {"role": "Desk User"}, {"role": "NXERP Access: Helpdesk"}],
			}
		).insert(ignore_permissions=True)
	# the Agent role creates the HD Agent record itself (a hook on User); only make one if that did not happen
	if not frappe.db.exists("HD Agent", {"user": agent}) and not frappe.db.exists("HD Agent", agent):
		frappe.get_doc({"doctype": "HD Agent", "user": agent, "agent_name": "Support Agent"}).insert(
			ignore_permissions=True, ignore_if_duplicate=True
		)
	ticket = frappe.db.exists("HD Ticket", {"subject": "NXT fixture ticket"})
	if not ticket:
		ticket = (
			frappe.get_doc(
				{
					"doctype": "HD Ticket",
					"subject": "NXT fixture ticket",
					"raised_by": "customer@example.test",
					"customer": name,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	frappe.db.commit()
	print(json.dumps({"hd_customer": name, "agent": agent, "ticket": ticket}))
