"""Persona x surface matrix over real HTTP: every journey in the brief, on every enforcement surface.

A = the request reaches the app (the gate lets it through; Frappe's own permissions still decide the
data). D = refused: by NXERP's gate where the gate owns the surface (desk, SPA, API method, resource,
DocType argument, metadata, report), and by the document-level hook for files and realtime.

Set NXERP_MATRIX_OUT=/path/to/file.md to also write the table as Markdown.
"""

import os

from frappe.tests import IntegrationTestCase

from nxerp.tests.utils import blocked, denied_by_gate, redirected_to_login
from nxerp.tests.world import PERSONAS, World

A, D = "A", "D"

#           admin sysmgr hd_agent erp_user both customer noapps revoked disabled guest
# (surface name, kind, how to call, expectations in PERSONAS order)
#   kind "gate": a denial must come from NXERP's gate for logged-in users
#   kind "doc":  a denial may come from the document-level hook or Frappe (generic refusal)
SURFACES = [
	("desk URL /desk", "gate", ("GET", "/desk"), [A, A, D, A, A, D, D, D, D, D]),
	("SPA URL /helpdesk/home", "gate", ("GET", "/helpdesk/home"), [A, D, A, D, A, A, D, D, D, D]),
	(
		"API method (ERPNext)",
		"gate",
		("GET", "/api/method/erpnext.accounts.utils.get_fiscal_year?date=2026-10-27"),
		[A, D, D, A, A, D, D, D, D, D],
	),
	(
		"API method (Helpdesk)",
		"gate",
		("GET", "/api/method/helpdesk.api.auth.get_user"),
		[A, D, A, D, A, A, D, D, D, D],
	),
	(
		"API resource ERPNext /api/resource/Customer",
		"gate",
		("GET", "/api/resource/Customer?limit_page_length=1"),
		[A, D, D, A, A, D, D, D, D, D],
	),
	(
		"API resource Helpdesk /api/resource/HD Ticket",
		"gate",
		("GET", "/api/resource/HD%20Ticket?limit_page_length=1"),
		[A, D, A, D, A, A, D, D, D, D],
	),
	(
		"DocType argument (get_count Sales Invoice)",
		"gate",
		("GET", "/api/method/frappe.client.get_count?doctype=Sales%20Invoice"),
		[A, D, D, A, A, D, D, D, D, D],
	),
	(
		"metadata (getdoctype Customer)",
		"gate",
		("GET", "/api/method/frappe.desk.form.load.getdoctype?doctype=Customer"),
		[A, D, D, A, A, D, D, D, D, D],
	),
	(
		"report (ERPNext Accounts Receivable)",
		"gate",
		("GET", "/api/method/frappe.desk.query_report.get_script?report_name=Accounts%20Receivable"),
		[A, D, D, A, A, D, D, D, D, D],
	),
	(
		"shared DocType (get_count ToDo)",
		"gate",
		("GET", "/api/method/frappe.client.get_count?doctype=ToDo"),
		[A, A, A, A, A, A, A, A, D, D],
	),
	(
		"private file attached to an ERPNext record",
		"doc",
		("GET", "{file_url}"),
		[A, D, D, A, A, D, D, D, D, D],
	),
	(
		"realtime room join (ERPNext doc)",
		"doc",
		("GET", "/api/method/frappe.realtime.has_permission?doctype=Customer&name={customer}"),
		[A, D, D, A, A, D, D, D, D, D],
	),
]


def _reached(resp) -> bool:
	"""The request got past the gate and was handled by the app. Redirects, 401 and 403 are refusals
	(NXERP's gate, or Frappe's own 403 for a guest); other statuses mean the app ran, even if it then
	reported its own business error."""
	return resp.status_code not in (302, 401, 403)


