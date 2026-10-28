"""Check commit subjects (and a PR title) against the Conventional Commits rules in docs/governance/contribution-policy.md.
Stdlib only.

	python3 -I tools/check_commits.py                      # origin/main..HEAD, or every commit when there is no origin/main
	python3 -I tools/check_commits.py --range main..HEAD
	python3 -I tools/check_commits.py --title "feat(access): add grant API"   # a PR title (squash merges use it as the commit)

Format:  type(scope)!: summary     scope optional; `!` marks a breaking change; several types may be joined with a comma
(`docs,ci: ...`, used in this repository's history). Types: feat fix docs chore ci test refactor perf build style revert.
Rules: subject at most --max-length (default 100) characters, summary not empty, no trailing period. Merge commits and `fixup!`/`squash!` are skipped
(squash merge removes them; a `fixup!` that reaches a PR is reported by the PR review, not here).
"""

import argparse
import re
import subprocess
import sys

TYPES = "feat|fix|docs|chore|ci|test|refactor|perf|build|style|revert"
PATTERN = re.compile(rf"^(?:{TYPES})(?:,(?:{TYPES}))*(?:\([a-z0-9][a-z0-9._/-]*\))?!?: \S.*$")
MAX_LENGTH = 100


def problems(subject, max_length=MAX_LENGTH):
	if subject.startswith(("Merge ", "fixup!", "squash!")):
		return []
	found = []
	if not PATTERN.match(subject):
		found.append("does not match `type(scope): summary` (types: " + TYPES.replace("|", ", ") + ")")
	if len(subject) > max_length:
		found.append(f"subject is {len(subject)} characters (max {max_length})")
	if subject.endswith("."):
		found.append("subject ends with a period")
	return found


def git_subjects(rev_range):
	out = subprocess.run(
		["git", "log", "--format=%h%x09%s", *([rev_range] if rev_range else [])],
		check=True,
		capture_output=True,
		text=True,
	).stdout
	return [line.split("\t", 1) for line in out.splitlines() if line]


def has_ref(ref):
	return (
		subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], capture_output=True).returncode == 0
	)


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--range", dest="rev_range", help="git revision range (default origin/main..HEAD)")
	parser.add_argument("--title", help="check a single PR title instead of git history")
	parser.add_argument(
		"--max-length", type=int, default=MAX_LENGTH, help=f"longest allowed subject (default {MAX_LENGTH})"
	)
	args = parser.parse_args()

	if args.title is not None:
		items = [("title", args.title)]
	else:
		rev_range = args.rev_range or ("origin/main..HEAD" if has_ref("origin/main") else None)
		items = git_subjects(rev_range)
		print(f"checking {len(items)} commit(s) in {rev_range or 'the whole history'}")

	failed = 0
	for ref, subject in items:
		for problem in problems(subject, args.max_length):
			failed += 1
			print(f"FAIL {ref}: {subject!r}: {problem}")
	print("commit messages OK" if not failed else f"{failed} problem(s)")
	return 1 if failed else 0


if __name__ == "__main__":
	sys.exit(main())
