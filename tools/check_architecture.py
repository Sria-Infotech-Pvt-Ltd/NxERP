"""Enforce ADR-005: the platform app and the other apps stay independent. Stdlib only.

Run with `python3 -I tools/check_architecture.py` (on a Windows host without a `python3` shim: `python -I ...`).

Rules (each is a failure, exit code 1):

  R1  `nxerp` imports no other Frappe app: erpnext, helpdesk, hrms, payments, telephony (and lending, crm),
      plus every app named in deploy/apps.json. Checked in every form that names the module literally:
      `import x`, `from x import y`, `importlib.import_module("x")`, `__import__("x")`. A dotted path held in a
      string for `frappe.get_attr(...)` or a hook is NOT an import and is allowed.
  R2  `nxerp` declares no `required_apps` (hooks.py: absent or an empty list literal, however it is assigned) and
      lists no other app in pyproject.toml (`[project].dependencies`, `[tool.bench.*]`); Frappe is the only bound.
  R3  No other app imports `nxerp` (import forms as R1, plus a dotted `nxerp.` path in the app's hooks.py).
      Needs the other apps' checkouts: pass `--app-path name=path` (repeatable) or set NXERP_APP_PATHS to
      `name=path` entries separated by the OS path separator. With neither, R3 and R4b are SKIPPED and say so.
  R4  Platform code lives in `nxerp/` and nowhere else:
        R4a  this repository holds no second Frappe app (another `hooks.py` next to an `__init__.py`);
        R4b  another app's checkout holds no platform-owned artefact: the `/login` page (`www/login.*`, ADR-005),
             a `www/nxerp/` folder, the login stylesheet or fonts (`public/nxerp_login/css|fonts`), or a
             re-definition of platform API (`AppEntry`, `resolve_landing`, `get_user_apps`, `can_access_app`,
             `safe_target`, `authorised_target`). The logo images under `public/nxerp_login/images` stay in
             Helpdesk on purpose (ADR-004 amendment 1).

`--root PATH` checks another tree with the same layout (used by the negative tests, which build a synthetic one).
"""

import argparse
import ast
import json
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORM_APP = Path("apps") / "nxerp_platform"

# Other apps the platform must never import. Frappe itself is allowed. deploy/apps.json adds to this set.
FORBIDDEN = {"erpnext", "helpdesk", "hrms", "telephony", "payments", "lending", "crm"}

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".ruff_cache", ".pytest_cache", "dist"}

# platform-owned paths inside another app's package (R4b). Helpdesk keeps the NXERP logo images under
# public/nxerp_login/images for its own SPA on purpose (ADR-004 amendment 1), so only the login page and
# its stylesheet and fonts count.
LOGIN_ASSETS = (
	"www/login.html",
	"www/login.py",
	"www/nxerp",
	"public/nxerp_login/css",
	"public/nxerp_login/fonts",
)

# names the platform defines; an app that re-defines them is carrying a copy of platform code (R4b)
PLATFORM_SYMBOLS = {
	"AppEntry",
	"resolve_landing",
	"get_user_apps",
	"can_access_app",
	"safe_target",
	"authorised_target",
}


def platform_root(root: Path) -> Path:
	"""Folder holding the platform app's pyproject.toml and nxerp/ package: apps/nxerp_platform in this monorepo,
	the repository root in the older single-app layout (which the negative tests build)."""
	app = root / PLATFORM_APP
	return app if (app / "nxerp").is_dir() else root


def discover_apps(root: Path) -> dict:
	"""The other apps of a monorepo: every apps/<name> folder except the platform's."""
	apps = root / "apps"
	if not apps.is_dir():
		return {}
	skip = platform_root(root)
	return {d.name: d for d in sorted(apps.iterdir()) if d.is_dir() and d != skip}


def iter_files(root: Path, suffix: str):
	for current, dirs, files in os.walk(root):
		dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
		for name in sorted(files):
			if name.endswith(suffix):
				yield Path(current) / name


