"""Validate deploy/apps.json and deploy/versions.env. Stdlib only; run with `python3 -I`."""

import json
import re
import sys
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent
SHA = re.compile(r"^[0-9a-f]{40}$")
errors = []

apps = json.loads((DEPLOY / "apps.json").read_text())
names = [app.get("name") for app in apps]
if len(names) != len(set(names)):
	errors.append(f"duplicate app names: {names}")
for app in apps:
	for key in ("name", "url", "branch"):
		if not app.get(key):
			errors.append(f"{app.get('name', '?')}: missing {key}")
	commit = app.get("commit")
	# every third-party app must be pinned to an exact commit; only our own platform app may follow a branch
	if app.get("name") != "nxerp" and not (commit and SHA.match(commit)):
		errors.append(f"{app.get('name')}: needs a 40-char commit pin")

env = dict(
	line.split("=", 1)
	for line in (DEPLOY / "versions.env").read_text().splitlines()
	if line and not line.startswith("#") and "=" in line
)
for key in ("FRAPPE_REPO", "FRAPPE_REF", "FRAPPE_COMMIT", "BENCH_IMAGE", "MARIADB_IMAGE", "REDIS_IMAGE"):
	if not env.get(key):
		errors.append(f"versions.env: missing {key}")
if env.get("FRAPPE_COMMIT") and not SHA.match(env["FRAPPE_COMMIT"]):
	errors.append("versions.env: FRAPPE_COMMIT must be a 40-char sha")
if env.get("BENCH_IMAGE") and "@sha256:" not in env["BENCH_IMAGE"]:
	errors.append("versions.env: BENCH_IMAGE must be pinned by digest")
if "nxerp" in names and names[-1] != "nxerp":
	errors.append("nxerp must be the last app so it installs after the apps it resolves")

if errors:
	print("\n".join(f"ERROR: {e}" for e in errors))
	sys.exit(1)
print(f"OK: {len(apps)} apps pinned, versions.env complete")
