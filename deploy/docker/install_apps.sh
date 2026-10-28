#!/usr/bin/env bash
# Runs INSIDE the image build (see deploy/docker/Dockerfile).
#   install_apps.sh pinned     bench init + every third-party app in apps.json (those with a url), each at its exact pinned commit
#   install_apps.sh platform   the apps of this repository (those with a path, in apps.json order: helpdesk, then nxerp) from
#                              /tmp/build/src/<name>, then the one asset build
# A pin that resolves to a different commit fails the build on purpose (same rule as deploy/bootstrap/bootstrap.sh).
# FRAPPE_REPO, FRAPPE_REF and FRAPPE_COMMIT come from the image ENV (set from deploy/versions.env by build.sh).
set -euo pipefail

BENCH_DIR=/home/frappe/frappe-bench
BUILD=/tmp/build
export PATH="$HOME/.local/bin:$PATH"
log() { printf '\n[image] %s\n' "$*"; }
die() { printf '\n[image] ERROR: %s\n' "$*" >&2; exit 1; }

# fetch_pinned NAME URL COMMIT -> $BUILD/vendor/NAME at exactly COMMIT
fetch_pinned() {
	local name=$1 url=$2 commit=$3 dir=$BUILD/vendor/$1 auth=()
	[ -n "$commit" ] || die "$name has no commit pin"
	if [ -s /run/secrets/git_token ] && case "$url" in */Sriainfotech/*|*/Sria-Infotech-Pvt-Ltd/*) true ;; *) false ;; esac; then
		# the token lives only in this process's git config for one fetch; it never reaches an image layer
		auth=(-c "http.extraheader=AUTHORIZATION: basic $(printf 'x-access-token:%s' "$(cat /run/secrets/git_token)" | base64 -w0)")
	fi
	git init -q "$dir"
	git -C "$dir" remote add origin "$url"
	git -C "$dir" "${auth[@]}" fetch -q --depth 1 origin "$commit"
	git -C "$dir" checkout -q --detach FETCH_HEAD
	[ "$(git -C "$dir" rev-parse HEAD)" = "$commit" ] || die "$name resolved to $(git -C "$dir" rev-parse HEAD), expected pinned $commit"
	log "$name @ $(git -C "$dir" rev-parse --short=10 HEAD)"
}

case "${1:-}" in
pinned)
	git config --global --add safe.directory '*'
	cd /home/frappe
	log "bench init: frappe $FRAPPE_REF"
	bench init --ignore-exist --frappe-path "$FRAPPE_REPO" --frappe-branch "$FRAPPE_REF" \
		--no-procfile --no-backups --skip-redis-config-generation --skip-assets "$BENCH_DIR"
	[ "$(git -C "$BENCH_DIR/apps/frappe" rev-parse HEAD)" = "$FRAPPE_COMMIT" ] \
		|| die "frappe $FRAPPE_REF resolved to $(git -C "$BENCH_DIR/apps/frappe" rev-parse HEAD), expected $FRAPPE_COMMIT"
	cd "$BENCH_DIR"
	# name|url|commit, in install order; the apps of this repository (with a path) are installed in the next stage
	mapfile -t APPS < <(python3 -I - "$BUILD/apps.json" <<'PY'
import json, sys
for app in json.load(open(sys.argv[1])):
    if not app.get("path"):
        print("|".join([app["name"], app["url"], app.get("commit", "")]))
PY
)
	for row in "${APPS[@]}"; do
		IFS='|' read -r name url commit <<<"$row"
		fetch_pinned "$name" "$url" "$commit"
		bench get-app --skip-assets "$BUILD/vendor/$name"
	done
	;;
platform)
	git config --global --add safe.directory '*'
	mapfile -t LOCAL < <(python3 -I - "$BUILD/apps.json" <<'PY'
import json, sys
for app in json.load(open(sys.argv[1])):
    if app.get("path"):
        print(app["name"])
PY
)
	for name in "${LOCAL[@]}"; do
		# bench get-app needs a git repository; the build context carries none (see .dockerignore)
		cd "$BUILD/src/$name"
		git init -q
		git add -A
		git -c user.name=build -c user.email=build@example.test commit -q -m "$name ${NXERP_REVISION:-unknown}"
		cd "$BENCH_DIR"
		bench get-app --skip-assets "$BUILD/src/$name"
	done
	log "bench build"
	bench build
	# the order of installed apps is the order of sites/apps.txt; nxerp must be last (ADR-005)
	[ "$(tail -n 1 sites/apps.txt)" = nxerp ] || die "nxerp is not the last app in sites/apps.txt"
	;;
*)
	die "usage: $0 pinned|platform"
	;;
esac
