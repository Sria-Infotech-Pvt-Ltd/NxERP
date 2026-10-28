"""A customer (Website User with the HD Customer role) and a guest must not read internal Helpdesk
data or anyone else's data through any endpoint. Real HTTP, real sessions, fake data.

Marker strings are planted in the data (an internal note, an assignment) and the tests assert they
never appear in any response body the customer can trigger.
"""

import json
from typing import ClassVar

from frappe.tests import IntegrationTestCase

from nxerp.tests.utils import blocked, body, denied_by_gate
from nxerp.tests.world import World

INTERNAL_NOTE = "NXT-INTERNAL-NOTE-DO-NOT-LEAK"


class TestCustomerLeaks(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.world = World().build()
		cls.a = cls.world.clients["customer"]
		cls.b = cls.world.clients["customer_b"]
		cls.guest = cls.world.clients["guest"]
		cls.data = cls.world.data
		cls.agent_email = cls.world.users["hd_agent"]

	@classmethod
	def tearDownClass(cls):
		cls.world.teardown()
		super().tearDownClass()

	def assertNoKey(self, resp, key, where=""):
		"""No JSON object in the response carries `key` (a column label in a list of names is fine)."""

		def walk(node):
			if isinstance(node, dict):
				return key in node or any(walk(v) for v in node.values())
			if isinstance(node, list):
				return any(walk(v) for v in node)
			return False

		self.assertFalse(walk(resp.json()), f"{where}: response still carries a '{key}' field")

	def assertNoLeak(self, resp, *needles, where=""):
		text = body(resp)
		for needle in needles:
			self.assertNotIn(needle, text, f"{where}: leaked {needle!r}")

	def q(self, path):
		return self.a.get(path)

	# --- control: the customer's own data works ---------------------------------------------

	def test_customer_can_read_their_own_ticket(self):
		resp = self.q(f"/api/resource/HD%20Ticket/{self.data['ticket_a']}")
		self.assertEqual(resp.status_code, 200, body(resp)[:200])
		self.assertIn("NXT ticket A", body(resp))

	def test_controls_the_planted_data_exists_and_staff_can_see_it(self):
		"""Without this, the "not leaked" tests below could pass because nothing was ever planted."""
		staff = self.world.clients["admin"] if "admin" in self.world.clients else self.world.clients["both"]
		note = staff.get(f"/api/resource/HD%20Ticket%20Comment/{self.data['internal_comment']}")
		self.assertIn(INTERNAL_NOTE, body(note), "the internal note must exist and be readable by staff")
		assigned = staff.get(
			f'/api/resource/HD%20Ticket?fields=["name","_assign"]&filters={{"name":"{self.data["ticket_a"]}"}}'
		)
		self.assertIn(self.agent_email, body(assigned), "the assignment must exist and be visible to staff")
		docinfo = staff.get(
			f"/api/method/frappe.desk.form.load.getdoc?doctype=HD%20Ticket&name={self.data['ticket_a']}"
		)
		self.assertIn(self.agent_email, body(docinfo), "staff see assignments in the document info")
		todo = staff.get('/api/resource/ToDo?fields=["allocated_to","reference_name"]&limit_page_length=500')
		self.assertIn(self.data["ticket_a"], body(todo))

	# --- other customers ---------------------------------------------------------------------

	def test_customer_cannot_read_another_customers_ticket(self):
		resp = self.q(f"/api/resource/HD%20Ticket/{self.data['ticket_b']}")
		self.assertTrue(blocked(resp), resp.status_code)
		self.assertNoLeak(resp, "NXT ticket B", where="direct read")

	def test_ticket_list_contains_only_own_tickets(self):
		resp = self.q('/api/resource/HD%20Ticket?fields=["name","subject"]&limit_page_length=500')
		self.assertEqual(resp.status_code, 200)
		self.assertIn(self.data["ticket_a"], body(resp))
		self.assertNoLeak(resp, self.data["ticket_b"], "NXT ticket B", where="list")

	def test_filtering_for_someone_elses_tickets_returns_nothing(self):
		other = self.world.users["customer_b"]
		filters = json.dumps({"raised_by": other})
		resp = self.q(
			f'/api/method/frappe.client.get_list?doctype=HD%20Ticket&filters={filters}&fields=["name","subject"]'
		)
		self.assertNoLeak(resp, self.data["ticket_b"], "NXT ticket B", where="filtered get_list")

	def test_the_other_customer_cannot_read_ticket_a_either(self):
		resp = self.b.get(f"/api/resource/HD%20Ticket/{self.data['ticket_a']}")
		self.assertTrue(blocked(resp), resp.status_code)
		self.assertNoLeak(resp, "NXT ticket A", where="reverse direct read")

	# --- internal notes ---------------------------------------------------------------------

	def test_internal_comments_are_not_readable(self):
		for path in (
			'/api/resource/HD%20Ticket%20Comment?fields=["name","content"]',
			f'/api/method/frappe.client.get_list?doctype=HD%20Ticket%20Comment&fields=["content"]&filters={{"reference_ticket":"{self.data["ticket_a"]}"}}',
			f"/api/resource/HD%20Ticket%20Comment/{self.data['internal_comment']}",
		):
			resp = self.q(path)
			self.assertNoLeak(resp, INTERNAL_NOTE, where=path)

	def test_the_ticket_document_itself_does_not_carry_the_internal_note(self):
		for path in (
			f"/api/resource/HD%20Ticket/{self.data['ticket_a']}",
			f"/api/method/frappe.client.get?doctype=HD%20Ticket&name={self.data['ticket_a']}",
			f"/api/method/frappe.desk.form.load.getdoc?doctype=HD%20Ticket&name={self.data['ticket_a']}",
		):
			self.assertNoLeak(self.q(path), INTERNAL_NOTE, where=path)

	# --- assignments and agent / employee data ---------------------------------------------

	def test_assignments_are_not_readable_through_todo(self):
		resp = self.q(
			'/api/resource/ToDo?fields=["name","allocated_to","reference_name"]&limit_page_length=500'
		)
		self.assertNoLeak(resp, self.agent_email, self.data["ticket_a"], where="ToDo list")

	LIST_DATA: ClassVar[dict] = {
		"doctype": "HD Ticket",
		"filters": [],
		"order_by": "modified desc",
		"page_length": 20,
		"page_length_count": 20,
		"view": {"view_type": "list", "group_by_field": "owner"},
		"columns": [],
		"rows": [],
		"show_customer_portal_fields": True,
		"is_default": True,
	}

	def test_the_assignee_is_not_exposed_to_the_customer(self):
		ticket = self.data["ticket_a"]
		for path in (
			f"/api/resource/HD%20Ticket/{ticket}",
			f"/api/method/frappe.client.get?doctype=HD%20Ticket&name={ticket}",
			'/api/resource/HD%20Ticket?fields=["name","_assign"]',
			'/api/resource/HD%20Ticket?fields=["*"]',
			f'/api/method/frappe.client.get_list?doctype=HD%20Ticket&fields=["name","_assign"]&filters={{"name":"{ticket}"}}',
			f'/api/method/frappe.client.get_value?doctype=HD%20Ticket&fieldname=_assign&filters={{"name":"{ticket}"}}',
		):
			self.assertNoLeak(self.q(path), self.agent_email, where=path)

	def test_the_portals_own_ticket_list_does_not_carry_the_assignee(self):
		# Helpdesk's customer list endpoint returns `_assign` upstream; NXERP strips it for portal users
		resp = self.a.post("/api/method/helpdesk.api.doc.get_list_data", json_body=self.LIST_DATA)
		self.assertEqual(resp.status_code, 200, body(resp)[:200])
		self.assertIn(self.data["ticket_a"], body(resp), "the customer still sees their own ticket")
		self.assertNoLeak(resp, self.agent_email, where="get_list_data")
		self.assertNoKey(resp, "_assign", where="get_list_data")

	def test_staff_still_see_assignments_in_the_same_list(self):
		staff = self.world.clients["admin"] if "admin" in self.world.clients else self.world.clients["both"]
		resp = staff.post("/api/method/helpdesk.api.doc.get_list_data", json_body=self.LIST_DATA)
		self.assertIn(self.agent_email, body(resp), "the sanitiser must only affect portal-only users")

	def test_document_info_endpoints_are_refused_to_portal_users(self):
		ticket = self.data["ticket_a"]
		for path in (
			f"/api/method/frappe.desk.form.load.getdoc?doctype=HD%20Ticket&name={ticket}",
			f"/api/method/frappe.desk.form.load.get_docinfo?doctype=HD%20Ticket&name={ticket}",
		):
			resp = self.q(path)
			self.assertTrue(denied_by_gate(resp), (path, resp.status_code))
			self.assertNoLeak(resp, self.agent_email, where=path)

	def test_agent_records_are_not_readable(self):
		for path in (
			'/api/resource/HD%20Agent?fields=["name","user"]&limit_page_length=500',
			'/api/method/frappe.client.get_list?doctype=HD%20Agent&fields=["name"]',
		):
			self.assertNoLeak(self.q(path), self.agent_email, where=path)

	def test_other_users_are_not_listed(self):
		for path in (
			'/api/resource/User?fields=["name","email","full_name"]&limit_page_length=500',
			'/api/method/frappe.client.get_list?doctype=User&fields=["name","email"]&limit_page_length=500',
			"/api/method/frappe.desk.search.search_link?doctype=User&txt=nxt",
		):
			resp = self.q(path)
			self.assertNoLeak(
				resp,
				self.agent_email,
				self.world.users["erp_user"],
				self.world.users["customer_b"],
				where=path,
			)

	def test_employee_and_other_erp_people_data_is_refused_by_the_gate(self):
		for path in (
			"/api/resource/Employee",
			"/api/resource/Customer",
			'/api/resource/Contact?fields=["email_id"]',
		):
			resp = self.q(path)
			if "Contact" in path:
				self.assertNoLeak(resp, self.agent_email, self.world.users["erp_user"], where=path)
			else:
				self.assertTrue(denied_by_gate(resp), (path, resp.status_code))

	def test_agent_only_endpoints_refuse_customers(self):
		for path in ("/api/method/helpdesk.api.dashboard.get_dashboard_data",):
			resp = self.q(path)
			self.assertIn(resp.status_code, (401, 403), path)

	def test_no_desk_for_customers(self):
		self.assertTrue(denied_by_gate(self.q("/desk")))
		self.assertTrue(denied_by_gate(self.q("/desk/user")))

	# --- guests ------------------------------------------------------------------------------

	def test_guest_reads_no_ticket_data(self):
		for path in (
			"/api/resource/HD%20Ticket",
			f"/api/resource/HD%20Ticket/{self.data['ticket_a']}",
			"/api/resource/HD%20Ticket%20Comment",
			"/api/resource/User",
			"/api/method/helpdesk.api.dashboard.get_dashboard_data",
			f"/api/method/frappe.client.get?doctype=HD%20Ticket&name={self.data['ticket_a']}",
		):
			resp = self.guest.get(path)
			self.assertIn(resp.status_code, (401, 403), path)
			self.assertNoLeak(resp, "NXT ticket", INTERNAL_NOTE, self.agent_email, where=path)
