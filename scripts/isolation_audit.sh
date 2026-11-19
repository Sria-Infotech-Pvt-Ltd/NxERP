#!/usr/bin/env bash
# Repeatable, read-only audit of how isolated the database login and the containers are. Changes nothing.
#
#   scripts/isolation_audit.sh grants | root-env | ports | all
#
#   grants    the site's own database login: one database-level grant, no global privilege, no host "%", no GRANT OPTION
#   root-env  the MariaDB root password is not in the environment of backend, websocket, queue-worker, scheduler
#   ports     exactly one service publishes a port (the proxy)
#   cross-read  isolated stacks: as one stack's login, SELECT and DELETE on another stack's database must give error 1142 or 1044
#   reach       isolated stacks: from a stack's backend, the other tier's database, other stacks' Redis and the shared database must be unreachable
#   published   isolated stacks: no database or stack container publishes a port; the edge only on 127.0.0.1
#   hostnames   isolated stacks: every host in stacks.list answers ping through the edge; /api/method/nxerp.shared.* answers 404
#   stacks      the grants and root-env audits once per stack in deploy/env/isolated/stacks.list
#   all         every audit above except `stacks`; several commands may be given: isolation_audit.sh cross-read reach ports
#               (exit 1 if any line is FAIL)
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

# ---- isolated stacks (Phase 5): one authoritative database per stack; see deploy/docker/compose/isolated/README.md ----------------------
ISO_ENV_DIR=deploy/env/isolated
ISO_COMPOSE_DIR=deploy/docker/compose/isolated

iso_stacks() { [ -f "$ISO_ENV_DIR/stacks.list" ] && awk '$1 !~ /^#/ && NF >= 3 {print $1}' "$ISO_ENV_DIR/stacks.list" || true; }
iso_tier() { tr -d '\015' <"$ISO_ENV_DIR/stacks.list" | awk -v n="$1" '$1 == n && $1 !~ /^#/ {print $3}'; }
iso_env() { [ -f "$1" ] && sed -n "s/^$2=//p" "$1" | head -n 1 | tr -d '\r' || true; }

# iso_ready NAME: UNVERIFIED (return 1) when there is no stacks.list or docker is missing
iso_ready() {
	if [ -z "$(iso_stacks)" ]; then
		unverified "$1" "no $ISO_ENV_DIR/stacks.list with stacks; copy stacks.list.example and start the stacks (deploy/scripts/stack.sh)"
		return 1
	fi
	if ! command -v docker >/dev/null 2>&1; then
		unverified "$1" "docker is not installed here; run: docker version"
		return 1
	fi
}

# iso_db_name STACK: the stack's database name (not a secret), read as the stack's own login
iso_db_name() {
	printf 'SELECT DATABASE();\n' | deploy/scripts/stack.sh "$1" bench mariadb 2>/dev/null | tr -d '\r' | awk 'NF {last = $0} END {print last}'
}

# T1 (cross-read): as stack A's login, SELECT and DELETE ... WHERE 1=0 on stack B's database. PASS only on error 1142 or 1044.
audit_cross_read() {
	iso_ready cross-read || return 0
	local a b db sql out code verb
	declare -A dbname=()
	for a in $(iso_stacks); do
		db="$(iso_db_name "$a")"
		if [ -z "$db" ]; then
			unverified "cross-read-$a" "could not read the database name as $a's login; run: deploy/scripts/stack.sh $a bench mariadb"
			continue
		fi
		dbname[$a]="$db"
	done
	for a in "${!dbname[@]}"; do
		for b in "${!dbname[@]}"; do
			[ "$a" != "$b" ] || continue
			for verb in SELECT DELETE; do
				if [ "$verb" = SELECT ]; then
					sql="SELECT 1 FROM \`${dbname[$b]}\`.tabSeries LIMIT 1;"
				else
					sql="DELETE FROM \`${dbname[$b]}\`.tabSeries WHERE 1=0;"
				fi
				out="$(printf '%s\n' "$sql" | deploy/scripts/stack.sh "$a" bench mariadb 2>&1 || true)"
				code="$(printf '%s' "$out" | sed -n 's/.*ERROR \([0-9][0-9]*\).*/\1/p' | head -n 1)"
				case "$code" in
					1142 | 1044) pass "cross-read-$a-cannot-$verb-$b (error $code)" ;;
					'')
						if printf '%s' "$out" | grep -q 'Error response\|No such\|not running'; then
							unverified "cross-read-$a-$verb-$b" "could not run SQL as $a; run: deploy/scripts/stack.sh $a bench mariadb"
						else
							bad "cross-read-$a-$verb-$b" "the statement was NOT refused ($a's login can reach $b's database)"
						fi
						;;
					*) bad "cross-read-$a-$verb-$b" "refused with error $code, expected 1142 or 1044" ;;
				esac
			done
		done
	done
}

# T2 (reach): from stack A's backend, a TCP connection to the other tier's database, to the other stacks' Redis servers and to the shared database must FAIL.
tcp_from() { # stack host port -> "REACHABLE" | "blocked" | "" (could not run)
	docker compose -p "nxerp-$1" exec -T backend bash -c "timeout 3 bash -c '</dev/tcp/$2/$3' 2>/dev/null && echo REACHABLE || echo blocked" 2>/dev/null | tr -d '\r' | tail -n 1
}

