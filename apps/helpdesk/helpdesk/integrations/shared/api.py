"""What the Helpdesk screens call for shared customer data. Off unless the site config key `nxerp_shared_read` is set.

`get_customer_card` reads through the Read API (never raises: a failure is a banner flag, the ticket stays usable). `update_customer` and
`update_contact` change NXERP only through its command API, as the signed-in agent; a refusal is shown to the agent with NXERP's own
error code and nothing changes in Helpdesk. Helpdesk never reads or writes a Customer, a Contact of ERPNext or the shared database.
"""

import frappe
from frappe import _

from helpdesk.integrations.shared import command_client, read_client
from helpdesk.integrations.shared.settings import is_on
from helpdesk.utils import is_agent

CUSTOMER_FIELDS = (
    "display_name",
    "customer_type",
    "customer_group",
    "territory",
    "disabled",
    "primary_contact_id",
)
CONTACT_FIELDS = ("full_name", "email", "phone")
SYSTEM_FIELDS = ("entity_id", "tenant_id", "source_modified", "synced_at")


def _reference(hd_customer: str) -> str | None:
    return (
        frappe.db.get_value("HD Customer", hd_customer, "customer_ref_id")
        if hd_customer
        else None
    )


def _require(hd_customer: str, ptype: str) -> str:
    if not is_on():
        frappe.throw(
            _("Shared customer data is not enabled on this site"),
            frappe.ValidationError,
        )
    if not hd_customer or not frappe.db.exists("HD Customer", hd_customer):
        frappe.throw(_("No such customer"), frappe.DoesNotExistError)
    # the change goes to NXERP, not to Helpdesk's own record: the person must be a Helpdesk agent who can see this customer
    # (NXERP then applies its own permissions to the same person)
    if not is_agent():
        frappe.throw(
            _("Only Helpdesk agents can change customer details"),
            frappe.PermissionError,
        )
    frappe.has_permission("HD Customer", ptype, hd_customer, throw=True)
    reference = _reference(hd_customer)
    if not reference:
        frappe.throw(_("This customer is not linked to NXERP"), frappe.ValidationError)
    return reference


@frappe.whitelist()
def get_customer_card(hd_customer: str) -> dict:
    """The customer card of a ticket: details from the Read API plus how fresh they are. Never raises into the page."""
    if not is_on():
        return {"enabled": False}
    try:
        frappe.has_permission("HD Customer", "read", hd_customer, throw=True)
    except frappe.PermissionError:
        return {"enabled": True, "linked": False, "banner": False, "error": "forbidden"}
    reference = _reference(hd_customer)
    cached_name = (
        frappe.db.get_value("HD Customer", hd_customer, "customer_name_cache")
        if hd_customer
        else None
    )
    if not reference:
        return {"enabled": True, "linked": False, "name": cached_name, "banner": False}
    result = read_client.get_customer(reference)
    row = result["data"]
    name = (row or {}).get("display_name") or cached_name
    if (
        row
        and not result["error"]
        and not result["from_cache"]
        and row.get("display_name")
        and row["display_name"] != cached_name
    ):
        # the card refreshes the cached name each time a read succeeds (a cache, never authoritative)
        frappe.db.set_value(
            "HD Customer",
            hd_customer,
            "customer_name_cache",
            row["display_name"],
            update_modified=False,
        )
    contact = _contact_of(row, result)
    return {
        "enabled": True,
        "linked": True,
        "contact": contact,
        "name": name,
        "fields": {k: v for k, v in (row or {}).items() if k not in SYSTEM_FIELDS},
        "version": (row or {}).get("source_modified"),
        "synced_at": result["synced_at"],
        "stale": result["stale"],
        "error": result["error"],
        "banner": bool(
            result["stale"]
            or result["error"]
            or (contact or {}).get("error")
            or (contact or {}).get("stale")
        ),  # "customer details may be out of date"
    }


def _contact_of(customer_row: dict | None, customer_result: dict) -> dict | None:
    """The customer's primary contact (name, email, phone) from the Read API, with its own freshness. Never raises."""
    contact_id = (customer_row or {}).get("primary_contact_id")
    if not contact_id:
        return None
    result = read_client.get_contact(contact_id)
    row = result["data"] or {}
    return {
        "id": contact_id,
        "fields": {k: row.get(k) for k in CONTACT_FIELDS if row},
        "version": row.get("source_modified"),
        "stale": result["stale"],
        "error": result["error"],
    }


def _fail(failure: command_client.CommandFailed, key: str):
    frappe.throw(
        _("NXERP did not apply the change ({0}): {1}").format(
            failure.code, failure.message or _("no details")
        ),
        frappe.ValidationError,
        title=_("Change not applied"),
    )


def _clean(fields, allowed: tuple) -> dict:
    if isinstance(fields, str):
        try:
            fields = frappe.parse_json(fields)
        except ValueError:
            fields = None
    if not isinstance(fields, dict) or not fields or set(fields) - set(allowed):
        frappe.throw(
            _("Only these details can be changed here: {0}").format(", ".join(allowed)),
            frappe.ValidationError,
        )
    return fields


@frappe.whitelist(methods=["POST"])
def update_customer(
    hd_customer: str,
    fields,
    idempotency_key: str | None = None,
    expected_version: str | None = None,
) -> dict:
    """Ask NXERP to change the customer's group or territory. Send the SAME `idempotency_key` when you retry a request."""
    reference = _require(hd_customer, "read")
    values = _clean(fields, ("customer_group", "territory"))
    key = idempotency_key or command_client.new_key()
    try:
        result = command_client.apply(
            "customer",
            reference,
            "request_change",
            values,
            idempotency_key=key,
            acting_user=frappe.session.user,
            expected_version=expected_version,
        )
    except command_client.CommandFailed as failure:
        _fail(failure, key)
    read_client.forget("customer", reference)
    return {
        "ok": True,
        "version": result.get("source_modified"),
        "idempotency_key": key,
    }


@frappe.whitelist(methods=["POST"])
def update_contact(
    hd_customer: str,
    fields,
    idempotency_key: str | None = None,
    expected_version: str | None = None,
) -> dict:
    """Ask NXERP to change the customer's primary contact (name, email, phone)."""
    reference = _require(hd_customer, "read")
    values = _clean(fields, CONTACT_FIELDS)
    card = read_client.get_customer(reference)
    contact_id = ((card["data"] or {}).get("primary_contact_id")) or None
    if not contact_id:
        frappe.throw(
            _("NXERP has no primary contact for this customer"), frappe.ValidationError
        )
    key = idempotency_key or command_client.new_key()
    try:
        result = command_client.apply(
            "contact",
            contact_id,
            "update_contact",
            values,
            idempotency_key=key,
            acting_user=frappe.session.user,
            expected_version=expected_version,
        )
    except command_client.CommandFailed as failure:
        _fail(failure, key)
    read_client.forget("contact", contact_id)
    return {
        "ok": True,
        "version": result.get("source_modified"),
        "idempotency_key": key,
    }


@frappe.whitelist()
def get_status() -> dict:
    """For the settings screen: is the shared path on, and is it configured. Names only, never a value."""
    from helpdesk.integrations.external.client import get_setting

    return {
        "enabled": is_on(),
        "read_configured": bool(
            get_setting(read_client.URL_NAME) and get_setting(read_client.TOKEN_NAME)
        ),
        "commands_configured": bool(
            get_setting(command_client.URL_NAME)
            and get_setting(command_client.KEY_NAME)
            and get_setting(command_client.SECRET_NAME)
        ),
    }
