#!/usr/bin/env bash
# Helpers for the CI job `upgrade-from-previous-tag` (.github/workflows/ci.yml). Runnable locally.
#
#   tools/ci_upgrade_test.sh previous-tag     print the newest stable release tag (vX.Y.Z, no suffix) that is an ancestor of HEAD;
#                                             print nothing (exit 0) when there is none, which is the case until the first release
#   tools/ci_upgrade_test.sh pin-diff TAG     say whether deploy/apps.json or deploy/versions.env changed since TAG
#
# What the job proves: a site installed from the PREVIOUS release's code (nxerp from tag TAG, with the upstream apps that tag
# pinned) migrates cleanly to THIS commit's nxerp code and then serves. What it does NOT prove: an upgrade of Frappe, ERPNext or
# Helpdesk themselves when their pins changed (the bench keeps the old upstream code); that rehearsal belongs to the staging-like
# environment with real images (docs/runbooks/migration-planning.md).
set -euo pipefail

case "${1:-}" in
previous-tag)
	# sort by version; exclude pre-releases (anything with a hyphen after the version, e.g. v1.0.0-rc.1)
	git tag --list 'v[0-9]*' --sort=-v:refname --merged HEAD | grep -Ev -- '-' | head -n 1 || true
	;;
pin-diff)
	tag=${2:?tag}
	if git diff --quiet "$tag" HEAD -- deploy/apps.json deploy/versions.env; then
		echo "unchanged"
	else
		echo "changed"
		git diff --stat "$tag" HEAD -- deploy/apps.json deploy/versions.env
	fi
	;;
*)
	sed -n '2,12p' "${BASH_SOURCE[0]}" >&2
	exit 2
	;;
esac
