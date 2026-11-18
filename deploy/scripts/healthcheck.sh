#!/usr/bin/env bash
# Is the site up and sane? Exit 0 only when every check passes.
#
#   deploy/scripts/healthcheck.sh
#
#   NXERP_BASE_URL       probe over HTTP from this host (e.g. https://staging.example.test); default: probe from inside the
#                        bench service against http://localhost:$NXERP_HTTP_PORT with the Host header set to the site
#   NXERP_HTTP_PORT      port inside the service (default 8000; the dev stack serves on 8000 too)
#   NXERP_EXPECT_APPS    apps that must be installed on the site (default "frappe erpnext helpdesk nxerp")
#   NXERP_REQUIRE_SCHEDULER  1 (default): a disabled scheduler fails the check; 0 only warns (a dev site has it disabled)
#   NXERP_HEALTH_RETRIES retries for the first (ping) check, 5 s apart (default 24, i.e. 2 minutes)
#
# Checks: (1) /api/method/ping answers "pong" (a site in maintenance mode answers 503, so this also proves maintenance is off),
# (2) /login answers 200, (3) every expected app is installed on the site, (4) the scheduler is not disabled.
set -euo pipefail
# shellcheck source=deploy/scripts/lib.sh
. "$(dirname "$0")/lib.sh"

port=${NXERP_HTTP_PORT:-8000}
expect=${NXERP_EXPECT_APPS:-frappe erpnext helpdesk nxerp}
retries=${NXERP_HEALTH_RETRIES:-24}
fail=0

# http_get PATH -> prints the response body, then a final line with the HTTP status (000 when unreachable)
http_get() {
	if [ -n "${NXERP_BASE_URL:-}" ]; then
		curl -sS --max-time 20 -o - -w '\n%{http_code}' "$NXERP_BASE_URL$1" 2>/dev/null || printf '\n000'
	else
		inbench "curl -sS --max-time 20 -o - -w '\n%{http_code}' -H 'Host: $NXERP_SITE' http://localhost:$port$1 2>/dev/null || printf '\n000'"
	fi
}
status_of() { printf '%s' "$1" | tail -n 1 | tr -d '\r'; }

pong=
for i in $(seq 1 "$retries"); do
	out=$(http_get /api/method/ping || true)
	if [ "$(status_of "$out")" = 200 ] && printf '%s' "$out" | grep -q '"pong"'; then pong=1; break; fi
	log "ping not ready (attempt $i/$retries, status $(status_of "$out"))"
	[ "$i" = "$retries" ] || sleep 5
done
if [ -n "$pong" ]; then log "OK   ping answers pong"; else log "FAIL ping"; fail=1; fi

out=$(http_get /login || true)
if [ "$(status_of "$out")" = 200 ]; then log "OK   /login 200"; else log "FAIL /login status $(status_of "$out")"; fail=1; fi

apps=$(bench_site list-apps 2>/dev/null | awk 'NF {print $1}' | tr '\n' ' ' || true)
for app in $expect; do
	case " $apps " in
		*" $app "*) log "OK   app installed: $app" ;;
		*) log "FAIL app not installed on $NXERP_SITE: $app (found: ${apps:-none})"; fail=1 ;;
	esac
done

sched=$(bench_site scheduler status 2>&1 || true)
case "$sched" in
	*isabled*)
		if [ "${NXERP_REQUIRE_SCHEDULER:-1}" = 1 ]; then log "FAIL scheduler: $sched"; fail=1; else log "WARN scheduler: $sched (NXERP_REQUIRE_SCHEDULER=0)"; fi ;;
	*) log "OK   scheduler: ${sched:-no status output}" ;;
esac

[ "$fail" = 0 ] && log "healthy: $NXERP_SITE" || log "UNHEALTHY: $NXERP_SITE"
exit "$fail"
