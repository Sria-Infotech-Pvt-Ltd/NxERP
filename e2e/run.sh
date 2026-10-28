#!/usr/bin/env bash
# Runs the browser suite against the dev stack, inside the bench container (it has Chromium).
#
#   e2e/run.sh                      # everything (needs e2e/site.sh create once)
#   e2e/run.sh journeys             # one file (e2e/journeys.test.mjs); "first-run" is the wizard suite
#
# Creates clearly fake users, runs the tests, ALWAYS removes the users and restores the site afterwards, then
# copies the screenshots to docs/evidence/phase3/. Passwords are generated per run, passed through the
# environment and never printed. Needs `deploy/dev/up.sh -d` running.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE/../deploy/dev" || exit 1
set -a
# shellcheck disable=SC1091
. ./.env
set +a
DC=(docker compose -p nxerp-dev -f compose.yaml)
E2E_PW=${NXERP_E2E_PASSWORD:-$(python -c 'import secrets; print(secrets.token_urlsafe(16))' 2>/dev/null || python3 -c 'import secrets; print(secrets.token_urlsafe(16))')}

inside() {
	"${DC[@]}" exec -T -e NXERP_E2E_PASSWORD="$E2E_PW" -e NXERP_ADMIN_PASSWORD="$NXERP_ADMIN_PASSWORD" bench bash -lc "$1"
}

SITE=nxerp-e2e.localhost
inside "cd ~/frappe-bench && ls -d sites/$SITE >/dev/null 2>&1" || { echo "no $SITE yet: run e2e/site.sh create first" >&2; exit 1; }
# the dev web server always answers with the default site, so the fresh site gets its own server on :8001
start_server() {
	# (pgrep -f would match the very shell running it, so probe the port instead)
	inside "cd ~/frappe-bench && (curl -s -o /dev/null http://localhost:8001/login || (setsid nohup bench --site $SITE serve --port 8001 --noreload >/tmp/e2e-serve.log 2>&1 </dev/null &)); for i in \$(seq 1 40); do curl -s -o /dev/null http://localhost:8001/login && break; sleep 2; done"
}
pkill_server() { inside "pkill -f 'bench_[h]elper.*serve --port 8001' || true" >/dev/null 2>&1; sleep 2; }
start_server
inside 'cd /tmp && [ -d node_modules/playwright-core ] || npm i --silent --no-save playwright-core@1.49.1 >/dev/null 2>&1; rm -rf /tmp/e2e-shots; mkdir -p /tmp/e2e-shots'

status=0
run() { inside "cd /workspace/e2e && node --test --test-concurrency=1 --test-timeout=1200000 $1 2>&1" | tee -a /tmp/e2e-run.log; [ "${PIPESTATUS[0]}" = 0 ] || status=1; }

# 1. the first-run flow needs the site exactly as installed: no users, no wizard done. It completes the wizard.
#    The pristine database is restored first, so this step is repeatable.
if [ -z "${1:-}" ] || [ "$1" = first-run ]; then
	"$HERE/site.sh" reset >/dev/null || { echo "could not reset the fresh site" >&2; exit 1; }
	pkill_server; start_server
	run /workspace/e2e/first-run.test.mjs
fi
# 2. fixtures, then every other suite
inside "cd /home/frappe/frappe-bench && cd sites && E2E_SITE=$SITE ../env/bin/python -W ignore -m nxerp.tests.e2e_fixtures setup 2>&1 | tail -2" || exit 1
if [ -z "${1:-}" ]; then
	for name in $(inside 'ls /workspace/e2e/*.test.mjs' | tr -d ''); do
		[ "$(basename "$name")" = first-run.test.mjs ] || run "$name"
	done
elif [ "$1" != first-run ]; then
	run "/workspace/e2e/$1.test.mjs"
fi
inside "cd /home/frappe/frappe-bench && cd sites && E2E_SITE=$SITE ../env/bin/python -W ignore -m nxerp.tests.e2e_fixtures teardown 2>&1 | tail -1"
mkdir -p ../../docs/evidence/phase3
"${DC[@]}" cp bench:/tmp/e2e-shots/. ../../docs/evidence/phase3/ >/dev/null 2>&1 || true
pkill_server
exit $status
