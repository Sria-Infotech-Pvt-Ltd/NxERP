"""The architecture rules (ADR-005), enforced by tools/check_architecture.py, and a proof that the checker
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
CHECKER = REPO / "tools" / "check_architecture.py"

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


@unittest.skipUnless(CHECKER.is_file(), "tools/check_architecture.py is not part of this deployment")
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
		self.assertTrue(output.startswith("OK:"))
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


if __name__ == "__main__":
	unittest.main()
