#!/usr/bin/env bash
# Container entrypoint: writes sites/common_site_config.json from NON-SECRET environment variables, then runs the command.
# Secrets (database root password, admin password) are never written here: they are only used by `bench new-site`.
#
#   NXERP_DB_HOST (default mariadb)  NXERP_DB_PORT (3306)  NXERP_REDIS_CACHE  NXERP_REDIS_QUEUE
#   NXERP_REDIS_SOCKETIO (defaults to NXERP_REDIS_QUEUE)  NXERP_SOCKETIO_PORT (9000)  NXERP_CONFIGURE=0 to skip
#   NXERP_WEBSERVER_HOST (backend)  NXERP_WEBSERVER_PORT (8000): where the websocket service authenticates sockets
set -euo pipefail
cd /home/frappe/frappe-bench
if [ "${NXERP_CONFIGURE:-1}" = 1 ] && [ -n "${NXERP_REDIS_CACHE:-}" ] && [ -n "${NXERP_REDIS_QUEUE:-}" ]; then
	# a sites volume keeps the generated files of the image that created it: refresh them from this image
	# (site folders, uploads and common_site_config.json are not touched)
	for entry in /home/frappe/image-sites/* /home/frappe/image-sites/.[!.]*; do
		name=$(basename "$entry")
		[ -e "$entry" ] && [ "$name" != common_site_config.json ] || continue
		rm -rf "sites/$name"
		cp -a "$entry" "sites/$name"
	done
	# Frappe serves the asset map from the shared redis key assets_json; `bench build` refreshes it, but the image is
	# built without redis, so a cached map would still name the previous image's bundles (404 on every page)
	env/bin/python -I -c 'import redis, sys; redis.Redis.from_url(sys.argv[1]).delete("assets_json")' "$NXERP_REDIS_CACHE"
	bench set-config -g db_host "${NXERP_DB_HOST:-mariadb}"
	bench set-config -g -p db_port "${NXERP_DB_PORT:-3306}"
	bench set-config -g redis_cache "$NXERP_REDIS_CACHE"
	bench set-config -g redis_queue "$NXERP_REDIS_QUEUE"
	bench set-config -g redis_socketio "${NXERP_REDIS_SOCKETIO:-$NXERP_REDIS_QUEUE}"
	bench set-config -g -p socketio_port "${NXERP_SOCKETIO_PORT:-9000}"
	# without these the websocket service calls back to the browser's Origin, unreachable from inside the container
	bench set-config -g webserver_host "${NXERP_WEBSERVER_HOST:-backend}"
	bench set-config -g -p webserver_port "${NXERP_WEBSERVER_PORT:-8000}"
fi
exec "$@"
