"""Resolve the third-party Python dependency set of the whole NXERP bench WITHOUT starting it. Stdlib only.

Fetches Frappe (deploy/versions.env) and every app in deploy/apps.json at its pinned commit, asks pip to resolve them together
(`pip install --dry-run --report`), and writes `requirements.txt` (name==version, one per line, our own apps excluded).
CI feeds that file to pip-audit (job `dependency-audit`) and pip-licenses (job `license-check`).

	python3 -I tools/resolve_python_deps.py --out build/deps

A private app repository needs a read token in the environment variable named by --token-env (default GIT_READ_TOKEN); it is
sent as an HTTP header for the one fetch and is never written to disk or printed.
STATUS: `pip install --dry-run --report` was exercised for Frappe alone on the dev workstation (143 packages); the full run
(Frappe + all apps) has not been executed: ERPNext cannot be checked out on Windows (path length), so it happens in CI.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPANY_ORGS = ("Sriainfotech", "Sria-Infotech-Pvt-Ltd")


def run(cmd, **kwargs):
	return subprocess.run(cmd, check=True, **kwargs)


def read_env(path):
	rows = (
		line.split("=", 1)
		for line in path.read_text().splitlines()
		if line and not line.startswith("#") and "=" in line
	)
	return {key: value for key, value in rows}


def fetch(name, url, commit, dest, token):
	dest.mkdir(parents=True, exist_ok=True)
	run(["git", "init", "-q", str(dest)])
	run(["git", "-C", str(dest), "remote", "add", "origin", url])
	auth = []
	# the token only goes to the company organisations' repositories, never to upstream hosts
	if token and any(f"/{org}/" in url for org in COMPANY_ORGS):
		header = base64.b64encode(f"x-access-token:{token}".encode()).decode()
		auth = ["-c", f"http.extraheader=AUTHORIZATION: basic {header}"]
	run(["git", "-C", str(dest), *auth, "fetch", "-q", "--depth", "1", "origin", commit])
	run(["git", "-C", str(dest), "checkout", "-q", "--detach", "FETCH_HEAD"])
	print(f"{name} @ {commit[:10]}", file=sys.stderr)


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--out", default="build/deps", help="output directory (default build/deps)")
	parser.add_argument(
		"--token-env", default="GIT_READ_TOKEN", help="env var holding a read token for private repositories"
	)
	args = parser.parse_args()

	out = Path(args.out).resolve()
	src = out / "src"
	token = os.environ.get(args.token_env, "")
	env = read_env(ROOT / "deploy" / "versions.env")
	apps = json.loads((ROOT / "deploy" / "apps.json").read_text())

	targets = []
	fetch("frappe", env["FRAPPE_REPO"], env["FRAPPE_COMMIT"], src / "frappe", token)
	targets.append(str(src / "frappe"))
	for app in apps:
		if app["name"] == "nxerp":
			targets.append(str(ROOT))  # the platform app is this checkout
			continue
		fetch(app["name"], app["url"], app["commit"], src / app["name"], token)
		targets.append(str(src / app["name"]))

	report = out / "report.json"
	run(
		[
			sys.executable,
			"-m",
			"pip",
			"install",
			"--dry-run",
			"--ignore-installed",
			"--quiet",
			"--report",
			str(report),
			*targets,
		]
	)
	install = json.loads(report.read_text(encoding="utf-8"))["install"]
	third_party = sorted(
		f"{item['metadata']['name']}=={item['metadata']['version']}"
		for item in install
		if not item.get("download_info", {}).get("url", "").startswith("file:")
	)
	(out / "requirements.txt").write_text("\n".join(third_party) + "\n")
	print(f"{len(third_party)} third-party packages -> {out / 'requirements.txt'}", file=sys.stderr)


if __name__ == "__main__":
	main()
