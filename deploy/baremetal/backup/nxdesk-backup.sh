#!/usr/bin/env bash
# Daily backup of every NXDESK site (database and files) with Frappe's own backup, kept for 14 days. Optional: encrypt with `age` and copy off the server.
#   OFFSITE=user@backup-host:/path   copy the backup folders there with rsync (optional)
#   AGE_RECIPIENT=age1...            encrypt each archive for this public key (optional; needs `age`)
# Run as the `deploy` user (the timer in this folder does). Writes only into the sites' own private/backups folders and /var/backups/nxdesk.
set -euo pipefail
BENCH_BIN=/home/deploy/.local/bin/bench
OUT=/var/backups/nxdesk
KEEP_DAYS=14
SITES=(
	"/srv/apps/helpdesk/frappe-bench helpdesk.nxsys.in"
	"/srv/apps/nxerp/frappe-bench nxerp.nxsys.in"
	# add the identity site after it exists:  "/srv/apps/nxerp/frappe-bench nxdesk.nxsys.in"
)
mkdir -p "$OUT"
stamp=$(date +%Y%m%d-%H%M%S)
for entry in "${SITES[@]}"; do
	read -r bench_dir site <<<"$entry"
	(cd "$bench_dir" && "$BENCH_BIN" --site "$site" backup --with-files >/dev/null)
	newest=$(ls -1t "$bench_dir/sites/$site/private/backups"/*-database.sql.gz | head -n 1)
	prefix=${newest%-database.sql.gz}
	dest="$OUT/$site-$stamp"
	mkdir -p "$dest"
	cp "$prefix"-* "$dest"/
	(cd "$dest" && sha256sum -- * >SHA256SUMS)
	if [ -n "${AGE_RECIPIENT:-}" ] && command -v age >/dev/null 2>&1; then
		tar -C "$dest" -cf - . | age -r "$AGE_RECIPIENT" -o "$dest.tar.age" && rm -rf "$dest"
	fi
done
find "$OUT" -mindepth 1 -maxdepth 1 -mtime +"$KEEP_DAYS" -exec rm -rf {} +
[ -z "${OFFSITE:-}" ] || rsync -a --delete "$OUT"/ "$OFFSITE"/
echo "backup $stamp done: $(find "$OUT" -mindepth 1 -maxdepth 1 | wc -l) item(s) in $OUT"
