#!/usr/bin/env bash
# Take a verified backup of one site (database + public and private files + site config) and copy it to the host.
#
#   deploy/scripts/backup.sh [--no-files]
#
# Output: $NXERP_BACKUP_DIR/<UTC timestamp>-<site>/  holding the Frappe backup files, SHA256SUMS and MANIFEST.
# The LAST line printed on stdout is the backup directory, so other scripts can capture it.
#
# Optional environment:
#   NXERP_BACKUP_KEEP_DAYS    delete local backup directories older than N days (default: keep everything)
#   NXERP_BACKUP_UPLOAD_CMD   command run with the backup directory as $1 after verification, e.g. an rclone/aws wrapper
#                             (off-site storage is the owner's choice: see docs/governance/owner-action-list.md)
#
# SECURITY: the backup contains personal data and the site's encryption_key (in the site config copy), which is
# required to restore encrypted fields. Treat the directory as secret: mode 700, encrypted storage, restricted access.
set -euo pipefail
# shellcheck source=deploy/scripts/lib.sh
. "$(dirname "$0")/lib.sh"

files=--with-files
case "${1:-}" in
	--no-files) files= ;;
	"") ;;
	*) die "usage: $0 [--no-files]" ;;
esac

stamp=$(date -u +%Y%m%dT%H%M%SZ)
dest="$NXERP_BACKUP_DIR/$stamp-$NXERP_SITE"
remote="/tmp/nxerp-backup-$stamp"
trap 'inbench "rm -rf $remote" >/dev/null 2>&1 || true' EXIT
mkdir -p "$dest"
chmod 700 "$dest" 2>/dev/null || true

log "backing up $NXERP_SITE to $dest"
inbench "mkdir -p $remote && bench --site $NXERP_SITE backup $files --backup-path $remote >/dev/null && ls -1 $remote" >"$dest/.listing" \
	|| die "bench backup failed (nothing was changed on the site)"
dc cp "$NXERP_SERVICE:$remote/." "$(hostpath "$dest")" >/dev/null || die "could not copy the backup out of the container"

# verification: required files present, archives readable, database dump looks like a dump
db=$(find "$dest" -maxdepth 1 -name '*-database.sql.gz' | head -n 1)
cfg=$(find "$dest" -maxdepth 1 -name '*-site_config_backup.json' | head -n 1)
[ -n "$db" ] || die "no database dump in the backup"
[ -n "$cfg" ] || die "no site config copy in the backup"
gzip -t "$db" || die "database dump is not a valid gzip file"
tables=$(gzip -dc "$db" | grep -c '^CREATE TABLE' || true)
[ "$tables" -gt 0 ] || die "database dump contains no CREATE TABLE statements"
if [ -n "$files" ]; then
	for f in "$dest"/*-files.tar "$dest"/*-private-files.tar; do
		[ -f "$f" ] || die "missing files archive: $f"
		tar -tf "$f" >/dev/null || die "unreadable archive: $f"
	done
fi

rm -f "$dest/.listing"
{
	echo "site=$NXERP_SITE"
	echo "created_utc=$stamp"
	echo "tables_in_dump=$tables"
	echo "image_tag=${NXERP_IMAGE_TAG:-unknown}"
	echo "apps:"
	inbench "bench --site $NXERP_SITE list-apps" 2>/dev/null | sed 's/^/  /' || true
} >"$dest/MANIFEST"
(cd "$dest" && sha256sum -- * >SHA256SUMS) # after MANIFEST, so every file but the checksum list itself is covered
chmod 600 "$dest"/* 2>/dev/null || true
log "verified: $tables tables in the dump, $(find "$dest" -type f | wc -l | tr -d ' ') files, checksums written"

if [ -n "${NXERP_BACKUP_UPLOAD_CMD:-}" ]; then
	log "uploading with NXERP_BACKUP_UPLOAD_CMD"
	$NXERP_BACKUP_UPLOAD_CMD "$dest" || die "upload command failed (the local backup is intact: $dest)"
fi
if [ -n "${NXERP_BACKUP_KEEP_DAYS:-}" ]; then
	find "$NXERP_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+$NXERP_BACKUP_KEEP_DAYS" -print -exec rm -rf {} + >&2 || true
fi
echo "$dest"
