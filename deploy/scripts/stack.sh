#!/usr/bin/env bash
# One command for the isolated stacks (Phase 5): the database tiers, the edge proxy and every app stack.
#
#   deploy/scripts/stack.sh <stack-name|db|edge> <up|down|ps|logs|create-site|bench ARGS...|health|backup>
#
# A stack name is any name listed in deploy/env/isolated/stacks.list that also has deploy/env/isolated/<name>.env.
# Adding an app needs only a new env file and one line in stacks.list (see deploy/env/isolated/app.env.example).
#
#   up           start the stack (db: both database servers; edge: regenerates the edge config first)
#   down [ARGS]  stop it; `-v` / `--volumes` (deleting data) is refused unless NXERP_ALLOW_DESTROY=1
#   ps | logs    docker compose ps / logs [ARGS]
#   create-site  create the stack's site once (the only moment a database root password is used)
#   bench ARGS   bench for the stack's site, e.g.  stack.sh hd bench list-apps
#   drop-site    remove the stack's database and login from its tier (needs NXERP_ALLOW_DESTROY=1; rehearsal and rollback only)
#   health       deploy/scripts/healthcheck.sh for the stack's site (apps expected = NXERP_EXPECT_APPS of its env file)
#   backup       deploy/scripts/backup.sh for the stack's site
#   restore ARGS deploy/scripts/restore.sh for the stack's site (--yes <backup-dir> ...; cutover.sh uses it)
#
# NXERP_PASSTHROUGH="NAME1 NAME2": environment variables forwarded BY NAME into `bench execute` (never their values on a command line).
# Secrets stay in the mode-600 env files; they are read here, never printed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ENV_DIR=deploy/env/isolated
COMPOSE_DIR=deploy/docker/compose/isolated
STACKS_LIST="$ENV_DIR/stacks.list"

fatal() { printf '[stack.sh] ERROR: %s\n' "$*" >&2; exit 1; }
usage() { sed -n "2,20p" "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

# env_value FILE KEY: the value of KEY in an env file (first match), empty when absent
env_value() { [ -f "$1" ] && sed -n "s/^$2=//p" "$1" | head -n 1 | tr -d '\r' || true; }

hostpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }

[ $# -ge 2 ] || usage
name="$1"
action="$2"
shift 2

in_stacks_list() { [ -f "$STACKS_LIST" ] && awk -v n="$1" '$1 == n && $1 !~ /^#/ {found = 1} END {exit !found}' "$STACKS_LIST"; }
tier_of() { tr -d '\015' <"$STACKS_LIST" | awk -v n="$1" '$1 == n && $1 !~ /^#/ {print $3}'; }

case "$name" in
	db)
		compose_files=("$COMPOSE_DIR/db.compose.yaml")
		env_file="$ENV_DIR/db.env"
		project=nxerp-db
		;;
	edge)
		compose_files=("$COMPOSE_DIR/edge.compose.yaml" "$COMPOSE_DIR/edge/generated/edge.networks.override.yaml")
		env_file="$ENV_DIR/edge.env"
		project=nxerp-edge
		;;
	*)
		in_stacks_list "$name" || fatal "'$name' is not listed in $STACKS_LIST (copy $STACKS_LIST.example and add a line)"
		compose_files=("$COMPOSE_DIR/stack.compose.yaml")
		env_file="$ENV_DIR/$name.env"
		project="nxerp-$name"
		;;
esac
[ -f "$env_file" ] || fatal "no env file $env_file: cp $env_file.example $env_file, chmod 600, fill in the CHANGE_ME values"

compose() {
	local args=(docker compose -p "$project" --env-file "$(hostpath "$env_file")") f
	for f in "${compose_files[@]}"; do args+=(-f "$f"); done
	"${args[@]}" "$@"
}

# the database administrator password of this stack's tier, from db.env: exported only for the commands that need it
tier_root_password() {
	local tier key value
	tier="$(tier_of "$name")"
	case "$tier" in
		standard) key=NXERP_DB_ROOT_PASSWORD_STANDARD ;;
		restricted) key=NXERP_DB_ROOT_PASSWORD_RESTRICTED ;;
		*) fatal "stacks.list gives '$name' the tier '$tier': expected standard or restricted" ;;
	esac
	value="$(env_value "$ENV_DIR/db.env" "$key")"
	[ -n "$value" ] || fatal "$key is empty or $ENV_DIR/db.env is missing"
	NXERP_DB_ROOT_PASSWORD="$value"
	export NXERP_DB_ROOT_PASSWORD
}

