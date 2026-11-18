"""Compare the pinned upstream versions with what upstream has published, and list recent security advisories. Stdlib + git.

	python3 -I scripts/upstream_watch.py                    # markdown report on stdout
	python3 -I scripts/upstream_watch.py --days 30          # advisory look-back window (default 14)

Reads deploy/versions.env (Frappe) and deploy/apps.json (ERPNext, payments, telephony, Helpdesk fork). Helpdesk is pinned to a
commit of the company fork, so its upstream base release is recorded in HELPDESK_UPSTREAM_BASE below and must equal ADR-002.
Exit code 0 always; the last line is `CHANGES=<n>` (the number of findings) for the workflow to act on. A GITHUB_TOKEN in the
environment raises the API rate limit; it is optional for public repositories and is never printed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPDESK_UPSTREAM_BASE = "v1.31.0"  # ADR-002: upstream release the company commits are re-applied on
WATCHED_ADVISORY_REPOS = [
	"frappe/frappe",
	"frappe/erpnext",
	"frappe/helpdesk",
	"frappe/payments",
	"frappe/telephony",
]
STABLE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def tags(repo):
	out = subprocess.run(
		["git", "ls-remote", "--tags", "--refs", f"https://github.com/{repo}.git"],
		check=True,
		capture_output=True,
		text=True,
	).stdout
	return [line.split("refs/tags/", 1)[1] for line in out.splitlines() if "refs/tags/" in line]


def latest_stable(repo, major=None):
	found = []
	for tag in tags(repo):
		match = STABLE_TAG.match(tag)
		if match and (major is None or int(match.group(1)) == major):
			found.append((tuple(int(part) for part in match.groups()), tag))
	return max(found)[1] if found else None


def branch_head(repo, branch):
	out = subprocess.run(
		["git", "ls-remote", f"https://github.com/{repo}.git", f"refs/heads/{branch}"],
		check=True,
		capture_output=True,
		text=True,
	).stdout
	return out.split()[0] if out.strip() else None


def parse_version(text):
	match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
	return tuple(int(part) for part in match.groups()) if match else None


def affects(advisory, pinned):
	"""True / False when GitHub's patched_versions say whether `pinned` is below a fix on its own major line; None when unknown."""
	pin = parse_version(pinned)
	if pin is None:
		return None
	verdicts = []
	for vulnerability in advisory.get("vulnerabilities", []):
		patched = parse_version(vulnerability.get("patched_versions"))
		if patched is not None and patched[0] == pin[0]:
			verdicts.append(pin < patched)
	return any(verdicts) if verdicts else None


def advisories(repo, since):
	url = f"https://api.github.com/repos/{repo}/security-advisories?state=published&per_page=30"
	request = urllib.request.Request(
		url, headers={"Accept": "application/vnd.github+json", "User-Agent": "nxerp-upstream-watch"}
	)
	if os.environ.get("GITHUB_TOKEN"):
		request.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
	try:
		with urllib.request.urlopen(request, timeout=30) as response:
			items = json.load(response)
	except urllib.error.URLError as error:
		return None, str(error)
	recent = [i for i in items if datetime.fromisoformat(i["published_at"].replace("Z", "+00:00")) >= since]
	return recent, None


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--days", type=int, default=14, help="advisory look-back window in days")
	args = parser.parse_args()

	env = dict(
		line.split("=", 1)
		for line in (ROOT / "deploy" / "versions.env").read_text(encoding="utf-8").splitlines()
		if line and not line.startswith("#") and "=" in line
	)
	apps = {
		app["name"]: app for app in json.loads((ROOT / "deploy" / "apps.json").read_text(encoding="utf-8"))
	}
	findings, notes = [], []

	frappe_major = int(re.match(r"v(\d+)", env["FRAPPE_REF"]).group(1))
	rows = [
		("Frappe", "frappe/frappe", env["FRAPPE_REF"], latest_stable("frappe/frappe", frappe_major)),
		(
			"ERPNext",
			"frappe/erpnext",
			apps["erpnext"]["branch"],
			latest_stable("frappe/erpnext", frappe_major),
		),
		(
			"Helpdesk (upstream base of the company fork)",
			"frappe/helpdesk",
			HELPDESK_UPSTREAM_BASE,
			latest_stable("frappe/helpdesk"),
		),
	]
	table = ["| Component | Pinned | Latest upstream release | Status |", "| --- | --- | --- | --- |"]
	for name, _repo, pinned, latest in rows:
		status = "current" if latest == pinned else "**newer release available**"
		if latest != pinned:
			findings.append(f"{name}: pinned {pinned}, upstream has {latest}")
		table.append(f"| {name} | `{pinned}` | `{latest}` | {status} |")

	for name in ("payments", "telephony"):
		app = apps[name]
		repo = app["url"].removeprefix("https://github.com/")
		head = branch_head(repo, app["branch"])
		moved = head is not None and head != app["commit"]
		table.append(
			f"| {name} (branch `{app['branch']}`, no releases) | `{app['commit'][:10]}` | head `{(head or '?')[:10]}` | "
			+ ("branch moved (review the diff before repinning)" if moved else "current")
			+ " |"
		)
		if moved:
			notes.append(f"{name}: branch `{app['branch']}` moved past the pinned commit (informational)")

	since = datetime.now(UTC) - timedelta(days=args.days)
	pins = {
		"frappe/frappe": env["FRAPPE_REF"],
		"frappe/erpnext": apps["erpnext"]["branch"],
		"frappe/helpdesk": HELPDESK_UPSTREAM_BASE,
	}
	advisory_lines = []
	for repo in WATCHED_ADVISORY_REPOS:
		items, error = advisories(repo, since)
		if error:
			advisory_lines.append(f"- `{repo}`: could not query advisories ({error})")
			continue
		for item in items:
			verdict = affects(item, pins.get(repo))
			label = {
				True: "**AFFECTS the pinned version**",
				False: "fixed at or below the pin",
				None: "pin vs fix UNKNOWN: check",
			}[verdict]
			if verdict is not False:
				findings.append(f"security advisory in {repo}: {item['ghsa_id']} ({item.get('severity')})")
			advisory_lines.append(
				f"- **{repo}** [{item['ghsa_id']}]({item['html_url']}) {item.get('severity')}, {label}: {item['summary']}"
			)
	if not advisory_lines:
		advisory_lines.append(
			f"- none published in the last {args.days} days for: {', '.join(WATCHED_ADVISORY_REPOS)}"
		)

	print("## Upstream versions\n")
	print("\n".join(table))
	print(f"\n## Security advisories (published in the last {args.days} days)\n")
	print("\n".join(advisory_lines))
	if notes:
		print("\n## Notes\n")
		print("\n".join(f"- {note}" for note in notes))
	print(
		"\nWhat to do: docs/runbooks/upstream-security-update.md. A new release is taken by changing the pin, updating ADR-002 and"
	)
	print("rebuilding from scratch; nothing here changes a pin automatically.")
	print(f"\nCHANGES={len(findings)}", file=sys.stderr)


if __name__ == "__main__":
	main()
