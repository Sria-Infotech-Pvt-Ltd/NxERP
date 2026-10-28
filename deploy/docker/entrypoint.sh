#!/usr/bin/env bash
# Container entrypoint: writes sites/common_site_config.json from NON-SECRET environment variables, then runs the command.
# Secrets (database root password, admin password) are never written here: they are only used by `bench new-site`.
#
#   NXERP_DB_HOST (default mariadb)  NXERP_DB_PORT (3306)  NXERP_REDIS_CACHE  NXERP_REDIS_QUEUE
#   NXERP_REDIS_SOCKETIO (defaults to NXERP_REDIS_QUEUE)  NXERP_SOCKETIO_PORT (9000)  NXERP_CONFIGURE=0 to skip
set -euo pipefail
cd /home/frappe/frappe-bench
if [ "${NXERP_CONFIGURE:-1}" = 1 ] && [ -n "${NXERP_REDIS_CACHE:-}" ] && [ -n "${NXERP_REDIS_QUEUE:-}" ]; then
	bench set-config -g db_host "${NXERP_DB_HOST:-mariadb}"
	bench set-config -g -p db_port "${NXERP_DB_PORT:-3306}"
	bench set-config -g redis_cache "$NXERP_REDIS_CACHE"
	bench set-config -g redis_queue "$NXERP_REDIS_QUEUE"
	bench set-config -g redis_socketio "${NXERP_REDIS_SOCKETIO:-$NXERP_REDIS_QUEUE}"
	bench set-config -g -p socketio_port "${NXERP_SOCKETIO_PORT:-9000}"
fi
exec "$@"
