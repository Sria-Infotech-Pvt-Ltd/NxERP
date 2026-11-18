#!/usr/bin/env bash
# Repeatable, read-only audit of how isolated the database login and the containers are. Changes nothing.
#
#   scripts/isolation_audit.sh grants | root-env | ports | all
#
#   grants    the site's own database login: one database-level grant, no global privilege, no host "%", no GRANT OPTION
#   root-env  the MariaDB root password is not in the environment of backend, websocket, queue-worker, scheduler
#   ports     exactly one service publishes a port (the proxy)
#   all       the three above; exit 1 if any line is FAIL
#
# Same environment variables as deploy/scripts/*.sh (NXERP_SITE, NXERP_COMPOSE_FILE, NXERP_COMPOSE_PROJECT,
# NXERP_ENV_FILES, NXERP_SERVICE): see deploy/scripts/lib.sh.
#
# Output lines are "PASS name", "FAIL name reason", "UNVERIFIED name reason" (with the command to run) or "INFO name text".
# Only counts, variable names and PASS/FAIL are printed: never a password, a password hash or a secret value.
# SQL runs as the site's own login, never as root. Exit status is 1 only for a real FAIL, never for UNVERIFIED.
set -euo pipefail
# shellcheck source=deploy/scripts/lib.sh
. "$(dirname "$0")/../deploy/scripts/lib.sh"

fail=0
pass() { printf 'PASS %s\n' "$1"; }
bad() { printf 'FAIL %s %s\n' "$1" "$2"; fail=1; }
unverified() { printf 'UNVERIFIED %s %s\n' "$1" "$2"; }
info() { printf 'INFO %s %s\n' "$1" "$2"; }

# stack_up: UNVERIFIED (return 1) when docker or the compose project cannot be reached
stack_up() {
	if ! command -v docker >/dev/null 2>&1; then
		unverified "$1" "docker is not installed here; run: docker version"
		return 1
	fi
	if [ -z "$(dc ps -q 2>/dev/null || true)" ]; then
		unverified "$1" "no running containers for this compose project; run: docker compose ${NXERP_COMPOSE_PROJECT:+-p $NXERP_COMPOSE_PROJECT }-f $NXERP_COMPOSE_FILE ps"
		return 1
	fi
}

audit_grants() {
	stack_up grants || return 0
	local sql out
	# SQL goes in on standard input so backticks stay literal. SHOW GRANTS carries a password hash: it is parsed here, never printed.
	sql=$'SHOW GRANTS FOR CURRENT_USER();\nSELECT CONCAT(\'CURRENT_USER=\', CURRENT_USER());\n'
	if ! out=$(printf '%s' "$sql" | bench_site mariadb 2>/dev/null); then
		unverified grants "could not run SQL as the site login; run: bench --site $NXERP_SITE mariadb"
		return 0
	fi

	local grants db_level global option host account
	grants=$(printf '%s\n' "$out" | tr -d '\r' | grep '^GRANT ' || true)
	if [ -z "$grants" ]; then
		unverified grants "SHOW GRANTS returned nothing; run: bench --site $NXERP_SITE mariadb, then SHOW GRANTS FOR CURRENT_USER();"
		return 0
	fi
	# the part before " TO " is the privilege list and the object; the part after holds the account and a password hash
	# shellcheck disable=SC2016 # the backticks are literal characters of the grant text
	db_level=$(printf '%s\n' "$grants" | sed 's/ TO .*//' | grep -Ec ' ON `[^`]+`\.\*$' || true)
	global=$(printf '%s\n' "$grants" | sed 's/ TO .*//' | grep -E ' ON \*\.\*$' | grep -vc '^GRANT USAGE ON' || true)
	option=$(printf '%s\n' "$grants" | grep -c 'WITH GRANT OPTION' || true)
	account=$(printf '%s\n' "$out" | tr -d '\r' | sed -n 's/^CURRENT_USER=//p' | head -n 1)
	host=${account##*@}

	if [ "$db_level" = 1 ]; then pass "grants-one-database-level-grant"; else bad grants-one-database-level-grant "found $db_level database-level grants, expected 1"; fi
	if [ "$global" = 0 ]; then pass "grants-no-global-privilege"; else bad grants-no-global-privilege "$global global (*.*) grant lines carry privileges"; fi
	if [ "$option" = 0 ]; then pass "grants-no-grant-option"; else bad grants-no-grant-option "$option grant lines include WITH GRANT OPTION"; fi
	if [ -z "$host" ]; then
		unverified grants-host "could not read CURRENT_USER(); run: SELECT CURRENT_USER();"
	elif [ "$host" = '%' ]; then
		bad grants-host-not-wildcard "the login's host is %, so any host on the network may connect with it"
	else
		pass "grants-host-not-wildcard"
	fi

	# the measured problem: how many installed apps share this one login (the site database holds all of them)
	local apps
	apps=$(bench_site list-apps 2>/dev/null | awk 'NF {n++} END {print n+0}' || echo 0)
	info grants-apps-sharing-this-login "$apps app(s) installed on $NXERP_SITE use this single database login"
	# other accounts: the site login normally cannot read mysql.user; that refusal is good, not an error
	if printf 'SELECT COUNT(*) FROM mysql.user;\n' | bench_site mariadb >/dev/null 2>&1; then
		info grants-mysql-user "the site login CAN read mysql.user (review: that is more than it needs)"
	else
		info grants-mysql-user "the site login cannot read mysql.user (expected)"
	fi
}

audit_root_env() {
	stack_up root-env || return 0
	local svc n
	for svc in backend websocket queue-worker scheduler; do
		if [ -z "$(dc ps -q "$svc" 2>/dev/null || true)" ]; then
			unverified "root-env-$svc" "service not running; run: docker compose ps $svc"
			continue
		fi
		# the length is computed inside the container: the value itself never leaves it
		# shellcheck disable=SC2016 # expanded inside the container on purpose
		n=$(dc exec -T "$svc" sh -c 'printf %s "${NXERP_DB_ROOT_PASSWORD:-}" | wc -c' 2>/dev/null | tr -d '[:space:]' || true)
		case "$n" in
			0) pass "root-env-$svc" ;;
			''|*[!0-9]*) unverified "root-env-$svc" "could not read the container environment; run: docker compose exec -T $svc env" ;;
			*) bad "root-env-$svc" "NXERP_DB_ROOT_PASSWORD is present in the environment ($n characters)" ;;
		esac
	done
}

audit_ports() {
	stack_up ports || return 0
	local rows published n
	if ! rows=$(dc ps --format '{{.Service}}|{{.Ports}}' 2>/dev/null); then
		unverified ports "could not list services; run: docker compose ps"
		return 0
	fi
	published=$(printf '%s\n' "$rows" | tr -d '\r' | awk -F'|' '$2 ~ /->/ {print $1}' | sort -u)
	n=$(printf '%s' "$published" | awk 'NF {c++} END {print c+0}')
	if [ "$n" = 1 ]; then
		pass "ports-one-published-service ($(printf '%s' "$published"))"
	else
		bad ports-one-published-service "$n services publish a port: $(printf '%s' "$published" | tr '\n' ' ')"
	fi
}

case "${1:-}" in
	grants) audit_grants ;;
	root-env) audit_root_env ;;
	ports) audit_ports ;;
	all) audit_grants; audit_root_env; audit_ports ;;
	*) die "usage: $0 grants | root-env | ports | all" ;;
esac
exit "$fail"
