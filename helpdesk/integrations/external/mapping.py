import frappe


def map_emails_to_users(emails: list[str]) -> dict[str, str]:
    """{email: user name} for emails that match an existing, enabled Frappe User.

    The only link between an HRMS employee and a Frappe User is a matching email address;
    an HRMS employee id is never treated as a user id, and no user is ever created here."""
    emails = list({e.lower() for e in emails if e})
    if not emails:
        return {}
    rows = frappe.get_all(
        "User",
        filters={"email": ["in", emails], "enabled": 1},
        fields=["name", "email"],
    )
    return {row.email.lower(): row.name for row in rows}
