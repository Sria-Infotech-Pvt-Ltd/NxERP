"""One person's first-run answers for one application. Only what the questions need; never logged.
Read and written through `nxerp.api.onboarding`, never directly by the person."""

import frappe
from frappe import _
from frappe.model.document import Document

from nxerp import registry


class NXERPOnboarding(Document):
	def autoname(self):
		self.name = f"{self.user}:{self.app_key}"

	def validate(self):
		if not registry.get_entry(self.app_key):
			frappe.throw(_("Unknown or uninstalled application"))
