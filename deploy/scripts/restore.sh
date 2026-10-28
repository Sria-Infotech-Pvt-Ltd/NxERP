#!/usr/bin/env bash
# Restore one site from a backup directory made by backup.sh. DESTRUCTIVE: replaces the site's database and files.
#
#   NXERP_DB_ROOT_PASSWORD=... deploy/scripts/restore.sh --yes <backup-dir> [--migrate] [--no-safety-backup]
#
#   --yes                required; without it the script only prints what it would do
#   --migrate            run `bench migrate` after the restore (needed when the backup is older than the running code)
#   --no-safety-backup   skip the backup of the current state taken before it is overwritten (not recommended)
#
# Steps: verify checksums -> safety backup of the CURRENT state -> maintenance mode on -> bench restore ->
# (optional) migrate -> clear cache -> maintenance mode off -> healthcheck.
# If the restore itself fails the site is left in maintenance mode on purpose; the safety backup path is printed.
set -euo pipefail
# shellcheck source=deploy/scripts/lib.sh
. "$(dirname "$0")/lib.sh"
scripts=$(cd "$(dirname "$0")" && pwd)

yes=0 migrate=0 safety=1 src=''
for arg in "$@"; do
	case "$arg" in
		--yes) yes=1 ;;
		--migrate) migrate=1 ;;
		--no-safety-backup) safety=0 ;;
		-*) die "unknown option $arg" ;;
		*) src=$arg ;;
	esac
done
[ -n "$src" ] && [ -d "$src" ] || die "usage: $0 --yes <backup-dir> [--migrate] [--no-safety-backup]"
[ -n "${NXERP_DB_ROOT_PASSWORD:-}" ] || die "NXERP_DB_ROOT_PASSWORD is not set (the database root password; bench needs it to recreate the site database)"

db=$(find "$src" -maxdepth 1 -name '*-database.sql.gz' | head -n 1)
[ -n "$db" ] || die "no *-database.sql.gz in $src"
pub=$(find "$src" -maxdepth 1 -name '*-files.tar' ! -name '*-private-files.tar' | head -n 1)
priv=$(find "$src" -maxdepth 1 -name '*-private-files.tar' | head -n 1)

if [ "$yes" != 1 ]; then
	log "DRY RUN: would restore $NXERP_SITE from $src (database $(basename "$db")${pub:+, public files}${priv:+, private files})"
	log "re-run with --yes to apply"
	exit 0
fi

[ -f "$src/SHA256SUMS" ] || die "$src/SHA256SUMS is missing: refusing to restore an unverified backup"
(cd "$src" && sha256sum -c --quiet SHA256SUMS) || die "checksum mismatch: the backup is corrupt or was modified"
log "checksums OK"

if [ "$safety" = 1 ]; then
	log "safety backup of the current state first"
	safety_dir=$("$scripts/backup.sh" | tail -n 1) || die "safety backup failed; nothing was changed"
	log "safety backup: $safety_dir"
fi

remote="/tmp/nxerp-restore-$$"
inbench "mkdir -p $remote" >/dev/null
dc cp "$(hostpath "$src")/." "$NXERP_SERVICE:$remote/" >/dev/null
cleanup() { inbench "rm -rf $remote" >/dev/null 2>&1 || true; }
trap cleanup EXIT

log "maintenance mode on"
bench_site set-maintenance-mode on >/dev/null
cmd="bench --site $NXERP_SITE restore $remote/$(basename "$db") --db-root-password \"\$NXERP_DB_ROOT_PASSWORD\" --force"
[ -z "$pub" ] || cmd="$cmd --with-public-files $remote/$(basename "$pub")"
[ -z "$priv" ] || cmd="$cmd --with-private-files $remote/$(basename "$priv")"
if ! inbench "$cmd"; then
	die "bench restore failed; the site is LEFT IN MAINTENANCE MODE. Safety backup: ${safety_dir:-none}"
fi
if [ "$migrate" = 1 ]; then
	log "migrate"
	bench_site migrate || die "migrate failed after restore; site left in maintenance mode. Safety backup: ${safety_dir:-none}"
fi
bench_site clear-cache >/dev/null
bench_site set-maintenance-mode off >/dev/null
log "maintenance mode off"
"$scripts/healthcheck.sh"
log "restore complete: $NXERP_SITE from $src"
