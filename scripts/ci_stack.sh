#!/usr/bin/env bash
# CI helper around the dev stack (deploy/dev). Used by .github/workflows/ci.yml and .github/actions/stack-up; also runnable
# locally. It never prints the generated passwords.
#
#   scripts/ci_stack.sh up                bring the stack up (deploy/dev/up.sh -d) and wait for "[bootstrap] ready:"
#   scripts/ci_stack.sh prep              allow tests on the dev site and lift Frappe's per-hour new-user throttle
#   scripts/ci_stack.sh bench ARGS...     bench --site <site> ARGS... inside the container
#   scripts/ci_stack.sh sh 'COMMAND'      a shell command inside the container, in the bench directory
#   scripts/ci_stack.sh down              stop the stack (volumes kept)
#   scripts/ci_stack.sh logs              last 300 lines of the bench service
#   scripts/ci_stack.sh volumes save|restore DIR   tar the three data volumes (and deploy/dev/.env) to/from DIR (CI cache; stack must be down)
#
# NXERP_CI_READY_TIMEOUT: seconds to wait for readiness (default 3600; a cold bootstrap measured 408 s on a workstation).
set -euo pipefail

root=${NXERP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
project=nxerp-dev
site=${NXERP_SITE:-nxerp.localhost}
dc() { docker compose -p "$project" -f "$root/deploy/dev/compose.yaml" --env-file "$root/deploy/versions.env" --env-file "$root/deploy/dev/.env" "$@"; }
inside() { dc exec -T -e NXERP_ADMIN_PASSWORD -e NXERP_DB_ROOT_PASSWORD -e NXERP_MATRIX_OUT bench bash -lc "cd frappe-bench && $1"; }

load_env() {
	set -a
	# shellcheck disable=SC1091
	. "$root/deploy/dev/.env"
	set +a
}

wait_ready() {
	local limit=${NXERP_CI_READY_TIMEOUT:-3600} waited=0
	while [ "$waited" -lt "$limit" ]; do
		if dc logs bench 2>&1 | grep -q '\[bootstrap\] ready:'; then echo "bootstrap finished after ${waited}s"; return 0; fi
		if [ "$(docker inspect -f '{{.State.Running}}' "$project-bench-1" 2>/dev/null)" != true ]; then
			echo "bench container stopped before it was ready" >&2
			dc logs --tail 200 bench >&2
			return 1
		fi
		sleep 15
		waited=$((waited + 15))
	done
	echo "timed out after ${limit}s waiting for bootstrap" >&2
	dc logs --tail 200 bench >&2
	return 1
}

case "${1:-}" in
up)
	(cd "$root" && ./deploy/dev/up.sh -d)
	wait_ready
	;;
prep)
	load_env
	# Frappe refuses more than `throttle_user_limit` (default 60) new users per hour; the tests create more.
	# Stored as a number (-p), not a string.
	inside "bench --site $site set-config -p throttle_user_limit 100000 && bench --site $site set-config allow_tests true"
	;;
bench)
	shift
	load_env
	inside "bench --site $site $*"
	;;
sh)
	load_env
	inside "$2"
	;;
down)
	(cd "$root" && ./deploy/dev/up.sh down)
	;;
logs)
	dc logs --tail 300 bench
	;;
volumes)
	action=${2:?save|restore}
	dir=$(mkdir -p "${3:?directory}" && cd "$3" && pwd)
	# The volumes hold a site installed with the passwords of deploy/dev/.env, so that file travels with them. It belongs to a
	# throwaway CI stack (random values, used nowhere else), but anyone who can read the repository's caches can read it.
	if [ "$action" = save ]; then
		install -m 600 "$root/deploy/dev/.env" "$dir/dev.env"
	elif [ -f "$dir/dev.env" ]; then
		install -m 600 "$dir/dev.env" "$root/deploy/dev/.env"
	fi
	for vol in mariadb-data bench-data vendor-data; do
		if [ "$action" = save ]; then
			docker run --rm -v "${project}_$vol:/d:ro" -v "$dir:/c" alpine:3.20 sh -c "tar -C /d -cpf - . | gzip -1 > /c/$vol.tar.gz"
		else
			# labels make Docker Compose adopt the volume without a "not created by compose" warning
			docker volume create --label "com.docker.compose.project=$project" --label "com.docker.compose.volume=$vol" "${project}_$vol" >/dev/null
			docker run --rm -v "${project}_$vol:/d" -v "$dir:/c:ro" alpine:3.20 sh -c "tar -C /d -xpzf /c/$vol.tar.gz"
		fi
		echo "$action: $vol"
	done
	;;
*)
	sed -n '2,15p' "${BASH_SOURCE[0]}" >&2
	exit 2
	;;
esac
