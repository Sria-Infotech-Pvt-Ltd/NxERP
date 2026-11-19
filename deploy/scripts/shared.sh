#!/usr/bin/env bash
# The shared read layer's stack: database, accounts, migrations, grants, views, projector and Read API (ADR-009).
#
#   deploy/scripts/shared.sh init-env            generate deploy/env/shared/shared.env (mode 600) with random passwords
#                                                (needs NXERP_IMAGE_TAG; optional NXERP_IMAGE, SHARED_DEV_SRC, SHARED_ALLOW_INSECURE_FEED)
#   deploy/scripts/shared.sh prepare             database, accounts, migrations, grants and views (no services)
#   deploy/scripts/shared.sh up                  prepare, then start the projector and the Read API
#   deploy/scripts/shared.sh down                stop everything (add --volumes to also delete the database)
#   deploy/scripts/shared.sh migrate             apply schema/*.sql with the migrate account, then refresh object grants
#   deploy/scripts/shared.sh create-accounts     create the database and the accounts (the only run that holds the root password)
#   deploy/scripts/shared.sh views               regenerate the per-consumer views from the contracts and consumer_grant
#   deploy/scripts/shared.sh grants sync|show    consumer_grant from the contracts' consumers
#   deploy/scripts/shared.sh tokens create|rotate|revoke|list --app <app>
#   deploy/scripts/shared.sh rebuild --source <app> | --all
#   deploy/scripts/shared.sh reconcile --recent | --full
#   deploy/scripts/shared.sh stop|start projector
#   deploy/scripts/shared.sh status
#   deploy/scripts/shared.sh test [unittest args]   run the shared_service tests in a one-shot container (needs SHARED_DEV_SRC)
#
# Environment: SHARED_ENV_FILE (default deploy/env/shared/shared.env), SHARED_COMPOSE_PROJECT (default nxerp-shared),
# SHARED_SYNC_NETWORK (default nxerp_sync). Passwords come from the env file, are never read from arguments and never printed.
set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash on Windows must not rewrite /home/frappe/... into C:/...

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_FILE="$ROOT/deploy/docker/compose/shared/shared.compose.yaml"
DEV_FILE="$ROOT/deploy/docker/compose/shared/shared.dev.override.yaml"
ENV_FILE="${SHARED_ENV_FILE:-$ROOT/deploy/env/shared/shared.env}"
PROJECT="${SHARED_COMPOSE_PROJECT:-nxerp-shared}"
PYTHON_IN_IMAGE=/home/frappe/frappe-bench/env/bin/python

log() { printf '[shared.sh] %s\n' "$*" >&2; }
die() { printf '[shared.sh] ERROR: %s\n' "$*" >&2; exit 1; }

# the path as docker (a Windows binary under Git Bash) wants it, with forward slashes so it is safe inside YAML values
hostpath() {
	if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

envval() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | head -n 1 || true; }

need_env() { [ -f "$ENV_FILE" ] || die "no env file at $ENV_FILE: run deploy/scripts/shared.sh init-env"; }

