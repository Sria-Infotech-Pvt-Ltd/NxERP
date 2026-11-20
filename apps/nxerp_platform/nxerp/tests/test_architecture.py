"""The architecture rules (ADR-005), enforced by scripts/check_architecture.py, and a proof that the checker
really catches each violation.

Plain unittest: nothing here needs a site, so it also runs on a developer's host:

	python -m unittest nxerp.tests.test_architecture
"""

import contextlib
import importlib.util
import io
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[4]
CHECKER = REPO / "scripts" / "check_architecture.py"

CLEAN_HOOKS = "app_name = 'nxerp'\nrequired_apps = []\n"
CLEAN_PYPROJECT = """
[project]
name = "nxerp"
dependencies = []

[tool.bench.frappe-dependencies]
frappe = ">=16.50.0,<17.0.0"
"""


def load_checker():
	spec = importlib.util.spec_from_file_location("nxerp_check_architecture", CHECKER)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def write(root: Path, files: dict):
	for rel, text in files.items():
		path = root / rel
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(textwrap.dedent(text), encoding="utf-8")


def platform_tree(root: Path, extra: dict | None = None):
	"""A minimal clean platform repo; `extra` replaces or adds files (key = path relative to the repo)."""
	files = {
		"nxerp/__init__.py": "",
		"nxerp/hooks.py": CLEAN_HOOKS,
		"nxerp/access.py": "import frappe\nfrom nxerp import registry\n",
		"pyproject.toml": CLEAN_PYPROJECT,
		"deploy/apps.json": '[{"name": "budget_mgmt", "url": "x", "branch": "y", "commit": "z"}, {"name": "nxerp"}]',
	}
	files.update(extra or {})
	write(root, files)


def other_app(base: Path, name: str, **extra):
	"""A separate checkout of another app, in a fresh folder under `base` (never inside the platform repo)."""
	root = Path(tempfile.mkdtemp(dir=base))
	files = {
		f"{name}/{name}/__init__.py": "",
		f"{name}/{name}/hooks.py": f"app_name = '{name}'\n",
		f"{name}/{name}/api.py": "import frappe\n",
	}
	files.update(extra)
	write(root, files)
	return root / name