def parse(path: Path):
	return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def named_modules(tree):
	"""(line, module) for every module a file names literally in an import."""
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			for alias in node.names:
				yield node.lineno, alias.name
		elif isinstance(node, ast.ImportFrom) and node.level == 0:
			yield node.lineno, node.module or ""
		elif isinstance(node, ast.Call) and node.args:
			func = node.func
			name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
			first = node.args[0]
			if name in ("import_module", "__import__") and isinstance(first, ast.Constant):
				if isinstance(first.value, str):
					yield node.lineno, first.value


def forbidden_apps(root: Path) -> set:
	names = set(FORBIDDEN)
	apps_json = root / "deploy" / "apps.json"
	if apps_json.is_file():
		for app in json.loads(apps_json.read_text(encoding="utf-8")):
			if app.get("name") and app["name"] != "nxerp":
				names.add(app["name"])
	return names


def check_platform_imports(root: Path, forbidden: set) -> list:
	errors = []
	for path in iter_files(platform_root(root) / "nxerp", ".py"):
		for lineno, module in named_modules(parse(path)):
			if module.split(".")[0] in forbidden:
				errors.append(f"R1 {path.relative_to(root).as_posix()}:{lineno}: imports {module}")
	return errors


def check_required_apps(root: Path, forbidden: set) -> list:
	errors = []
	hooks = platform_root(root) / "nxerp" / "hooks.py"
	if not hooks.is_file():
		return ["R2 apps/nxerp_platform/nxerp/hooks.py is missing"]
	for node in ast.walk(parse(hooks)):
		if isinstance(node, ast.Assign):
			targets, value = node.targets, node.value
		elif isinstance(node, ast.AnnAssign):
			targets, value = [node.target], node.value
		elif isinstance(node, ast.AugAssign):
			targets, value = [node.target], None  # `required_apps += [...]` is never empty-by-construction
		else:
			continue
		if not any(getattr(t, "id", "") == "required_apps" for t in targets):
			continue
		try:
			literal = ast.literal_eval(value) if value is not None else None
		except ValueError:
			literal = None
		if literal not in ([], ()):
			errors.append(f"R2 apps/nxerp_platform/nxerp/hooks.py:{node.lineno}: required_apps must be an empty list (ADR-005)")

	pyproject = platform_root(root) / "pyproject.toml"
	if pyproject.is_file():
		data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
		for dep in data.get("project", {}).get("dependencies", []):
			name = dep.replace("=", " ").replace("<", " ").replace(">", " ").replace("~", " ").split()[0]
			if name.lower() in forbidden:
				errors.append(f"R2 pyproject.toml: dependency on app {name}")
		bench = data.get("tool", {}).get("bench", {})
		for section, table in bench.items():
			if section in ("frappe-dependencies", "dev-dependencies") and isinstance(table, dict):
				for name in table:
					if section == "frappe-dependencies" and name != "frappe":
						errors.append(f"R2 pyproject.toml: [tool.bench.{section}] lists {name}; only frappe")
					if name.lower() in forbidden:
						errors.append(f"R2 pyproject.toml: [tool.bench.{section}] lists app {name}")
	return errors


def check_second_app_in_repo(root: Path) -> list:
	errors = []
	for hooks in iter_files(root, "hooks.py"):
		if hooks.name != "hooks.py":
			continue
		package = hooks.parent
		if package == platform_root(root) / "nxerp" or not (package / "__init__.py").is_file():
			continue
		# a sibling app under apps/ is checked by the other-app rules (R3, R4b), not a stray second app
		if (root / "apps") in package.parents and platform_root(root) not in package.parents:
			continue
		errors.append(
			f"R4a {package.relative_to(root).as_posix()}: a second Frappe app lives in the platform repo"
		)
	return errors


def app_packages(app_root: Path):
	"""Directories of a checkout that are Frappe app packages (hooks.py beside __init__.py)."""
	for hooks in iter_files(app_root, "hooks.py"):
		if hooks.name == "hooks.py" and (hooks.parent / "__init__.py").is_file():
			yield hooks.parent