class TestAccessMatrix(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.world = World().build()
		cls.rows = {}

	@classmethod
	def tearDownClass(cls):
		cls.world.teardown()
		cls._print_matrix()
		super().tearDownClass()

	@classmethod
	def _print_matrix(cls):
		personas = [p for p in PERSONAS if p in cls.world.clients]
		header = "| surface | " + " | ".join(personas) + " |"
		lines = [header, "|" + "---|" * (len(personas) + 1)]
		for name, *_ in SURFACES:
			cells = cls.rows.get(name, {})
			lines.append("| " + name + " | " + " | ".join(cells.get(p, "-") for p in personas) + " |")
		print(
			"\nPERSONA x SURFACE MATRIX (A = reaches the app, D = refused; as observed)\n" + "\n".join(lines)
		)
		out = os.environ.get("NXERP_MATRIX_OUT")
		if out:
			with open(out, "w", encoding="utf-8") as f:
				f.write("\n".join(lines) + "\n")

	def call(self, persona, spec):
		method, path = spec
		path = path.format(file_url=self.world.data["file_url"], customer=self.world.data["customer"])
		client = self.world.clients[persona]
		return client.get(path) if method == "GET" else client.post(path)

	def test_matrix(self):
		for name, kind, spec, expected in SURFACES:
			for persona, want in zip(PERSONAS, expected, strict=True):
				if persona not in self.world.clients:
					continue  # admin needs NXERP_ADMIN_PASSWORD
				with self.subTest(surface=name, persona=persona):
					resp = self.call(persona, spec)
					got = A if _reached(resp) and not (kind == "doc" and blocked(resp)) else D
					self.rows.setdefault(name, {})[persona] = got
					self.assertEqual(
						got,
						want,
						f"{persona} on '{name}': expected {want}, got {got} (HTTP {resp.status_code})",
					)
					if want == D and kind == "gate" and persona not in ("guest", "disabled"):
						# a logged-in user refused on a gate surface must be refused BY the gate, cleanly
						self.assertTrue(
							denied_by_gate(resp), f"{persona} on '{name}': not refused by the gate"
						)
						self.assertNotIn("Traceback", resp.text)

	def test_guests_are_sent_to_login_not_to_a_denial_page(self):
		guest = self.world.clients["guest"]
		for path in ("/desk", "/helpdesk", "/helpdesk/home", "/helpdesk/tickets/1"):
			resp = guest.get(path)
			self.assertTrue(redirected_to_login(resp), (path, resp.status_code, resp.headers.get("Location")))

	def test_denial_page_is_plain_and_reachable(self):
		resp = self.world.clients["noapps"].get("/nxerp/no-access")
		self.assertEqual(resp.status_code, 200)
		self.assertNotIn("ERPNext", resp.text)
		self.assertNotIn("Helpdesk", resp.text)  # names no application

	def test_direct_url_bypass_and_trailing_variants_are_still_gated(self):
		agent = self.world.clients["hd_agent"]
		for path in (
			"/desk/",
			"/desk/customer",
			"/desk/customer/x",
			"/app",
			"/app/customer",
			"/desk?x=1",
			"//desk",
		):
			resp = agent.get(path)
			self.assertFalse(resp.status_code == 200 and "frappe.boot" in resp.text, path)

	def test_website_list_and_print_pages_for_owned_doctypes(self):
		agent, erp = self.world.clients["hd_agent"], self.world.clients["erp_user"]
		for path in ("/list?doctype=Customer", "/printview?doctype=Customer&name=x"):
			self.assertTrue(denied_by_gate(agent.get(path)), path)  # redirected to the denial page
			self.assertFalse(denied_by_gate(erp.get(path)), path)  # reaches Frappe's own handling

	def test_revocation_applies_to_a_live_session_without_relogin(self):
		# the "revoked" session was created while the user still had both apps
		revoked = self.world.clients["revoked"]
		self.assertTrue(denied_by_gate(revoked.get("/desk")))
		self.assertTrue(denied_by_gate(revoked.get("/helpdesk/home")))

	def test_disabled_users_session_is_dead(self):
		resp = self.world.clients["disabled"].get("/api/method/helpdesk.api.auth.get_user")
		self.assertIn(resp.status_code, (401, 403))
