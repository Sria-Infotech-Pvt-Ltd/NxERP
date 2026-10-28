"""Managers are notified through the existing @mention mechanism (Frappe core owns mentions; Helpdesk only
links them to the ticket). These tests pin the behaviour the manager-notification requirement relies on,
so a change in either layer is noticed. No new notification code exists: mentions are core's."""

import frappe

from helpdesk.test_utils import make_agent_manager, make_ticket
from helpdesk.tests.test_core_comments import (
    CUSTOMER,
    AGENT_ONE,
    CoreCommentsTestCase,
    mention,
    notification_rows,
)


class TestManagerMentions(CoreCommentsTestCase):
    def test_a_mentioned_manager_gets_a_notification_pointing_at_the_ticket(self):
        manager = make_agent_manager("mentioned-manager")
        ticket = make_ticket()
        comment = self.make_comment(ticket, f"needs a decision {mention(manager)}")

        frappe.set_user(manager)
        rows = notification_rows(for_user=manager, source_name=comment.name)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].type, "Mention")
        self.assertEqual(rows[0].document_type, "HD Ticket")
        self.assertEqual(rows[0].document_name, ticket.name)

    def test_managers_are_in_the_editor_mention_list(self):
        """The editor offers active HD Agents (desk/src/stores/agent.ts); a manager invited as an agent is one."""
        manager = make_agent_manager("listed-manager")
        self.assertTrue(frappe.db.get_value("HD Agent", manager, "is_active"))

    def test_the_internal_comment_stays_hidden_from_the_customer(self):
        ticket = make_ticket(raised_by=CUSTOMER)
        comment = self.make_comment(ticket, "internal note", author=AGENT_ONE)

        frappe.set_user(CUSTOMER)
        self.assertFalse(frappe.has_permission("Comment", doc=comment.name))
