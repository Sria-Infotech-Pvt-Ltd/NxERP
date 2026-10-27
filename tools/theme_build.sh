#!/usr/bin/env bash
# Regenerate the palette outputs with the real frappe-ui (installed in the dev container) and copy
# them back into both checkouts. The host needs no node_modules.
#
#   ./tools/theme_build.sh
#
# Reads the token source from ../helpdesk/desk/src/theme and writes:
#   ../helpdesk/desk/src/theme/generated/*   and   ../helpdesk/helpdesk/theme_tokens.py
#   ../helpdesk/helpdesk/public/nxerp_login/css/nxerp-theme.css
#   ./nxerp/public/css/nxerp-theme.css, nxerp-desk-theme.css   (served by the platform app)
set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash must not rewrite the container paths below

# docker.exe needs Windows-style host paths under Git Bash
winpath() { if command -v cygpath >/dev/null; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
hd="$(cd "$here/../helpdesk" && pwd)"
c=nxerp-dev-bench-1
app=/home/frappe/frappe-bench/apps/helpdesk

# the container's Helpdesk is a clone; overlay the working-tree theme sources
docker cp "$(winpath "$hd")/desk/src/theme/." "$c:$app/desk/src/theme"
docker exec -u root "$c" chown -R frappe:frappe "$app/desk/src/theme"
docker exec "$c" bash -lc "mkdir -p /tmp/nxerp-css && cd $app/desk && NXERP_PUBLIC=/tmp/nxerp-css yarn -s theme:build"

# copy the results back to the working trees
docker cp "$c:$app/desk/src/theme/generated/." "$(winpath "$hd")/desk/src/theme/generated"
docker cp "$c:$app/helpdesk/theme_tokens.py" "$(winpath "$hd")/helpdesk/theme_tokens.py"
docker cp "$c:$app/helpdesk/public/nxerp_login/css/nxerp-theme.css" "$(winpath "$hd")/helpdesk/public/nxerp_login/css/nxerp-theme.css"
docker cp "$c:/tmp/nxerp-css/." "$(winpath "$here")/nxerp/public/css"

echo "done. Review with git diff in both repos, then commit."