@unittest.skipUnless(CHECKER.is_file(), "scripts/check_architecture.py is not part of this deployment")
class TestArchitectureRules(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.checker = load_checker()

	def setUp(self):
		self._tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self._tmp.cleanup)
		self.root = Path(self._tmp.name)
		# other apps are separate checkouts, never inside the platform repo
		self._apps = tempfile.TemporaryDirectory()
		self.addCleanup(self._apps.cleanup)
		self.apps = Path(self._apps.name)

	def run_cli(self, *args) -> tuple:
		"""The command line entry point (`main`), in process: (exit code, what it printed). Its `python3 -I`
		invocation is exercised by hand and in CI; running it here keeps the test free of subprocesses."""
		out = io.StringIO()
		environment = {k: v for k, v in os.environ.items() if k != "NXERP_APP_PATHS"}
		with patch.dict(os.environ, environment, clear=True), contextlib.redirect_stdout(out):
			code = self.checker.main(list(args))
		return code, out.getvalue()

	def codes(self, app_paths=None) -> list:
		return [e.split()[0] for e in self.checker.check(self.root, app_paths)]

	# --- this repository, as it is now -------------------------------------------------------

	def test_the_repository_obeys_the_rules(self):
		self.assertEqual(self.checker.check(REPO), [])

	def test_the_cli_passes_on_the_repository_and_says_what_it_skipped(self):
		code, output = self.run_cli("--root", str(REPO))
		self.assertEqual(code, 0, output)
		self.assertTrue(output.strip().splitlines()[-1].startswith("OK:"))  # R5 may print WARN lines (undecidable DocType names) first
		# without --app-path the other-app rules are verified only for apps found under apps/ (none in the older layout)
		self.assertTrue("SKIPPED" in output or "checked other apps" in output)

	# --- the checker catches violations (negative tests on a synthetic tree) ------------------

	def test_a_clean_synthetic_tree_passes(self):
		platform_tree(self.root)
		self.assertEqual(self.checker.check(self.root), [])

	def test_r1_every_import_form_of_another_app_is_caught(self):
		forms = {
			"import_plain": "import erpnext.accounts\n",
			"import_from": "from helpdesk.api import x\n",
			"import_alias": "import hrms as h\n",
			"import_module": "import importlib\nimportlib.import_module('payments.a')\n",
			"dunder_import": "__import__('telephony')\n",
			"inside_function": "def f():\n\tfrom erpnext import x\n",
			"app_named_in_apps_json": "import budget_mgmt\n",  # an app added to deploy/apps.json is covered too
		}
		for label, source in forms.items():
			with self.subTest(label):
				platform_tree(self.root, {"nxerp/leak.py": source})
				self.assertEqual(self.codes(), ["R1"], label)
				(self.root / "nxerp" / "leak.py").unlink()

	def test_r1_strings_for_frappe_get_attr_are_not_imports(self):
		platform_tree(
			self.root,
			{
				"nxerp/ok.py": "import frappe\nfrappe.get_attr('erpnext.accounts.utils.x')\nX = 'helpdesk.api'\n"
			},
		)
		self.assertEqual(self.checker.check(self.root), [])

	def test_r1_frappe_and_relative_imports_are_allowed(self):
		platform_tree(
			self.root,
			{"nxerp/ok.py": "import frappe\nfrom frappe.utils import cint\nfrom . import registry\n"},
		)
		self.assertEqual(self.checker.check(self.root), [])

	def test_r2_required_apps_in_any_form_is_caught(self):
		for label, source in {
			"list": "required_apps = ['erpnext']\n",
			"augmented": "required_apps = []\nrequired_apps += ['erpnext']\n",
			"annotated": "required_apps: list = ['helpdesk']\n",
			"computed": "required_apps = list(get())\n",
		}.items():
			with self.subTest(label):
				platform_tree(self.root, {"nxerp/hooks.py": source})
				self.assertEqual(self.codes(), ["R2"], label)

	def test_r2_a_missing_or_empty_required_apps_is_fine(self):
		platform_tree(
			self.root,
			{"nxerp/hooks.py": "app_name = 'nxerp'\n"},
		)
		self.assertEqual(self.checker.check(self.root), [])

	def test_r2_pyproject_may_bound_only_frappe(self):
		platform_tree(self.root, {"pyproject.toml": CLEAN_PYPROJECT + 'erpnext = ">=16"\n'})
		self.assertIn("R2", self.codes())
		dependent = CLEAN_PYPROJECT.replace("dependencies = []", 'dependencies = ["erpnext>=16"]')
		platform_tree(self.root, {"pyproject.toml": dependent})
		self.assertIn("R2", self.codes())

	def test_r4a_a_second_app_in_the_platform_repo_is_caught(self):
		platform_tree(
			self.root,
			{"stray/hooks.py": "app_name = 'stray'\n", "stray/__init__.py": ""},
		)
		self.assertEqual(self.codes(), ["R4a"])

	def test_r3_another_app_importing_nxerp_is_caught(self):
		platform_tree(self.root)
		for label, source in {
			"import": "import nxerp\n",
			"from": "from nxerp.access import get_user_apps as g\n",
			"import_module": "import importlib\nimportlib.import_module('nxerp.routing')\n",
		}.items():
			with self.subTest(label):
				app = other_app(self.apps, "helpdesk", **{"helpdesk/helpdesk/api.py": source})
				self.assertEqual(self.codes({"helpdesk": app}), ["R3"], label)

	def test_r3_a_hook_that_points_at_nxerp_is_caught(self):
		platform_tree(self.root)
		app = other_app(
			self.apps, "helpdesk", **{"helpdesk/helpdesk/hooks.py": "on_login = ['nxerp.routing.x']\n"}
		)
		self.assertEqual(self.codes({"helpdesk": app}), ["R3"])

	def test_r3_a_clean_other_app_passes_and_its_asset_path_text_is_not_a_dependency(self):
		platform_tree(self.root)
		app = other_app(
			self.apps,
			"helpdesk",
			**{
				"helpdesk/helpdesk/hooks.py": "logo = '/assets/nxerp/x.png'\nname = 'nxerp'\n",
				"helpdesk/helpdesk/public/nxerp_login/images/mark.png": "",
			},
		)
		self.assertEqual(self.checker.check(self.root, {"helpdesk": app}), [])

	def test_r4b_platform_code_inside_another_app_is_caught(self):
		platform_tree(self.root)
		for label, extra in {
			"login_page": {"helpdesk/helpdesk/www/login.html": "<html></html>"},
			"login_controller": {"helpdesk/helpdesk/www/login.py": "x = 1\n"},
			"nxerp_www_folder": {"helpdesk/helpdesk/www/nxerp/apps.html": "<p></p>"},
			"login_stylesheet": {"helpdesk/helpdesk/public/nxerp_login/css/a.css": "a{}"},
			"copied_resolver": {"helpdesk/helpdesk/access.py": "def resolve_landing(user):\n\treturn 1\n"},
			"copied_registry": {"helpdesk/helpdesk/reg.py": "class AppEntry:\n\tpass\n"},
		}.items():
			with self.subTest(label):
				app = other_app(self.apps, "helpdesk", **extra)
				self.assertEqual(self.codes({"helpdesk": app}), ["R4b"], label)

	def test_an_app_path_that_does_not_exist_is_an_error_not_a_pass(self):
		platform_tree(self.root)
		self.assertEqual(self.codes({"helpdesk": self.apps / "nowhere"}), ["R3"])

	def test_the_cli_exits_non_zero_on_a_violation_and_names_it(self):
		platform_tree(
			self.root,
			{"nxerp/leak.py": "import erpnext\n"},
		)
		code, output = self.run_cli("--root", str(self.root))
		self.assertEqual(code, 1)
		self.assertIn("R1 nxerp/leak.py:1: imports erpnext", output)

	def test_the_cli_checks_an_app_path_given_as_an_argument(self):
		platform_tree(self.root)
		app = other_app(self.apps, "helpdesk", **{"helpdesk/helpdesk/api.py": "import nxerp\n"})
		code, output = self.run_cli("--root", str(self.root), "--app-path", f"helpdesk={app}")
		self.assertEqual(code, 1)
		self.assertIn("R3", output)
		self.assertNotIn("SKIPPED", output)


