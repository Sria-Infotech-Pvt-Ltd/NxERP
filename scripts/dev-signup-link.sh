#!/usr/bin/env bash
# Local test sites only: carry on with onboarding without the verification email.
#
#   scripts/dev-signup-link.sh <hd|erp> <email> ["Full name"]            print the set-password link for that sign-up
#   DEV_PASSWORD='...' scripts/dev-signup-link.sh <hd|erp> <email>       set the password directly instead
#
# Typical use: fill in the sign-up form on the site, then run this with the same email, open the link it prints, set a password, sign in and
# continue with the first-run screens (/welcome/<product>). The script refuses to run on any site that is not a local test site.
set -euo pipefail
export MSYS_NO_PATHCONV=1
stack="${1:?usage: $0 <hd|erp> <email> [full name]}"
email="${2:?usage: $0 <hd|erp> <email> [full name]}"
name="${3:-Test User}"
case "$stack" in hd) app=helpdesk ;; erp) app=erpnext ;; *) echo "stack must be hd or erp (the identity site has no sign-up of its own)" >&2; exit 2 ;; esac
cid="$(docker compose -p "nxerp-$stack" ps -q backend | head -n 1)"
[ -n "$cid" ] || { echo "the $stack backend is not running (docker compose -p nxerp-$stack ps)" >&2; exit 1; }
site="$(docker exec "$cid" bash -lc "ls /home/frappe/frappe-bench/sites | grep -E '^$stack\\.' | head -n 1")"
here="$(cd "$(dirname "$0")" && pwd)"
src="$here/dev_signup_link.py"
if command -v cygpath >/dev/null 2>&1; then src="$(cygpath -m "$src")"; fi # Git Bash path -> the form docker.exe reads
docker cp "$src" "$cid:/home/frappe/frappe-bench/apps/nxerp/nxerp/dev_signup_link.py"
docker exec -u root "$cid" chown frappe:frappe /home/frappe/frappe-bench/apps/nxerp/nxerp/dev_signup_link.py
set +e
docker exec -e DEV_EMAIL="$email" -e DEV_NAME="$name" -e DEV_APP="$app" -e DEV_PASSWORD="${DEV_PASSWORD:-}" "$cid" \
	bash -lc "cd /home/frappe/frappe-bench && bench --site $site execute nxerp.dev_signup_link.run 2>&1 | grep -E 'DEV|refused|rror' | grep -v CSSStyle"
rc=$?
docker exec "$cid" rm -f /home/frappe/frappe-bench/apps/nxerp/nxerp/dev_signup_link.py
exit $rc
