"""Release notes from Conventional Commits. Stdlib + git.

	python3 -I scripts/changelog.py --version 0.1.0 [--from v0.0.9] [--to HEAD]

`--from` defaults to the newest stable release tag (vX.Y.Z) before `--to`; with none, the whole history is used. Output is Markdown
on stdout. Types without a section are listed under "Other changes"; breaking changes (`type!:` or a `BREAKING CHANGE:` footer)
are listed first. Commits that do not follow the format are listed under "Unclassified" so nothing is hidden.
"""

import argparse
import re
import subprocess
import sys

SECTIONS = [
	("feat", "Features"),
	("fix", "Fixes"),
	("perf", "Performance"),
	("refactor", "Refactoring"),
	("docs", "Documentation"),
	("test", "Tests"),
	("ci", "CI and build"),
	("build", "CI and build"),
	("chore", "Maintenance"),
	("style", "Maintenance"),
	("revert", "Reverts"),
]
HEADER = re.compile(r"^(?P<types>[a-z]+(?:,[a-z]+)*)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?: (?P<summary>.+)$")


def git(*args):
	return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def previous_tag(to):
	tags = git("tag", "--list", "v[0-9]*", "--sort=-v:refname", "--merged", to).split()
	stable = [tag for tag in tags if "-" not in tag]
	return stable[0] if stable else None


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--version", required=True)
	parser.add_argument("--from", dest="start")
	parser.add_argument("--to", default="HEAD")
	args = parser.parse_args()

	start = args.start or previous_tag(args.to)
	log = git(
		"log", "--no-merges", "--format=%h%x1f%s%x1f%b%x1e", f"{start}..{args.to}" if start else args.to
	)
	grouped, breaking, unclassified = {}, [], []
	count = 0
	for record in log.split("\x1e"):
		if not record.strip():
			continue
		sha, subject, body = [*record.strip("\n").split("\x1f"), "", ""][:3]
		match = HEADER.match(subject)
		if not match:
			unclassified.append(f"- {subject} ({sha})")
			continue
		scope = f"**{match['scope']}**: " if match["scope"] else ""
		line = f"- {scope}{match['summary']} ({sha})"
		if match["bang"] or "BREAKING CHANGE:" in body:
			breaking.append(line)
		first = match["types"].split(",")[0]
		title = dict(SECTIONS).get(first, "Other changes")
		grouped.setdefault(title, []).append(line)
		count += 1

	print(f"# NXERP {args.version}\n")
	print(f"Changes since {start or 'the beginning of the history'} ({count} conventional commits).\n")
	if breaking:
		print("## Breaking changes\n")
		print("\n".join(breaking) + "\n")
	order = [*dict.fromkeys(title for _, title in SECTIONS), "Other changes"]
	for title in order:
		if title in grouped:
			print(f"## {title}\n")
			print("\n".join(grouped[title]) + "\n")
	if unclassified:
		print("## Unclassified (not Conventional Commits)\n")
		print("\n".join(unclassified) + "\n")
	print(
		"Pinned upstream versions for this release are in `deploy/versions.env` and `deploy/apps.json` (ADR-002)."
	)


if __name__ == "__main__":
	sys.exit(main())