# absolute host paths for the files compose mounts (a relative value in the env file would resolve next to the compose file)
normalise_paths() {
	local sources secrets
	sources="${SHARED_SOURCES_FILE:-$(envval SHARED_SOURCES_FILE)}"
	secrets="${SHARED_SECRETS_DIR:-$(envval SHARED_SECRETS_DIR)}"
	case "$sources" in ""|./*) sources="$ROOT/deploy/env/shared/sources.json" ;; esac
	case "$secrets" in ""|./*) secrets="$ROOT/deploy/env/shared/secrets" ;; esac
	[ -f "$sources" ] || { log "no sources file at $sources: writing an empty one (the projector will idle)"; mkdir -p "$(dirname "$sources")"; printf '{"sources": []}\n' >"$sources"; }
	mkdir -p "$secrets"
	SHARED_SOURCES_FILE="$(hostpath "$sources")"
	SHARED_SECRETS_DIR="$(hostpath "$secrets")"
	export SHARED_SOURCES_FILE SHARED_SECRETS_DIR
}

sdc() {
	local args=(docker compose -p "$PROJECT" --env-file "$(hostpath "$ENV_FILE")" -f "$(hostpath "$COMPOSE_FILE")")
	if [ -n "$(envval SHARED_DEV_SRC)" ]; then args+=(-f "$(hostpath "$DEV_FILE")"); fi
	"${args[@]}" "$@"
}

# tool SERVICE ARGS...: one-shot run of `python -m nxerp.shared_service ARGS` in a tools service
tool() {
	local service="$1"
	shift
	sdc --profile tools run --rm -T "$service" "$PYTHON_IN_IMAGE" -m nxerp.shared_service "$@"
}

ensure_network() {
	local network="${SHARED_SYNC_NETWORK:-$(envval SHARED_SYNC_NETWORK)}"
	network="${network:-nxerp_sync}"
	docker network inspect "$network" >/dev/null 2>&1 || { log "creating the private network $network"; docker network create "$network" >/dev/null; }
}

wait_db() {
	local id status
	id="$(sdc ps -q shared-db)"
	[ -n "$id" ] || die "shared-db is not running"
	for _ in $(seq 1 60); do
		status="$(docker inspect --format '{{.State.Health.Status}}' "$id" 2>/dev/null || true)"
		[ "$status" = healthy ] && return 0
		sleep 2
	done
	die "shared-db did not become healthy"
}

cmd_init_env() {
	[ ! -e "$ENV_FILE" ] || die "$ENV_FILE exists; delete it first if you want new passwords"
	[ -n "${NXERP_IMAGE_TAG:-}" ] || die "set NXERP_IMAGE_TAG to the application image tag before running init-env"
	local py=""
	for candidate in python3 python; do
		if "$candidate" -c 'pass' >/dev/null 2>&1; then py="$candidate"; break; fi
	done
	[ -n "$py" ] || die "no working python3 or python found"
	mkdir -p "$(dirname "$ENV_FILE")"
	(
		umask 077
		ENV_OUT="$(hostpath "$ENV_FILE")" DEV_SRC="${SHARED_DEV_SRC:-}" ALLOW_INSECURE="${SHARED_ALLOW_INSECURE_FEED:-0}" "$py" - <<'PY'
import os
import secrets

lines = [
	f"NXERP_IMAGE_TAG={os.environ['NXERP_IMAGE_TAG']}",
	*([f"NXERP_IMAGE={os.environ['NXERP_IMAGE']}"] if os.environ.get("NXERP_IMAGE") else []),
	"SHARED_DB_NAME=nxerp_shared",
	f"SHARED_DB_ROOT_PASSWORD={secrets.token_urlsafe(24)}",
	f"SHARED_MIGRATE_PASSWORD={secrets.token_urlsafe(24)}",
	f"SHARED_PROJECTOR_PASSWORD={secrets.token_urlsafe(24)}",
	f"SHARED_READAPI_PASSWORD={secrets.token_urlsafe(24)}",
	"SHARED_DB_REQUIRE_SSL=0",
	"SHARED_REPORT_RO_APPS=",
	f"SHARED_ALLOW_INSECURE_FEED={os.environ['ALLOW_INSECURE']}",
	"SHARED_SYNC_NETWORK=nxerp_sync",
	f"SHARED_DEV_SRC={os.environ['DEV_SRC']}",
]
with open(os.environ["ENV_OUT"], "w", encoding="utf-8", newline="\n") as handle:
	handle.write("\n".join(lines) + "\n")
PY
	)
	chmod 600 "$ENV_FILE" 2>/dev/null || true
	# Windows ignores chmod: restrict the file to the current user as well (icacls exists only there)
	if command -v icacls >/dev/null 2>&1; then icacls "$(hostpath "$ENV_FILE" | sed "s|/|\\|g")" /inheritance:r /grant:r "${USERNAME:-$USER}:F" >/dev/null 2>&1 || true; fi
	log "wrote $ENV_FILE (mode 600). Keys: $(sed -n 's/=.*//p' "$ENV_FILE" | tr '\n' ' ')"
	log "copy the file into the password manager; its values are never printed"
}

# database, accounts, migrations, grants and views: everything except the long-running services
cmd_prepare() {
	need_env
	normalise_paths
	ensure_network
	log "starting the database"
	sdc up -d shared-db
	wait_db
	log "creating the database and accounts"
	tool shared-root-tool create-accounts
	log "applying migrations"
	tool shared-admin migrate
	log "syncing grants and generating views"
	tool shared-admin grants sync
	tool shared-admin views
}

cmd_up() {
	cmd_prepare
	log "starting the projector and the Read API"
	sdc up -d shared-projector shared-api
	cmd_status
}

cmd_down() {
	need_env
	normalise_paths
	sdc down "$@"
}

cmd_status() {
	need_env
	normalise_paths
	sdc ps
	tool shared-ops status || log "status unavailable (the accounts or migrations may not exist yet)"
}

main() {
	local command="${1:-}"
	[ -n "$command" ] || { sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
	shift
	case "$command" in
		init-env) cmd_init_env ;;
		prepare) cmd_prepare ;;
		up) cmd_up ;;
		down) cmd_down "$@" ;;
		status) cmd_status ;;
		migrate) need_env; normalise_paths; ensure_network; tool shared-admin migrate ;;
		create-accounts) need_env; normalise_paths; ensure_network; tool shared-root-tool create-accounts ;;
		views) need_env; normalise_paths; ensure_network; tool shared-admin views ;;
		grants) need_env; normalise_paths; ensure_network; tool shared-admin grants "$@" ;;
		tokens) need_env; normalise_paths; ensure_network; tool shared-admin tokens "$@" ;;
		rebuild) need_env; normalise_paths; ensure_network; tool shared-ops rebuild "$@" ;;
		reconcile) need_env; normalise_paths; ensure_network; tool shared-ops reconcile "$@" ;;
		stop) need_env; normalise_paths; sdc stop "shared-${1:?stop projector|api}" ;;
		start) need_env; normalise_paths; ensure_network; sdc start "shared-${1:?start projector|api}" ;;
		test)
			need_env
			normalise_paths
			ensure_network
			[ -n "$(envval SHARED_DEV_SRC)" ] || die "tests run the working copy: set SHARED_DEV_SRC in $ENV_FILE"
			sdc --profile tools run --rm -T shared-root-tool "$PYTHON_IN_IMAGE" -m unittest discover \
				-s /opt/nxerp-src/nxerp/shared_service/tests -t /opt/nxerp-src "$@"
			;;
		*) die "unknown command: $command" ;;
	esac
}

main "$@"
