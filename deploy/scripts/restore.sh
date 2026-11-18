#!/usr/bin/env bash
# Restore one site from a backup directory made by backup.sh. DESTRUCTIVE: replaces the site's database and files.
#
#   NXERP_DB_ROOT_PASSWORD=... deploy/scripts/restore.sh --yes <backup-dir> [--migrate] [--no-safety-backup]
#
# <backup-dir> may also be an encrypted backup, <dir>.tar.age, made by backup.sh with NXERP_BACKUP_AGE_RECIPIENT. Then
# NXERP_BACKUP_AGE_IDENTITY (path to the age PRIVATE key file, never printed) is required and <dir>.tar.age.sha256 must sit next to it.
# The archive is checked against that checksum, decrypted into a private (mode 700) temporary folder, restored exactly like a plain
# directory, and the temporary folder is removed on exit even when the restore fails.
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
if [ ! -d "$src" ] && [ ! -f "$src" ]; then die "usage: $0 --yes <backup-dir | backup.tar.age> [--migrate] [--no-safety-backup]"; fi
[ -n "${NXERP_DB_ROOT_PASSWORD:-}" ] || die "NXERP_DB_ROOT_PASSWORD is not set (the database root password; bench needs it to recreate the site database)"

remote='' plain=''
cleanup() {
	[ -z "$remote" ] || inbench "rm -rf $remote" >/dev/null 2>&1 || true
	[ -z "$plain" ] || rm -rf "$plain"
}
trap cleanup EXIT

encrypted=0
case "$src" in
	*.tar.age)
		[ -f "$src" ] || die "$src is not a file"
		encrypted=1
		command -v age >/dev/null 2>&1 || die "age is not installed, so $src cannot be decrypted (see docs/runbooks/backup-restore.md)"
		[ -n "${NXERP_BACKUP_AGE_IDENTITY:-}" ] || die "NXERP_BACKUP_AGE_IDENTITY is not set (path to the age private key file)"
		[ -f "$NXERP_BACKUP_AGE_IDENTITY" ] || die "NXERP_BACKUP_AGE_IDENTITY does not point to a file"
		[ -f "$src.sha256" ] || die "$src.sha256 is missing: refusing to restore an unverified backup"
		;;
	*) [ -d "$src" ] || die "$src is a file but not a .tar.age backup" ;;
esac

if [ "$encrypted" = 1 ]; then
	if [ "$yes" != 1 ]; then
		log "DRY RUN: would verify the checksum of $src, decrypt it with NXERP_BACKUP_AGE_IDENTITY and restore $NXERP_SITE from it"
		log "re-run with --yes to apply"
		exit 0
	fi
	(cd "$(dirname "$src")" && sha256sum -c --quiet "$(basename "$src").sha256") || die "checksum mismatch: the encrypted backup is corrupt or was modified"
	log "encrypted archive checksum OK"
	plain=$(umask 077 && mktemp -d "${TMPDIR:-/tmp}/nxerp-restore-plain.XXXXXX") || die "could not create a temporary folder"
	chmod 700 "$plain"
	# age authenticates the archive: a wrong key or a tampered file fails here, before anything is restored
	age -d -i "$(hostpath "$NXERP_BACKUP_AGE_IDENTITY")" "$(hostpath "$src")" | tar -C "$plain" -xf - || die "could not decrypt $src with the given identity (nothing was changed)"
	log "decrypted into a private temporary folder"
	src=$plain
fi

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
# docker cp leaves the files root-owned (and private, if they were on the host); bench runs as frappe and must read them
dc exec -T -u root "$NXERP_SERVICE" chown -R frappe:frappe "$remote" >/dev/null
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