# the variables deploy/scripts/*.sh read (see deploy/scripts/lib.sh), set from this stack's env file
use_lib() {
	NXERP_SITE="$(env_value "$env_file" NXERP_SITE)"
	[ -n "$NXERP_SITE" ] || fatal "NXERP_SITE is empty in $env_file"
	NXERP_COMPOSE_FILE="${compose_files[0]}"
	NXERP_COMPOSE_PROJECT="$project"
	NXERP_ENV_FILES="$env_file"
	NXERP_SERVICE=backend
	NXERP_EXPECT_APPS="$(env_value "$env_file" NXERP_EXPECT_APPS)"
	[ -n "$NXERP_EXPECT_APPS" ] || fatal "NXERP_EXPECT_APPS is empty in $env_file"
	export NXERP_SITE NXERP_COMPOSE_FILE NXERP_COMPOSE_PROJECT NXERP_ENV_FILES NXERP_SERVICE NXERP_EXPECT_APPS
}

is_stack=1
case "$name" in db | edge) is_stack=0 ;; *) ;; esac

case "$action" in
	up)
		if [ "$name" = edge ]; then deploy/scripts/edge-gen.sh; fi
		compose up -d "$@"
		;;
	down)
		for arg in "$@"; do
			case "$arg" in
				-v | --volumes)
					[ "${NXERP_ALLOW_DESTROY:-0}" = 1 ] || fatal "refusing '$arg': it deletes data. Rehearsal only: NXERP_ALLOW_DESTROY=1 $0 $name down $arg"
					;;
				*) ;;
			esac
		done
		compose down "$@"
		;;
	ps) compose ps "$@" ;;
	logs) compose logs "$@" ;;
	create-site)
		[ "$is_stack" = 1 ] || fatal "create-site is for app stacks, not $name"
		tier_root_password
		if ! compose --profile init run --rm create-site; then
			printf '[stack.sh] create-site failed; the script removed what it had created.\n' >&2
			printf '[stack.sh] check that the database tier is up and healthy:  %s db ps\n' "$0" >&2
			printf '[stack.sh] and that the networks exist:  docker network ls | grep nxerp   (docker network create nxerp-api)\n' >&2
			printf '[stack.sh] then repeat:  %s %s create-site\n' "$0" "$name" >&2
			exit 1
		fi
		;;
	bench)
		[ "$is_stack" = 1 ] || fatal "bench is for app stacks, not $name"
		[ $# -ge 1 ] || fatal "usage: $0 $name bench ARGS..."
		# shellcheck source=deploy/scripts/lib.sh
		use_lib
		. deploy/scripts/lib.sh
		bench_site "$@"
		;;
	drop-site)
		# removes the stack's database and its login from the tier (`down -v` removes only the stack's own volumes). Rehearsal and rollback only.
		[ "$is_stack" = 1 ] || fatal "drop-site is for app stacks, not $name"
		[ "${NXERP_ALLOW_DESTROY:-0}" = 1 ] || fatal "refusing: drop-site deletes the stack's database. Rehearsal only: NXERP_ALLOW_DESTROY=1 $0 $name drop-site"
		use_lib
		tier_root_password
		db_host="$(env_value "$env_file" NXERP_DB_HOST)"
		db_scope="$(env_value "$env_file" NXERP_DB_USER_SCOPE)"
		# shellcheck source=deploy/scripts/lib.sh
		. deploy/scripts/lib.sh
		inbench "db_login=\$(env/bin/python -c \"import json,sys; print(json.load(open(sys.argv[1])).get('db_name',''))\" sites/$NXERP_SITE/site_config.json) && bench drop-site $NXERP_SITE --no-backup --force --mariadb-root-password \"\$NXERP_DB_ROOT_PASSWORD\" && MYSQL_PWD=\"\$NXERP_DB_ROOT_PASSWORD\" mariadb -h $db_host -uroot -e \"DROP USER IF EXISTS '\$db_login'@'$db_scope'\""
		;;
	health)
		[ "$is_stack" = 1 ] || fatal "health is for app stacks, not $name"
		use_lib
		exec deploy/scripts/healthcheck.sh
		;;
	backup)
		[ "$is_stack" = 1 ] || fatal "backup is for app stacks, not $name"
		use_lib
		tier_root_password
		exec deploy/scripts/backup.sh
		;;
	restore)
		[ "$is_stack" = 1 ] || fatal "restore is for app stacks, not $name"
		use_lib
		tier_root_password
		exec deploy/scripts/restore.sh "$@"
		;;
	*) usage ;;
esac
