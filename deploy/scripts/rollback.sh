#!/usr/bin/env bash
# Roll the deployment back to the previous image tag, and (when migrations ran) restore the pre-migration backup.
#
#   NXERP_DB_ROOT_PASSWORD=... deploy/scripts/rollback.sh --yes --previous-tag <tag> (--backup <dir> | --code-only)
#
#   --previous-tag TAG  the image tag to go back to (e.g. 0.1.0-ab12cd34ef56); passed to compose as NXERP_IMAGE_TAG
#   --backup DIR        the backup taken by migrate.sh before the failed release: restored after the old code is running.
#                       REQUIRED whenever the failed release ran migrations (Frappe cannot migrate down)
#   --code-only         only switch the image back, do not touch the database. Use ONLY when the release failed before
#                       migrate ran, or the previous release has no schema difference. The script cannot check this for you.
#   --yes               required to act; without it the script prints the plan
#
# Order: maintenance mode on -> switch image -> restore backup (restore.sh, which verifies checksums and takes a safety
# backup of the failed state for forensics) -> maintenance mode off -> healthcheck.
#
# Compose services recreated: $NXERP_ROLLBACK_SERVICES (default "backend websocket queue-worker scheduler"). The compose
# file must read the image tag from ${NXERP_IMAGE_TAG} (deploy/staging-like/compose.yaml does).
set -euo pipefail
# shellcheck source=deploy/scripts/lib.sh
. "$(dirname "$0")/lib.sh"
scripts=$(cd "$(dirname "$0")" && pwd)

yes=0 code_only=0 tag='' backup=''
while [ $# -gt 0 ]; do
	case "$1" in
		--yes) yes=1 ;;
		--previous-tag) tag=${2:?--previous-tag needs a value}; shift ;;
		--backup) backup=${2:?--backup needs a value}; shift ;;
		--code-only) code_only=1 ;;
		*) die "unknown option $1" ;;
	esac
	shift
done
[ -n "$tag" ] || die "--previous-tag is required"
{ [ -n "$backup" ] || [ "$code_only" = 1 ]; } || die "give --backup <dir> (database restore) or --code-only (you assert no migration ran)"
[ -z "$backup" ] || [ -d "$backup" ] || die "backup directory not found: $backup"
services=${NXERP_ROLLBACK_SERVICES:-backend websocket queue-worker scheduler}

if [ "$yes" != 1 ]; then
	log "DRY RUN plan: maintenance on; image -> NXERP_IMAGE_TAG=$tag for: $services; $([ -n "$backup" ] && echo "restore $backup" || echo "code only, database untouched"); maintenance off; healthcheck"
	log "re-run with --yes to apply"
	exit 0
fi

log "maintenance mode on"
bench_site set-maintenance-mode on >/dev/null || log "could not set maintenance mode (site may be down); continuing"

log "switching image to $tag"
# shellcheck disable=SC2086
NXERP_IMAGE_TAG=$tag dc up -d --no-deps $services

# wait for the old code to answer before touching data
for i in $(seq 1 30); do
	if inbench "curl -fsS -o /dev/null http://localhost:${NXERP_HTTP_PORT:-8000}/api/method/ping || [ \$? = 22 ]" >/dev/null 2>&1; then break; fi
	[ "$i" != 30 ] || die "the service did not come back on image $tag"
	sleep 5
done

if [ -n "$backup" ]; then
	"$scripts/restore.sh" --yes "$backup"
else
	log "code-only rollback: database NOT restored"
	bench_site set-maintenance-mode off >/dev/null
	"$scripts/healthcheck.sh"
fi
log "rollback to $tag complete"
