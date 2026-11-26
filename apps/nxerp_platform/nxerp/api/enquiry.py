"""The public "Get in touch" and partner forms. Open to guests, so it is rate limited, has a honeypot field and stores a
plain record (`NXERP Enquiry`) that an administrator reads in Desk. It never sends the visitor anything and never reveals
whether an email address is known. If site config `nxerp_enquiry_email` is set, a copy is emailed there; a mail problem never
fails the visitor's request."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

LIMIT_PER_HOUR = 6
KINDS = ("General", "Partnership")
THANKS = "Thanks. We have your message and will reply."


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=LIMIT_PER_HOUR, seconds=60 * 60)
def submit(
	full_name: str,
	email: str,
	message: str,
	kind: str = "General",
	phone: str = "",
	company: str = "",
	page: str = "",
	website: str = "",
) -> dict:
	if (website or "").strip():  # the honeypot: a person never sees this field, a bot fills it
		return {"message": _(THANKS)}
	doc = frappe.get_doc(
		{
			"doctype": "NXERP Enquiry",
			"kind": kind if kind in KINDS else "General",
			"full_name": full_name,
			"email": email,
			"phone": phone,
			"company": company,
			"message": message,
			"source_page": (page or "")[:60],
		}
	)
	doc.insert(ignore_permissions=True)
	_notify(doc)
	return {"message": _(THANKS)}


def _notify(doc) -> None:
	target = (frappe.conf.get("nxerp_enquiry_email") or "").strip()
	if "@" not in target:
		return
	try:
		frappe.sendmail(
			recipients=[target],
			reply_to=doc.email,
			subject=f"NXDESK enquiry {doc.name}: {doc.kind}",
			message=frappe.utils.escape_html(
				f"{doc.full_name} <{doc.email}> {doc.phone or ''} {doc.company or ''}\n\n{doc.message}"
			).replace("\n", "<br>"),
		)
	except Exception:
		frappe.log_error(title="NXERP enquiry notification failed")