def check_other_app(name: str, app_root: Path) -> list:
	errors = []
	label = f"{name}"
	for path in iter_files(app_root, ".py"):
		rel = path.relative_to(app_root).as_posix()
		try:
			tree = parse(path)
		except SyntaxError as exc:
			errors.append(f"R3 {label}:{rel}: cannot be parsed ({exc.msg}), so it could not be checked")
			continue
		for lineno, module in named_modules(tree):
			if module.split(".")[0] == "nxerp":
				errors.append(f"R3 {label}:{rel}:{lineno}: imports {module} (apps never import the platform)")
		for node in ast.walk(tree):
			if isinstance(node, ast.FunctionDef | ast.ClassDef) and node.name in PLATFORM_SYMBOLS:
				errors.append(f"R4b {label}:{rel}:{node.lineno}: defines {node.name}, which is platform code")
		if path.name == "hooks.py":
			for node in ast.walk(tree):
				if isinstance(node, ast.Constant) and isinstance(node.value, str):
					if node.value.startswith("nxerp.") and node.value[6:7].isidentifier():
						errors.append(
							f"R3 {label}:{rel}:{node.lineno}: hook points at {node.value} (apps never depend on the platform)"
						)
	for package in app_packages(app_root):
		base = package.relative_to(app_root).as_posix()
		for owned in LOGIN_ASSETS:
			if (package / owned).exists():
				errors.append(f"R4b {label}:{base}/{owned}: platform-owned (ADR-005); it belongs in nxerp/")
	return errors


def check(root: Path = ROOT, app_paths: dict | None = None) -> list:
	"""All violations as strings; an empty list means the tree is clean."""
	forbidden = forbidden_apps(root)
	errors = []
	if not (platform_root(root) / "nxerp").is_dir():
		return [f"R1 {root}: no nxerp/ package to check"]
	errors += check_platform_imports(root, forbidden)
	errors += check_required_apps(root, forbidden)
	errors += check_second_app_in_repo(root)
	for name, path in (app_paths or {}).items():
		if not Path(path).is_dir():
			errors.append(f"R3 --app-path {name}={path}: not a directory")
		else:
			errors += check_other_app(name, Path(path))
	return errors


def parse_app_paths(values, env: str | None) -> dict:
	entries = list(values or [])
	if env:
		entries += [e for e in env.split(os.pathsep) if e.strip()]
	result = {}
	for entry in entries:
		name, sep, path = entry.partition("=")
		if not sep or not name.strip() or not path.strip():
			raise SystemExit(f"ERROR: --app-path must look like name=path, got {entry!r}")
		result[name.strip()] = path.strip()
	return result


def main(argv=None) -> int:
	parser = argparse.ArgumentParser(description="NXERP architecture rules (ADR-005)")
	parser.add_argument("--root", default=str(ROOT), help="repository to check (default: this one)")
	parser.add_argument(
		"--app-path",
		action="append",
		metavar="NAME=PATH",
		help="checkout of another app, to prove it does not import nxerp (repeatable; or NXERP_APP_PATHS)",
	)
	args = parser.parse_args(argv)
	app_paths = parse_app_paths(args.app_path, os.environ.get("NXERP_APP_PATHS"))

	app_paths = {**discover_apps(Path(args.root)), **app_paths}
	errors = check(Path(args.root), app_paths)
	if errors:
		print("\n".join(f"ERROR: {e}" for e in errors))
		return 1
	if app_paths:
		scope = f"checked other apps: {', '.join(sorted(app_paths))}"
	else:
		scope = (
			"SKIPPED the other-app checks (R3, R4b): no --app-path / NXERP_APP_PATHS given, "
			"so 'no app imports nxerp' is NOT verified by this run"
		)
	print(f"OK: nxerp imports no other app, declares no required_apps, and the repo holds one app; {scope}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
