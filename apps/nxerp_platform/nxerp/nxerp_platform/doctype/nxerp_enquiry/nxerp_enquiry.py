"""A message sent from the public contact or partners page. Stored only: it grants nothing and creates no account.
Created through `nxerp.api.enquiry.submit`; an administrator reads it in Desk and marks it Handled."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import strip_html, validate_email_address

MESSAGE_MAX = 2000


class NXERPEnquiry(Document):
	def validate(self):
		self.full_name = " ".join(strip_html(self.full_name or "").split())
		self.company = " ".join(strip_html(self.company or "").split())
		self.phone = " ".join(strip_html(self.phone or "").split())
		self.message = strip_html(self.message or "").strip()
		self.email = (self.email or "").strip().lower()
		if not self.full_name:
			frappe.throw(_("Enter your name"))
		if not validate_email_address(self.email):
			frappe.throw(_("Enter a valid email address"))
		if not self.message:
			frappe.throw(_("Write a message"))
		if len(self.message) > MESSAGE_MAX:
			frappe.throw(_("A message is at most {0} characters").format(MESSAGE_MAX))
