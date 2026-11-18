#!/usr/bin/env bash
# Black-box smoke test of a deployed site over HTTP. Needs only curl and a URL; no credentials, no data written.
#
#   NXERP_BASE_URL=https://staging.example.test deploy/scripts/smoke.sh
#
# What it asserts (each line was checked against the running dev site on 2026-10-28, see docs/runbooks/deploy.md):
#   - /api/method/ping answers pong
#   - /login renders the login form
#   - protected routes do NOT serve content to an anonymous visitor: /nxerp/apps, /nxerp/go and /helpdesk redirect to
#     /login; /api/resource/User answers 401 or 403
# Exit 0 only when all pass. It is a gate, not a replacement for the browser suite (apps/nxerp_platform/browser-tests/).
set -euo pipefail

base=${NXERP_BASE_URL:?set NXERP_BASE_URL, e.g. https://staging.example.test}
base=${base%/}
fail=0

pass() { printf 'OK   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1" >&2; fail=1; }

status() { curl -sS -o /dev/null --max-time 30 -w '%{http_code}' "$base$1" 2>/dev/null || echo 000; }
location() { curl -sS -o /dev/null --max-time 30 -w '%{redirect_url}' "$base$1" 2>/dev/null || true; }

body=$(curl -sS --max-time 30 "$base/api/method/ping" 2>/dev/null || true)
case "$body" in *'"pong"'*) pass "ping answers pong" ;; *) bad "ping did not answer pong: ${body:0:80}" ;; esac

code=$(status /login)
[ "$code" = 200 ] && pass "/login 200" || bad "/login status $code"
curl -sS --max-time 30 "$base/login" 2>/dev/null | grep -q 'id="login_email"' && pass "/login has the sign-in form" || bad "/login has no #login_email field"

for path in /nxerp/apps /nxerp/go /helpdesk /desk; do
	code=$(status "$path")
	loc=$(location "$path")
	case "$code:$loc" in
		30[1278]:*/login*) pass "$path anonymous -> login ($code)" ;;
		*) bad "$path anonymous: status $code, redirect '${loc:-none}' (expected a redirect to /login)" ;;
	esac
done

code=$(status /api/resource/User)
case "$code" in 401|403) pass "/api/resource/User anonymous refused ($code)" ;; *) bad "/api/resource/User anonymous status $code (expected 401/403)" ;; esac

[ "$fail" = 0 ] && echo "smoke passed: $base" || { echo "smoke FAILED: $base" >&2; exit 1; }
