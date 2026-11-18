"""Decide an access request. Platform administrators only.

Approval uses the platform's one grant path, `nxerp.api.access.set_app_access` (the role goes through a normal
`User.save()`, so the last-administrator guard and Frappe's Version log apply), and writes one hashed audit line.
Deciding twice is harmless: a request that is no longer Pending is returned unchanged.
"""

import frappe
from frappe import _
from frappe.utils import escape_html, get_url, now_datetime, strip_html

from nxerp import access, audit, registry
from nxerp.api import access as access_api
from nxerp.nxerp_platform.doctype.nxerp_access_request.nxerp_access_request import NOTE_MAX

DECISIONS = {"Approve": "Approved", "Reject": "Rejected"}
DESK_ROLE = "Desk User"


@frappe.whitelist(methods=["POST"])
def decide(name: str, decision: str, note: str = "") -> dict:
	if not access.is_platform_admin(frappe.session.user):
		frappe.throw(_("Only a System Manager can decide access requests"), frappe.PermissionError)
	if decision not in DECISIONS:
		frappe.throw(_("Decision must be Approve or Reject"), frappe.ValidationError)
	if not isinstance(name, str) or not frappe.db.exists("NXERP Access Request", name):
		frappe.throw(_("Request not found"), frappe.DoesNotExistError)

	req = frappe.get_doc("NXERP Access Request", name)
	req.check_permission("write")
	if req.status != "Pending":
		return _summary(req)

	note = strip_html(note or "").strip()
	if len(note) > NOTE_MAX:
		frappe.throw(_("A note is at most {0} characters").format(NOTE_MAX), frappe.ValidationError)
	if decision == "Approve":
		access_api.set_app_access(req.user, req.app_key, 1)
		_ensure_desk_access(req.user)

	req.status = DECISIONS[decision]
	req.decided_by = frappe.session.user
	req.decided_on = now_datetime()
	if note:
		req.note = note
	req.save()
	audit.log_event(req.status.lower(), req.app_key, req.user)
	_email_user(req)
	return _summary(req)


def _ensure_desk_access(user: str):
	"""Staff access needs a System User (`access.get_user_apps` ignores Website Users whatever roles they hold), and a
	self-signed account is a Website User. Approving therefore also gives the one desk-access role Frappe ships
	("Desk User": Desk login, no DocType permissions), through a normal User save. What the person may then do inside
	the product is still the administrator's call (Agent, ERPNext roles, Role Profiles), exactly as for any new colleague."""
	if frappe.db.get_value("User", user, "user_type") == "System User":
		return
	doc = frappe.get_doc("User", user)
	if DESK_ROLE not in {r.role for r in doc.roles}:
		doc.append("roles", {"role": DESK_ROLE})
	doc.save(ignore_version=False)


def _summary(req) -> dict:
	return {"name": req.name, "status": req.status, "app": req.app_key}


def _email_user(req):
	entry = registry.get_entry(req.app_key)
	title = escape_html(entry.public_title if entry else req.app_key)
	if req.status == "Approved":
		subject = _("Your access to {0} was approved").format(title)
		message = _("You can now open {0}: {1}").format(title, get_url("/nxerp/go"))
	else:
		subject = _("Your access request for {0}").format(title)
		message = _("Your request for {0} was not approved.").format(title)
		if req.note:
			message += " " + escape_html(req.note)
	try:
		frappe.sendmail(
			recipients=[req.user],
			subject=subject,
			message=message,
			reference_doctype=req.doctype,
			reference_name=req.name,
		)
	except frappe.OutgoingEmailError:
		pass  # the decision stands; the user sees it on their next visit
