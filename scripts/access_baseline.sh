#!/usr/bin/env bash
# Records, as HTTP status codes, who can reach what TODAY on the dev site. Phase 2 regression
# baseline: rerun after adding the app gate and compare. It changes nothing on the site.
#
#   NXERP_SEED_PASSWORD=<password used when seeding> NXERP_ADMIN_PASSWORD=<admin password> \
#     scripts/access_baseline.sh [base-url]
#
# Prints status codes only; never prints credentials.
set -uo pipefail

BASE=${1:-http://localhost:8100}
: "${NXERP_SEED_PASSWORD:?set the password used by nxerp.tests.seed_users}"
: "${NXERP_ADMIN_PASSWORD:?set the Administrator password (deploy/dev/.env)}"
jars=$(mktemp -d)
trap 'rm -rf "$jars"' EXIT

login() { # name user password
	curl -s -m 60 -c "$jars/$1" -X POST "$BASE/api/method/login" -d "usr=$2" --data-urlencode "pwd=$3" >/dev/null
}
code() { # name path...
	local who=$1 path=$2
	if [ "$who" = guest ]; then
		curl -s -m 60 -o /dev/null -w '%{http_code}' "$BASE$path"
	else
		curl -s -m 60 -b "$jars/$who" -o /dev/null -w '%{http_code}' "$BASE$path"
	fi
}

login admin Administrator "$NXERP_ADMIN_PASSWORD"
for u in agent manager erpuser customer; do login "$u" "$u@example.test" "$NXERP_SEED_PASSWORD"; done

users=(guest admin agent manager erpuser customer)
checks=(
	"/desk"
	"/desk/home"
	"/helpdesk/home"
	"/api/resource/Sales%20Invoice?limit_page_length=1"
	"/api/resource/Customer?limit_page_length=1"
	"/api/resource/HD%20Ticket?limit_page_length=1"
	"/api/v2/document/Sales%20Invoice?limit=1"
	"/api/method/frappe.client.get_count?doctype=Sales%20Invoice"
	"/api/method/frappe.desk.form.load.getdoctype?doctype=Sales%20Invoice"
	"/api/v2/doctype/Sales%20Invoice/meta"
	"/api/method/frappe.apps.get_apps"
	"/api/method/frappe.desk.desktop.get_installed_apps"
	"/api/v2/discovery/search?q=sales"
	"/api/resource/Workspace?limit_page_length=1"
	"/api/resource/Report?limit_page_length=1"
	"/api/method/frappe.desk.desk_page.getpage?name=point-of-sale"
	"/api/method/helpdesk.api.config.get_config"
	"/api/method/helpdesk.api.auth.get_user"
)

printf '%-82s' "request (HTTP status)"
printf '%-8s' "${users[@]}"
echo
for path in "${checks[@]}"; do
	printf '%-82s' "$path"
	for u in "${users[@]}"; do printf '%-8s' "$(code "$u" "$path")"; done
	echo
done

echo
printf 'Guest /helpdesk HTML exposes an "apps" list: '
curl -s -m 60 "$BASE/helpdesk" | grep -oE '"apps": ?\[[^]]*\]' | head -1 || true
echo
