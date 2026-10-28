# shellcheck shell=bash
# Shared helpers for deploy/scripts/*.sh. Source it; do not run it.
#
# Every script is parameterised by environment variables, so the same script drives the staging-like compose stack,
# a real staging/production host (run it there, or over ssh) and, for tests, the dev stack:
#
#   NXERP_SITE              site name (default nxerp.localhost)
#   NXERP_COMPOSE_FILE      compose file (default deploy/staging-like/compose.yaml)
#   NXERP_COMPOSE_PROJECT   compose project name (-p), optional
#   NXERP_ENV_FILES         space-separated --env-file list, optional
#   NXERP_SERVICE           service that has bench (default backend; the dev stack uses "bench")
#   NXERP_BENCH_DIR         bench path inside that service (default /home/frappe/frappe-bench)
#   NXERP_BACKUP_DIR        host directory that receives backups (default ./backups; git-ignored)
#
# Secrets (NXERP_DB_ROOT_PASSWORD) are read from the environment, never from arguments, and never printed.

export MSYS_NO_PATHCONV=1 # Git Bash on Windows must not rewrite /home/frappe/... into C:/...

NXERP_SITE=${NXERP_SITE:-nxerp.localhost}
NXERP_COMPOSE_FILE=${NXERP_COMPOSE_FILE:-deploy/staging-like/compose.yaml}
NXERP_COMPOSE_PROJECT=${NXERP_COMPOSE_PROJECT:-}
NXERP_ENV_FILES=${NXERP_ENV_FILES:-}
NXERP_SERVICE=${NXERP_SERVICE:-backend}
NXERP_BENCH_DIR=${NXERP_BENCH_DIR:-/home/frappe/frappe-bench}
NXERP_BACKUP_DIR=${NXERP_BACKUP_DIR:-./backups}

# The database root password may come from an env file (the host's .env); a value already in the environment wins.
if [ -z "${NXERP_DB_ROOT_PASSWORD:-}" ]; then
	for _env_file in $NXERP_ENV_FILES; do
		[ -f "$_env_file" ] || continue
		_value=$(sed -n 's/^NXERP_DB_ROOT_PASSWORD=//p' "$_env_file" | head -n 1)
		[ -z "$_value" ] || NXERP_DB_ROOT_PASSWORD=$_value
	done
	[ -z "${NXERP_DB_ROOT_PASSWORD:-}" ] || export NXERP_DB_ROOT_PASSWORD
fi

log() { printf '[%s] %s\n' "$(basename "$0")" "$*" >&2; }
die() { printf '[%s] ERROR: %s\n' "$(basename "$0")" "$*" >&2; exit 1; }

# hostpath PATH: the path as the docker CLI wants it (Git Bash on Windows hands docker.exe /c/... paths it cannot read)
hostpath() {
	if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi
}

# dc ARGS... : docker compose with the configured project, env files and compose file
dc() {
	local args=(docker compose) f
	[ -z "$NXERP_COMPOSE_PROJECT" ] || args+=(-p "$NXERP_COMPOSE_PROJECT")
	for f in $NXERP_ENV_FILES; do args+=(--env-file "$f"); done
	args+=(-f "$NXERP_COMPOSE_FILE")
	"${args[@]}" "$@"
}

# inbench 'COMMAND' : run a shell command inside the bench service, in the bench directory.
# NXERP_DB_ROOT_PASSWORD is forwarded by name (not value) so it never appears in a host process list.
inbench() {
	dc exec -T -e NXERP_DB_ROOT_PASSWORD "$NXERP_SERVICE" bash -lc "cd $NXERP_BENCH_DIR && $1"
}

# bench ARGS... : bench for the configured site
bench_site() {
	inbench "bench --site $NXERP_SITE $*"
}
