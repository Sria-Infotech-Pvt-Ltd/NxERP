"""The switch for the new path: Helpdesk reads shared data through the Read API and changes NXERP through its command API.

Site config key `nxerp_shared_read`. Unset (or 0) means today's behaviour, exactly: nothing in `integrations/shared` runs and the
old ERPNext integration is untouched. Set it with `bench --site <site> set-config nxerp_shared_read 1`.
"""

import frappe


def is_on() -> bool:
    return bool(frappe.utils.cint(frappe.conf.get("nxerp_shared_read")))


def refuse_customer_write() -> None:
    """Helpdesk never creates, renames or deletes a customer: NXERP owns them. Raised if any path tries while the setting is on."""
    frappe.throw(
        frappe._(
            "Customers are managed in NXERP. Ask NXERP to create, rename or remove this customer."
        ),
        frappe.ValidationError,
    )
