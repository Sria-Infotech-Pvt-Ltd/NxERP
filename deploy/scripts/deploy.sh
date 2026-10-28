#!/usr/bin/env bash
# Deploy one image tag on THIS host (run it on the staging/production host, normally over ssh from the deploy workflow).
#
#   deploy/scripts/deploy.sh --tag 0.1.0 [--init] [--no-rollback]
#
#   --tag TAG        image tag to run (the value of NXERP_IMAGE_TAG); required
#   --init           first deployment: create the site and install the apps instead of migrating
#   --no-rollback    on failure stop and leave the site in maintenance mode instead of rolling back automatically
#
# Order: pull the image -> record the running tag -> switch the tag in the env file -> start the stack ->
# backup + maintenance + migrate (migrate.sh) -> healthcheck. A failed migrate or healthcheck rolls back to the recorded
# tag (rollback.sh, restoring the pre-migration backup) unless --no-rollback. Exit code 0 only when the new tag is healthy.
#
# Environment (same as the other scripts, plus):  NXERP_ENV_FILES (default ".env", the host's secrets file, mode 600),
# NXERP_COMPOSE_FILE (default compose.yaml next to this script's parent), NXERP_SITE, NXERP_BACKUP_DIR.
# NXERP_DB_ROOT_PASSWORD is read from the env file by lib.sh when it is not already exported.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
NXERP_COMPOSE_FILE=${NXERP_COMPOSE_FILE:-$here/../compose.yaml}
NXERP_ENV_FILES=${NXERP_ENV_FILES:-.env}
export NXERP_COMPOSE_FILE NXERP_ENV_FILES
# shellcheck source=deploy/scripts/lib.sh
. "$here/lib.sh"

tag='' init=0 rollback=1
while [ $# -gt 0 ]; do
	case "$1" in
		--tag) tag=${2:?--tag needs a value}; shift ;;
		--init) init=1 ;;
		--no-rollback) rollback=0 ;;
		*) die "unknown option $1" ;;
	esac
	shift
done
[[ "$tag" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9._-]+)?$ ]] || die "--tag must look like 1.2.3, 1.2.3-rc.1 or 1.2.3-ab12cd34ef56 (got '$tag')"
env_file=${NXERP_ENV_FILES%% *}
[ -f "$env_file" ] || die "env file not found: $env_file (create it from deploy/env/*.env.example)"

set_tag() { # set_tag TAG: rewrite NXERP_IMAGE_TAG in the env file atomically, keeping its mode
	local tmp
	tmp=$(mktemp "$env_file.XXXXXX")
	{ grep -v '^NXERP_IMAGE_TAG=' "$env_file" || true; echo "NXERP_IMAGE_TAG=$1"; } >"$tmp"
	chmod --reference="$env_file" "$tmp"
	mv "$tmp" "$env_file"
}

previous=$(sed -n 's/^NXERP_IMAGE_TAG=//p' "$env_file" | head -n 1)
log "deploying $tag (currently: ${previous:-none})"

NXERP_IMAGE_TAG=$tag dc pull --quiet
set_tag "$tag"
dc up -d --remove-orphans

fail() {
	log "FAILED: $1"
	if [ "$rollback" = 1 ] && [ -n "$previous" ] && [ "$init" = 0 ]; then
		last=$(cat "$NXERP_BACKUP_DIR/LAST_BACKUP" 2>/dev/null || true)
		if [ -n "$last" ] && [ -d "$last" ]; then
			log "rolling back to $previous and restoring $last"
			"$here/rollback.sh" --yes --previous-tag "$previous" --backup "$last" || log "ROLLBACK ALSO FAILED: follow docs/runbooks/rollback.md by hand"
			set_tag "$previous"
		else
			log "no backup recorded: not rolling back automatically. Follow docs/runbooks/rollback.md"
		fi
	else
		log "left as is (site may be in maintenance mode). Follow docs/runbooks/rollback.md"
	fi
	exit 1
}

if [ "$init" = 1 ]; then
	dc --profile init run --rm create-site || fail "site creation failed"
else
	"$here/migrate.sh" || fail "migrate failed"
fi
"$here/healthcheck.sh" || fail "healthcheck failed"
log "deployed $tag"
