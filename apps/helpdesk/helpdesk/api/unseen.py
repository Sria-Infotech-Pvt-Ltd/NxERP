"""Per-agent count of assigned tickets the agent has not opened yet (Tickets badge in the agent sidebar).

Reuses what Frappe already records instead of adding state: `_assign` (who a ticket is assigned to) and `_seen`
(who has opened it; HD Ticket has `track_seen`, and `HDTicket.mark_seen` writes it when an agent opens the ticket).
The query goes through `frappe.get_list`, so ticket permissions and team restrictions apply to the count too.
"""

import frappe

from helpdesk.utils import agent_only

HD_TICKET = "HD Ticket"


@frappe.whitelist()
@agent_only
def get_unseen_assigned_count() -> int:
    """Open tickets assigned to the caller that the caller has not seen. Only ever the caller's own count."""
    user = frappe.session.user
    mine = f'%"{user}"%'
    rows = frappe.get_list(
        HD_TICKET,
        filters=[["_assign", "like", mine], ["status_category", "!=", "Resolved"]],
        or_filters=[["_seen", "is", "not set"], ["_seen", "not like", mine]],
        fields=[{"COUNT": "*", "as": "unseen"}],
    )
    return int(rows[0].unseen) if rows else 0
