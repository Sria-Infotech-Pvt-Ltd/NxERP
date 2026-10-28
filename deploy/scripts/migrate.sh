#!/usr/bin/env bash
# Apply the migrations of the code that is currently deployed to the site, with a backup first and a health check after.
#
#   deploy/scripts/migrate.sh [--skip-backup]
#
# Order: backup (verified) -> maintenance mode on -> bench migrate -> clear cache -> maintenance mode off -> healthcheck.
# Frappe has no "down" migrations, so the backup IS the rollback (see deploy/scripts/rollback.sh).
# On a failed migrate the site is LEFT IN MAINTENANCE MODE on purpose (a half-migrated site must not serve users); the
# script prints the backup path and the rollback command and exits non-zero.
#
# Writes the backup path to $NXERP_BACKUP_DIR/LAST_BACKUP so the deploy workflow and rollback.sh can find it.
set -euo pipefail
# shellcheck source=deploy/scripts/lib.sh
. "$(dirname "$0")/lib.sh"
scripts=$(cd "$(dirname "$0")" && pwd)

backup=1
case "${1:-}" in
	--skip-backup) backup=0 ;;
	"") ;;
	*) die "usage: $0 [--skip-backup]" ;;
esac

before=$(bench_site list-apps 2>/dev/null | tr '\n' ';' || true)
log "apps before: ${before:-unknown}"

backup_dir=none
if [ "$backup" = 1 ]; then
	backup_dir=$("$scripts/backup.sh" | tail -n 1) || die "backup failed: not migrating"
	mkdir -p "$NXERP_BACKUP_DIR"
	echo "$backup_dir" >"$NXERP_BACKUP_DIR/LAST_BACKUP"
	log "backup: $backup_dir"
else
	log "WARNING: --skip-backup: there is no rollback point for this migration"
fi

log "maintenance mode on"
bench_site set-maintenance-mode on >/dev/null
if ! bench_site migrate; then
	log "MIGRATE FAILED. The site is in maintenance mode. Backup: $backup_dir"
	log "to roll back: deploy/scripts/rollback.sh --previous-tag <tag> --backup $backup_dir --yes"
	exit 1
fi
bench_site clear-cache >/dev/null
bench_site set-maintenance-mode off >/dev/null
log "maintenance mode off"
log "apps after: $(bench_site list-apps 2>/dev/null | tr '\n' ';' || true)"
"$scripts/healthcheck.sh"
log "migrate complete (backup: $backup_dir)"
