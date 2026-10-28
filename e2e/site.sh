#!/usr/bin/env bash
# Creates (or drops) the FRESH site the browser suite runs against: nxerp-e2e.localhost, with the same apps as
# the dev site and NO setup wizard completed, so the first-run flow is real. The dev site is never touched.
#
#   e2e/site.sh create    # ~10 minutes the first time
#   e2e/site.sh drop      # remove it (and its database)
#   e2e/site.sh snapshot  # save the pristine database (do this once, before any wizard)
#   e2e/site.sh reset     # restore the pristine database: the first-run flow is repeatable
#   e2e/site.sh status
set -uo pipefail
cd "$(dirname "$0")/../deploy/dev" || exit 1
set -a
# shellcheck disable=SC1091
. ./.env
set +a
DC=(docker compose -p nxerp-dev -f compose.yaml)
SITE=nxerp-e2e.localhost

inside() {
	"${DC[@]}" exec -T -e NXERP_DB_ROOT_PASSWORD="$NXERP_DB_ROOT_PASSWORD" -e NXERP_ADMIN_PASSWORD="$NXERP_ADMIN_PASSWORD" bench bash -lc "$1"
}

case "${1:-status}" in
create)
	inside "cd ~/frappe-bench && if [ -d sites/$SITE ]; then echo 'already exists'; exit 0; fi
		bench new-site $SITE --mariadb-root-password \"\$NXERP_DB_ROOT_PASSWORD\" --admin-password \"\$NXERP_ADMIN_PASSWORD\" --no-mariadb-socket &&
		for app in payments erpnext telephony helpdesk nxerp; do bench --site $SITE install-app \$app || exit 1; done &&
		bench --site $SITE set-config developer_mode 1 &&
		bench --site $SITE set-config allow_tests 1 &&
		bench --site $SITE set-config mute_emails 1 &&
		bench --site $SITE set-config -p throttle_user_limit 100000 &&
		bench --site $SITE set-config host_name http://localhost:8001 &&
		bench --site $SITE clear-cache"
	;;
drop)
	inside "cd ~/frappe-bench && bench drop-site $SITE --force --root-password \"\$NXERP_DB_ROOT_PASSWORD\" --no-backup 2>&1 | tail -3"
	;;
snapshot)
	# the pristine, installed-but-not-set-up database, so the first-run flow is repeatable
	inside "cd ~/frappe-bench && bench --site $SITE backup --backup-path /home/frappe/frappe-bench/e2e-fresh >/dev/null 2>&1 &&
		cp \$(ls -t e2e-fresh/*-database.sql.gz | head -1) e2e-fresh/fresh.sql.gz && ls -la e2e-fresh/fresh.sql.gz"
	;;
reset)
	inside "cd ~/frappe-bench && test -f e2e-fresh/fresh.sql.gz || { echo 'no snapshot: run e2e/site.sh snapshot on a fresh site' >&2; exit 1; }
		bench --site $SITE restore e2e-fresh/fresh.sql.gz --db-root-password \"\$NXERP_DB_ROOT_PASSWORD\" --force 2>&1 | tail -2 &&
		bench --site $SITE set-config developer_mode 1 && bench --site $SITE set-config allow_tests 1 &&
		bench --site $SITE set-config mute_emails 1 && bench --site $SITE set-config -p throttle_user_limit 100000 &&
		bench --site $SITE set-config host_name http://localhost:8001 && bench --site $SITE clear-cache"
	;;
reinstall)
	inside "cd ~/frappe-bench && bench --site $SITE reinstall --yes --admin-password \"\$NXERP_ADMIN_PASSWORD\" --db-root-password \"\$NXERP_DB_ROOT_PASSWORD\" 2>&1 | tail -3"
	;;
status)
	inside "cd ~/frappe-bench && ls -d sites/$SITE 2>/dev/null && bench --site $SITE list-apps 2>/dev/null"
	;;
*) echo "usage: $0 create|snapshot|reset|drop|status" >&2; exit 2 ;;
esac