reach_check() { # name stack host port
	local result
	result="$(tcp_from "$2" "$3" "$4")"
	case "$result" in
		blocked) pass "reach-$1" ;;
		REACHABLE) bad "reach-$1" "$2's backend can open $3:$4" ;;
		*) unverified "reach-$1" "could not run in nxerp-$2 backend; run: docker compose -p nxerp-$2 ps" ;;
	esac
}

audit_reach() {
	iso_ready reach || return 0
	local a b tier host ip port
	for a in $(iso_stacks); do
		tier="$(iso_tier "$a")"
		for host in mariadb-standard mariadb-restricted; do
			[ "$host" != "mariadb-$tier" ] || continue
			reach_check "$a-to-$host-database" "$a" "$host" 3306
		done
		reach_check "$a-to-shared-database" "$a" shared-db 3306
		for b in $(iso_stacks); do
			[ "$a" != "$b" ] || continue
			for port in redis-cache redis-queue; do
				ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "nxerp-$b-$port-1" 2>/dev/null | awk '{print $1}')"
				if [ -z "$ip" ]; then
					unverified "reach-$a-to-$b-$port" "container nxerp-$b-$port-1 not found; run: docker ps"
					continue
				fi
				reach_check "$a-to-$b-$port" "$a" "$ip" 6379
			done
		done
	done
}

# published: no database or stack container publishes a port; the edge publishes only on 127.0.0.1
audit_published() {
	iso_ready published || return 0
	local project rows bad_rows s
	for project in nxerp-db $(for s in $(iso_stacks); do printf 'nxerp-%s ' "$s"; done); do
		rows="$(docker ps --filter "label=com.docker.compose.project=$project" --format '{{.Names}} {{.Ports}}' | tr -d '\r' || true)"
		if [ -z "$rows" ]; then unverified "published-$project" "no running containers; run: docker ps"; continue; fi
		bad_rows="$(printf '%s\n' "$rows" | grep -- '->' || true)"
		if [ -z "$bad_rows" ]; then pass "published-$project-none"; else bad "published-$project" "publishes: $bad_rows"; fi
	done
	rows="$(docker ps --filter "label=com.docker.compose.project=nxerp-edge" --format '{{.Names}} {{.Ports}}' | tr -d '\r' || true)"
	if [ -z "$rows" ]; then
		unverified published-nxerp-edge "edge not running; run: deploy/scripts/stack.sh edge up"
	elif printf '%s\n' "$rows" | grep -E -- '(0\.0\.0\.0|\[::\]):[0-9]+->' >/dev/null; then
		bad published-nxerp-edge "the edge publishes on all interfaces: $rows"
	else
		pass published-nxerp-edge-loopback-only
	fi
}

# hostnames: every host in stacks.list answers /api/method/ping through the edge, and the app-to-app endpoints answer 404
audit_hostnames() {
	iso_ready hostnames || return 0
	local domain port base name prefix host body code
	domain="$(iso_env "$ISO_ENV_DIR/edge.env" NXERP_DOMAIN)"
	port="$(iso_env "$ISO_ENV_DIR/edge.env" NXERP_EDGE_PORT)"
	port="${port:-8080}"
	base="${NXERP_EDGE_URL:-http://127.0.0.1:$port}"
	if [ -z "$domain" ]; then unverified hostnames "no NXERP_DOMAIN in $ISO_ENV_DIR/edge.env"; return 0; fi
	while read -r name prefix _tier; do
		case "$name" in '' | '#'*) continue ;; *) ;; esac
		host="$prefix.$domain"
		body="$(curl -sS --max-time 20 -H "Host: $host" "$base/api/method/ping" 2>/dev/null || true)"
		case "$body" in
			*pong*) pass "hostnames-$name-ping ($host)" ;;
			*) bad "hostnames-$name-ping" "$host did not answer pong through $base" ;;
		esac
		code="$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' -H "Host: $host" "$base/api/method/nxerp.shared.feed.head" 2>/dev/null || true)"
		if [ "$code" = 404 ]; then pass "hostnames-$name-feed-hidden"; else bad "hostnames-$name-feed-hidden" "/api/method/nxerp.shared.feed.head answered $code, expected 404"; fi
	done < <(tr -d '\015' <"$ISO_ENV_DIR/stacks.list")
}

# stacks: the grants and root-env audits of the original script, once per stack in stacks.list
audit_stacks() {
	iso_ready stacks || return 0
	local s
	for s in $(iso_stacks); do
		info "stack-$s" "grants and root-env of nxerp-$s"
		NXERP_SITE="$(iso_env "$ISO_ENV_DIR/$s.env" NXERP_SITE)"
		NXERP_COMPOSE_FILE="$ISO_COMPOSE_DIR/stack.compose.yaml"
		NXERP_COMPOSE_PROJECT="nxerp-$s"
		NXERP_ENV_FILES="$ISO_ENV_DIR/$s.env"
		audit_grants
		audit_root_env
	done
}

USAGE='usage: isolation_audit.sh (grants | root-env | ports | cross-read | reach | published | hostnames | stacks | all)...'

run_one() {
	case "$1" in
		grants) audit_grants ;;
		root-env) audit_root_env ;;
		ports) audit_ports ;;
		cross-read) audit_cross_read ;;
		reach) audit_reach ;;
		published) audit_published ;;
		hostnames) audit_hostnames ;;
		stacks) audit_stacks ;;
		all) audit_grants; audit_root_env; audit_ports; audit_cross_read; audit_reach; audit_published; audit_hostnames ;;
		*) die "$USAGE" ;;
	esac
}

[ $# -ge 1 ] || die "$USAGE"
for command_name in "$@"; do run_one "$command_name"; done
exit "$fail"
