#!/usr/bin/env bash
# Runs INSIDE the bench container (see deploy/docker/compose/dev/compose.yaml). Idempotent: on an existing
# bench it skips straight to `bench start`.
#
# Builds: frappe (pinned in deploy/versions.env) + the apps in deploy/apps.json, in order,
# on one site. Every app is fetched at its pinned commit and verified; a drifted pin fails
# the bootstrap on purpose.
set -euo pipefail

BENCH_DIR=/home/frappe/frappe-bench
VENDOR=/home/frappe/vendor
WORKSPACE=/workspace
APPS_JSON=$WORKSPACE/deploy/apps.json
SITE=${NXERP_SITE:-nxerp.localhost}
export PATH="$HOME/.local/bin:$PATH"

log() { printf '\n[bootstrap] %s\n' "$*"; }
die() { printf '\n[bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }

# named volumes are created root-owned
sudo chown frappe:frappe "$BENCH_DIR" "$VENDOR"
git config --global --add safe.directory '*'
printf '[client]\nskip-ssl\n' > ~/.my.cnf

# fetch_pinned NAME URL BRANCH COMMIT -> $VENDOR/NAME checked out detached at COMMIT (or BRANCH tip)
fetch_pinned() {
	local name=$1 url=$2 branch=$3 commit=${4:-} dir=$VENDOR/$1
	if [ ! -d "$dir/.git" ]; then
		git init -q "$dir"
		git -C "$dir" remote add origin "$url"
	fi
	git -C "$dir" fetch -q --depth 1 origin "${commit:-$branch}"
	git -C "$dir" checkout -q --detach FETCH_HEAD
	if [ -n "$commit" ] && [ "$(git -C "$dir" rev-parse HEAD)" != "$commit" ]; then
		die "$name resolved to $(git -C "$dir" rev-parse HEAD), expected pinned $commit"
	fi
	log "$name @ $(git -C "$dir" rev-parse --short=10 HEAD)"
}

# fetch_local NAME PATH REF -> $VENDOR/NAME at REF taken from a local checkout (dev only)
fetch_local() {
	local name=$1 src=$2 ref=$3 dir=$VENDOR/$1
	if [ ! -d "$dir/.git" ]; then
		git init -q "$dir"
	fi
	# --update-shallow: the source checkout may itself be a shallow clone (CI fetches the pin at depth 1)
	git -C "$dir" fetch -q --update-shallow "$src" "$ref"
	git -C "$dir" checkout -q --detach FETCH_HEAD
	log "$name @ $(git -C "$dir" rev-parse --short=10 HEAD) (local $src $ref)"
}

# name|url|branch|commit, in install order
mapfile -t APPS < <(python3 -I - "$APPS_JSON" <<'PY'
import json, sys
for app in json.load(open(sys.argv[1])):
    print("|".join([app["name"], app["url"], app["branch"], app.get("commit", "")]))
PY
)

cd /home/frappe

if [ ! -d "$BENCH_DIR/apps/frappe" ]; then
	log "bench init: frappe $FRAPPE_REF"
	bench init --ignore-exist --frappe-path "$FRAPPE_REPO" --frappe-branch "$FRAPPE_REF" \
		--no-procfile --no-backups --skip-redis-config-generation --skip-assets --verbose "$BENCH_DIR"
	[ "$(git -C "$BENCH_DIR/apps/frappe" rev-parse HEAD)" = "$FRAPPE_COMMIT" ] \
		|| die "frappe $FRAPPE_REF resolved to $(git -C "$BENCH_DIR/apps/frappe" rev-parse HEAD), expected $FRAPPE_COMMIT"

	cd "$BENCH_DIR"
	bench set-config -g db_host mariadb
	bench set-config -g redis_cache redis://redis-cache:6379
	bench set-config -g redis_queue redis://redis-queue:6379
	bench set-config -g redis_socketio redis://redis-queue:6379
	bench set-config -g socketio_port 9000

	for row in "${APPS[@]}"; do
		IFS='|' read -r name url branch commit <<<"$row"
		if [ "$name" = nxerp ] && [ -n "${NXERP_SRC:-}" ]; then
			# dev: live checkout, edits apply without a rebuild
			log "get-app $name (soft link to $NXERP_SRC)"
			bench get-app --soft-link --skip-assets "$NXERP_SRC"
		elif [ "$name" = helpdesk ] && [ -n "${HELPDESK_REF:-}" ] && [ -d /helpdesk-src/.git ]; then
			fetch_local helpdesk /helpdesk-src "$HELPDESK_REF"
			log "get-app helpdesk (clone of $VENDOR/helpdesk)"
			bench get-app --skip-assets "$VENDOR/helpdesk"
		else
			# Pinned apps are real clones inside apps/: some build configs (e.g. erpnext's
			# banking/vite.config.ts) resolve ../../sites relative to the app's real path,
			# which a soft link to another directory breaks.
			fetch_pinned "$name" "$url" "$branch" "$commit"
			log "get-app $name (clone of $VENDOR/$name)"
			bench get-app --skip-assets "$VENDOR/$name"
		fi
	done

	log "bench build"
	bench build
	# test-only packages (e.g. freezegun, which Helpdesk's tests import)
	bench setup requirements --dev
fi

cd "$BENCH_DIR"

if [ ! -f Procfile ]; then
	# the dev stack uses the compose redis services and no file watcher
	bench setup procfile
	sed -i '/^redis_/d;/^watch:/d' Procfile
fi

if [ ! -d "sites/$SITE" ]; then
	log "new-site $SITE"
	bench new-site "$SITE" --mariadb-root-password "$NXERP_DB_ROOT_PASSWORD" \
		--admin-password "$NXERP_ADMIN_PASSWORD" --no-mariadb-socket
	for row in "${APPS[@]}"; do
		IFS='|' read -r name _ <<<"$row"
		log "install-app $name"
		bench --site "$SITE" install-app "$name"
	done
	bench --site "$SITE" set-config developer_mode 1
	bench --site "$SITE" set-config mute_emails 1
	bench --site "$SITE" set-config host_name "http://$SITE:8100"
	bench --site "$SITE" clear-cache
fi

bench use "$SITE"
log "ready: http://$SITE:8100  (apps: $(bench --site "$SITE" list-apps | tr '\n' ' '))"
exec bench start