@unittest.skipUnless(CHECKER.is_file(), "scripts/check_architecture.py is not part of this deployment")
class TestForeignDoctypeRule(unittest.TestCase):
	"""R5: another app's code does not touch a DocType another app owns (ADR-009). Sample sources only; no network, no database."""

	@classmethod
	def setUpClass(cls):
		cls.checker = load_checker()

	def setUp(self):
		self._tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self._tmp.cleanup)
		self.root = Path(self._tmp.name)
		platform_tree(
			self.root,
			extra={
				"nxerp/shared/contracts/org_unit.json": '{"source_doctype": "Company", "owner_app": "erpnext"}'
			},
		)

	def scan(self, source: str, rel="helpdesk/helpdesk/api.py", allow=frozenset()) -> tuple:
		write(self.root / "apps" / "helpdesk", {rel: source})
		foreign = self.checker.foreign_doctypes(self.root, "helpdesk")
		return self.checker.check_foreign_doctypes(
			"helpdesk", self.root / "apps" / "helpdesk", self.root, foreign, set(allow)
		)

	def test_a_literal_foreign_doctype_in_each_call_form_fails_with_file_and_line(self):
		cases = {
			'frappe.get_all("Customer", fields=["name"])': "get_all() on Customer",
			'frappe.get_list("Sales Invoice")': "get_list() on Sales Invoice",
			'frappe.get_doc("GL Entry", name)': "get_doc() on GL Entry",
			'frappe.get_doc({"doctype": "Customer", "customer_name": "x"})': "get_doc() on Customer",
			'frappe.db.get_value("Employee", name, "email")': "get_value() on Employee",
			'frappe.db.exists("Company", name)': "exists() on Company",
			'frappe.db.set_value("Customer", name, "territory", "x")': "set_value() on Customer",
			'frappe.new_doc("Customer")': "new_doc() on Customer",
			'frappe.delete_doc("Customer", name)': "delete_doc() on Customer",
			'frappe.qb.DocType("Sales Invoice")': "DocType() on Sales Invoice",
			'frappe.qb.from_("Customer")': "from_() on Customer",
			'frappe.get_all(doctype="Customer")': "get_all() on Customer",
		}
		for source, expected in cases.items():
			errors, _ = self.scan(f"import frappe\nx = {source}\n")
			self.assertEqual(len(errors), 1, source)
			self.assertIn(
				"R5 apps/helpdesk/helpdesk/helpdesk/api.py:2:", errors[0].replace("\\", "/"), source
			)
			self.assertIn(expected, errors[0], source)

	def test_raw_sql_on_a_foreign_table_fails(self):
		errors, _ = self.scan(
			'import frappe\nrows = frappe.db.sql("SELECT name FROM `tabCustomer` WHERE 1")\n'
		)
		self.assertEqual(len(errors), 1)
		self.assertIn("raw SQL on the tables of Customer", errors[0])
		self.assertEqual(
			self.scan('import frappe\nframe = frappe.db.sql("SELECT name FROM `tabHD Ticket`")\n')[0], []
		)

	def test_the_contract_owners_add_to_the_fixed_list(self):
		# org_unit's source DocType is Company in this sample: owned by erpnext, so foreign for helpdesk; not foreign for erpnext
		self.assertIn("Company", self.checker.foreign_doctypes(self.root, "helpdesk"))
		write(
			self.root / "nxerp/shared/contracts",
			{"x.json": '{"source_doctype": "Widget", "owner_app": "erpnext"}'},
		)
		self.assertIn("Widget", self.checker.foreign_doctypes(self.root, "helpdesk"))
		self.assertNotIn("Widget", self.checker.foreign_doctypes(self.root, "erpnext"))
		self.assertIn(
			"Customer", self.checker.foreign_doctypes(self.root, "helpdesk"), "the fixed list always applies"
		)

	def test_an_apps_own_doctypes_and_frappe_core_doctypes_are_fine(self):
		source = (
			"import frappe\n"
			'a = frappe.get_all("HD Ticket")\n'
			'b = frappe.get_doc("HD Customer", name)\n'
			'c = frappe.get_all("Contact")\n'
			'd = frappe.get_doc("User", user)\n'
			'e = frappe.db.get_value("Dynamic Link", name, "link_name")\n'
		)
		self.assertEqual(self.scan(source), ([], []))

	def test_a_doctype_name_that_is_not_a_literal_warns_and_does_not_fail(self):
		source = "import frappe\nrows = frappe.get_all(doctype_name)\nother = frappe.get_doc(frappe.form_dict.doctype, name)\nok = frappe.db.get_value(var, 'a', 'b')\n"
		errors, warnings = self.scan(source)
		self.assertEqual(errors, [])
		self.assertEqual(len(warnings), 2)
		self.assertIn("R5 apps/helpdesk/helpdesk/helpdesk/api.py:2:", warnings[0].replace("\\", "/"))
		self.assertIn("cannot be decided", warnings[0])

	def test_the_legacy_allow_list_exempts_only_the_exact_path(self):
		source = 'import frappe\nx = frappe.get_all("Customer")\n'
		path = "apps/helpdesk/helpdesk/helpdesk/api.py"
		self.assertEqual(self.scan(source, allow={path})[0], [], "the listed file is exempt")
		other = "helpdesk/helpdesk/api_copy.py"
		errors, _ = self.scan(source, rel=other, allow={path})
		self.assertEqual(len(errors), 1, "any other file with the same content is not")
		self.assertTrue(
			all(isinstance(p, str) and p.startswith("apps/helpdesk/") for p in self.checker.LEGACY_ALLOW)
		)
		self.assertNotIn("apps/helpdesk/helpdesk/integrations/shared", " ".join(self.checker.LEGACY_ALLOW))

	def test_the_check_fails_the_run_through_the_cli_and_names_the_line(self):
		write(
			self.root / "apps" / "helpdesk",
			{
				"helpdesk/hooks.py": "app_name = 'helpdesk'\n",
				"helpdesk/__init__.py": "",
				"helpdesk/bad.py": 'import frappe\nx = frappe.get_all("Customer")\n',
			},
		)
		out = io.StringIO()
		with (
			patch.dict(
				os.environ, {k: v for k, v in os.environ.items() if k != "NXERP_APP_PATHS"}, clear=True
			),
			contextlib.redirect_stdout(out),
		):
			code = self.checker.main(["--root", str(self.root)])
		text = out.getvalue()
		self.assertEqual(code, 1, text)
		self.assertIn("ERROR: R5", text)
		self.assertIn("bad.py:2", text)

	def test_the_repository_has_no_new_reach_and_prints_its_undecided_cases(self):
		errors, warnings = self.checker.run_checks(REPO, self.checker.discover_apps(REPO))
		self.assertEqual([e for e in errors if e.startswith("R5")], [])
		self.assertTrue(all(w.startswith("R5 ") and ":" in w for w in warnings))


if __name__ == "__main__":
	unittest.main()
