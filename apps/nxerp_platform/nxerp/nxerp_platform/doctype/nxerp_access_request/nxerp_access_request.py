"""A person's request for access to one application. Created through `nxerp.api.onboarding.submit`, decided
through `nxerp.api.access_request.decide`. It grants nothing by itself: approval runs the platform's one grant
path (`nxerp.api.access.set_app_access`)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import strip_html

from nxerp import registry

NOTE_MAX = 500
MAX_REQUESTS_PER_USER = (
	10  # all statuses together, so a person cannot fill the queue with cancelled and re-sent requests
)
OPEN_STATUS = "Pending"


class NXERPAccessRequest(Document):
	def validate(self):
		if self.user in ("Administrator", "Guest"):
			frappe.throw(_("Administrator and Guest cannot request access"))
		if not registry.get_entry(self.app_key):
			frappe.throw(_("Unknown or uninstalled application"))

		self.note = strip_html(self.note or "").strip()
		if len(self.note) > NOTE_MAX:
			frappe.throw(_("A note is at most {0} characters").format(NOTE_MAX))

		if self.is_new():
			self.status = self.status or OPEN_STATUS
			if self.status != OPEN_STATUS:
				frappe.throw(_("A new request starts as Pending"))
			total = frappe.db.count("NXERP Access Request", {"user": self.user})
			if total >= MAX_REQUESTS_PER_USER:
				frappe.throw(_("Too many requests for this account"))
		if self.status == OPEN_STATUS:
			clash = frappe.db.exists(
				"NXERP Access Request",
				{
					"user": self.user,
					"app_key": self.app_key,
					"status": OPEN_STATUS,
					"name": ["!=", self.name or ""],
				},
			)
			if clash:
				frappe.throw(_("There is already an open request for this application"))
