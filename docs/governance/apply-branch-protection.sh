#!/usr/bin/env bash
# Apply the repository governance settings described in docs/governance/branch-protection.md with the GitHub CLI.
#
#   docs/governance/apply-branch-protection.sh                  DRY RUN (default): prints every command and JSON body, changes nothing
#   docs/governance/apply-branch-protection.sh --apply          really call the GitHub API (needs a token with repository ADMIN rights)
#
# Options (combine freely; the base set is always branch protection + merge settings):
#   --repo OWNER/NAME        default Sria-Infotech-Pvt-Ltd/NxERP
#   --branch NAME            default main
#   --reviews 1|2            required approving reviews (default 1; use 2 once there are at least three reviewers)
#   --with-security          enable secret scanning, push protection, Dependabot alerts and security updates
#   --with-tags              ruleset that makes release tags v* immutable (no update, no delete)
#   --with-environments      create GitHub Environments `staging` and `production` (production gets required reviewers from
#                            PRODUCTION_REVIEWERS="login1,login2" and prevent-self-review)
#
# STATUS: NEVER APPLIED. The account used to write it has READ-only access, so even the dry run could only be checked for
# syntax: JSON bodies are validated as JSON, nothing is sent to GitHub. `ci-gate` must have run at least once on the repository
# before it can be selected as a required check in the UI; the API accepts the name earlier but then no PR can ever merge if the
# check never reports, so run CI once first.
set -euo pipefail

repo=Sria-Infotech-Pvt-Ltd/NxERP branch=main reviews=1 apply=0 security=0 tags=0 environments=0
while [ $# -gt 0 ]; do
	case "$1" in
		--apply) apply=1 ;;
		--repo) repo=${2:?}; shift ;;
		--branch) branch=${2:?}; shift ;;
		--reviews) reviews=${2:?}; shift ;;
		--with-security) security=1 ;;
		--with-tags) tags=1 ;;
		--with-environments) environments=1 ;;
		-h | --help) sed -n '2,20p' "$0"; exit 0 ;;
		*) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
	esac
	shift
done
[[ "$reviews" =~ ^[12]$ ]] || { echo "--reviews must be 1 or 2" >&2; exit 2; }

if [ "$apply" = 1 ]; then
	command -v gh >/dev/null || { echo "gh (GitHub CLI) is required for --apply" >&2; exit 1; }
	gh auth status >/dev/null 2>&1 || { echo "gh is not logged in: run 'gh auth login' with an account that has admin rights on $repo" >&2; exit 1; }
	echo "APPLYING to $repo (branch $branch). Press Ctrl-C within 5 s to abort."
	sleep 5
else
	echo "DRY RUN: nothing is sent to GitHub. Add --apply to execute. Target: $repo, branch $branch."
fi

# call METHOD ENDPOINT JSON  : print (dry) or execute (apply) one gh api call with a JSON body
call() {
	local method=$1 endpoint=$2 body=${3:-}
	if [ -n "$body" ]; then
		printf '%s' "$body" | python3 -c 'import json, sys; json.load(sys.stdin)' 2>/dev/null \
			|| printf '%s' "$body" | python -c 'import json, sys; json.load(sys.stdin)' \
			|| { echo "internal error: invalid JSON body for $endpoint" >&2; exit 1; }
	fi
	if [ "$apply" = 1 ]; then
		echo ">> $method $endpoint"
		if [ -n "$body" ]; then printf '%s' "$body" | gh api -X "$method" "$endpoint" --input - >/dev/null; else gh api -X "$method" "$endpoint" >/dev/null; fi
	else
		echo
		echo "+ gh api -X $method $endpoint ${body:+--input - <<'JSON'}"
		[ -z "$body" ] || printf '%s\nJSON\n' "$body"
	fi
}

