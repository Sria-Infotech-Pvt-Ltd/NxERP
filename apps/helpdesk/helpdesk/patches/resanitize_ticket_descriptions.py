import frappe


def execute():
    """Store the sanitized form of any ticket description that was saved unsanitized.

    Document._sanitize_content skips installs (frappe.flags.in_install), so the sample "Welcome to Helpdesk"
    ticket created by the install hook kept its raw HTML. Description is set-only-once and the framework
    compares the sanitized text with the stored one on every save, so every later save of that ticket, even a
    priority change, was refused with "Value cannot be changed for Description".

    Only the stored text is normalised (inline style spacing, quote entities); what the ticket shows does not
    change. It cannot go through doc.save() (that is the protection), so the value is written directly, without
    touching `modified`. Running it again changes nothing."""
    if not frappe.db.table_exists("HD Ticket"):
        return

    names = frappe.get_all(
        "HD Ticket",
        filters={"description": ["like", "%<%"]},
        pluck="name",
        limit_page_length=0,
    )
    for name in names:
        doc = frappe.get_doc("HD Ticket", name)
        stored = doc.description
        # The step save() runs before its set-only-once check, applied to the stored value.
        doc._sanitize_content()
        if doc.description == stored:
            continue
        frappe.db.set_value(
            "HD Ticket", name, "description", doc.description, update_modified=False
        )
