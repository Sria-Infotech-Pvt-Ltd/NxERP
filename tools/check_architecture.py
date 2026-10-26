"""Enforce ADR-005: the platform app imports no other app and requires none. Stdlib only.

Run with `python3 -I tools/check_architecture.py`.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORM = ROOT / "nxerp"
# Other apps the platform must never import. Frappe itself is allowed.
FORBIDDEN = {"erpnext", "helpdesk", "hrms", "telephony", "payments", "lending", "crm"}

errors = []

for path in sorted(PLATFORM.rglob("*.py")):
	tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			modules = [alias.name for alias in node.names]
		elif isinstance(node, ast.ImportFrom) and node.level == 0:
			modules = [node.module or ""]
		else:
			continue
		for module in modules:
			if module.split(".")[0] in FORBIDDEN:
				errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: imports {module}")

hooks = ast.parse((PLATFORM / "hooks.py").read_text(encoding="utf-8"))
for node in hooks.body:
	if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "required_apps" for t in node.targets):
		try:
			value = ast.literal_eval(node.value)
		except ValueError:
			value = None
		if value != []:
			errors.append("nxerp/hooks.py: required_apps must be an empty list (ADR-005)")

if errors:
	print("\n".join(f"ERROR: {e}" for e in errors))
	sys.exit(1)
print("OK: nxerp imports no other app and declares no required_apps")