# 1. Branch protection on main -------------------------------------------------------------------------------------------------
protection=$(cat <<JSON
{
  "required_status_checks": { "strict": true, "checks": [ { "context": "ci-gate" } ] },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": $reviews,
    "require_code_owner_reviews": true,
    "dismiss_stale_reviews": true,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
JSON
)
call PUT "repos/$repo/branches/$branch/protection" "$protection"

# 2. Repository merge settings: squash only, delete head branches after merge -----------------------------------------------------
merge_settings=$(cat <<'JSON'
{
  "allow_squash_merge": true,
  "allow_merge_commit": false,
  "allow_rebase_merge": false,
  "squash_merge_commit_title": "PR_TITLE",
  "squash_merge_commit_message": "PR_BODY",
  "delete_branch_on_merge": true,
  "allow_auto_merge": false,
  "allow_update_branch": true
}
JSON
)
call PATCH "repos/$repo" "$merge_settings"

# 3. Optional: security features ---------------------------------------------------------------------------------------------------
if [ "$security" = 1 ]; then
	call PATCH "repos/$repo" '{"security_and_analysis":{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}}'
	call PUT "repos/$repo/vulnerability-alerts"
	call PUT "repos/$repo/automated-security-fixes"
	echo '# CodeQL: the workflow job "codeql" uploads results; on a private repository that needs GitHub Advanced Security (Settings > Code security).' >&2
fi

# 4. Optional: immutable release tags ---------------------------------------------------------------------------------------------
if [ "$tags" = 1 ]; then
	call POST "repos/$repo/rulesets" '{"name":"release tags are immutable","target":"tag","enforcement":"active","conditions":{"ref_name":{"include":["refs/tags/v*"],"exclude":[]}},"rules":[{"type":"deletion"},{"type":"update"},{"type":"non_fast_forward"}]}'
fi

# 5. Optional: Environments ---------------------------------------------------------------------------------------------------------
if [ "$environments" = 1 ]; then
	call PUT "repos/$repo/environments/staging" '{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}'
	# both deploy workflows run from the default branch (workflow_run and workflow_dispatch use main's workflow file) and check out
	# the release tag themselves, so the Environment's deployment ref is `main`, not the tag
	call POST "repos/$repo/environments/staging/deployment-branch-policies" '{"name":"main","type":"branch"}'

	reviewers_json=
	if [ -z "${PRODUCTION_REVIEWERS:-}" ]; then
		echo "# PRODUCTION_REVIEWERS is not set: the production Environment would get NO required reviewers. Set it (comma-separated logins) before applying." >&2
		[ "$apply" = 0 ] || { echo "refusing to create a production Environment without reviewers" >&2; exit 1; }
		reviewers_json='{"type":"User","id":0}'
	else
		IFS=',' read -r -a logins <<<"$PRODUCTION_REVIEWERS"
		for login in "${logins[@]}"; do
			if [ "$apply" = 1 ]; then id=$(gh api "users/$login" --jq .id); else id=0; echo "# dry run: the real id of $login is looked up with 'gh api users/$login --jq .id'" >&2; fi
			[ -z "$reviewers_json" ] || reviewers_json+=,
			reviewers_json+="{\"type\":\"User\",\"id\":$id}"
		done
	fi
	call PUT "repos/$repo/environments/production" "{\"wait_timer\":0,\"prevent_self_review\":true,\"reviewers\":[$reviewers_json],\"deployment_branch_policy\":{\"protected_branches\":false,\"custom_branch_policies\":true}}"
	call POST "repos/$repo/environments/production/deployment-branch-policies" '{"name":"main","type":"branch"}'
	echo "# Environment secrets/variables (DEPLOY_SSH_KEY, DEPLOY_HOST, ...) are NOT set by this script: see deploy/environments/README.md." >&2
fi

echo
if [ "$apply" = 1 ]; then
	echo "applied. Verify with: gh api repos/$repo/branches/$branch/protection --jq '{checks: .required_status_checks.checks, reviews: .required_pull_request_reviews.required_approving_review_count, admins: .enforce_admins.enabled, linear: .required_linear_history.enabled}'"
else
	echo "dry run complete: no call was made."
fi
