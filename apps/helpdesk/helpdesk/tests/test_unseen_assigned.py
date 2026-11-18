"""Per-agent badge: the count of open tickets assigned to an agent that they have not opened."""

import frappe
from frappe.desk.form.assign_to import add as assign_add
from frappe.tests import IntegrationTestCase

from helpdesk.api.unseen import get_unseen_assigned_count
from helpdesk.test_utils import create_user, make_agent, make_ticket, unique_email


class TestUnseenAssignedCount(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.agent = make_agent(unique_email("unseen-agent"))
        self.other = make_agent(unique_email("unseen-other"))
        self.customer = create_user(unique_email("unseen-customer")).name

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def assigned(self, user, **kwargs):
        ticket = make_ticket(raised_by=self.customer, **kwargs)
        assign_add({"doctype": "HD Ticket", "name": ticket.name, "assign_to": [user]})
        return ticket

    def count_for(self, user):
        frappe.set_user(user)
        try:
            return get_unseen_assigned_count()
        finally:
            frappe.set_user("Administrator")

    def test_counts_only_my_own_assigned_unseen_tickets(self):
        self.assigned(self.agent)
        self.assigned(self.agent)
        self.assigned(self.other)
        make_ticket(raised_by=self.customer)  # not assigned to anyone
        self.assertEqual(self.count_for(self.agent), 2)
        self.assertEqual(self.count_for(self.other), 1)

    def test_opening_a_ticket_removes_it_from_the_count(self):
        ticket = self.assigned(self.agent)
        self.assertEqual(self.count_for(self.agent), 1)
        frappe.set_user(self.agent)
        frappe.get_doc("HD Ticket", ticket.name).mark_seen()
        frappe.set_user("Administrator")
        self.assertEqual(self.count_for(self.agent), 0)

    def test_someone_else_opening_it_does_not_hide_it_from_me(self):
        ticket = self.assigned(self.agent)
        frappe.set_user(self.other)
        frappe.get_doc("HD Ticket", ticket.name).mark_seen()
        frappe.set_user("Administrator")
        self.assertEqual(self.count_for(self.agent), 1)

    def test_resolved_tickets_are_not_counted(self):
        ticket = self.assigned(self.agent)
        frappe.db.set_value("HD Ticket", ticket.name, "status_category", "Resolved")
        self.assertEqual(self.count_for(self.agent), 0)

    def test_customers_cannot_ask(self):
        frappe.set_user(self.customer)
        with self.assertRaises(frappe.PermissionError):
            get_unseen_assigned_count()
        frappe.set_user("Administrator")
