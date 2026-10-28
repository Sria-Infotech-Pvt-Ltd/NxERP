# Runbook: backup and restore

**When to use:** before any migration or risky change (automatic in `migrate.sh`), on a schedule, and to restore after data loss or a
failed release. **Status:** the scripts were run against the throwaway dev-stack site `nxerp-e2e.localhost` (below); they have NOT been
run on a staging/production host, and no off-host storage or schedule exists yet.

## Setup (once per host)

Scripts live in `deploy/scripts/` (copied to `$DEPLOY_PATH/scripts/` by the deploy workflow). They are parameterised by environment:

```bash
cd /opt/nxerp                                    # DEPLOY_PATH: compose.yaml, scripts/, .env (mode 600)
export NXERP_COMPOSE_FILE=/opt/nxerp/compose.yaml NXERP_ENV_FILES=/opt/nxerp/.env \
       NXERP_SITE=app.example.test NXERP_BACKUP_DIR=/var/backups/nxerp
```

`NXERP_DB_ROOT_PASSWORD` is read from `.env` by the scripts (never printed, never on a command line on the host). Other knobs:
`NXERP_SERVICE` (default `backend`), `NXERP_BACKUP_KEEP_DAYS`, `NXERP_BACKUP_UPLOAD_CMD` (your off-site copy command, gets the backup
directory as `$1`).

## Backup

```bash
scripts/backup.sh                 # database + public/private files + site config; prints the backup directory last
scripts/backup.sh --no-files      # database only (fast, for a pre-check)
```

Result: `$NXERP_BACKUP_DIR/<UTC stamp>-<site>/` with the Frappe files, `MANIFEST` (site, time, app versions) and `SHA256SUMS`.
**Verify** (the script already does the first three and fails otherwise): database dump is valid gzip and contains `CREATE TABLE`;
files archives are readable; checksums written. Then check the directory is mode 700 and that the off-site copy arrived.

**Security:** the backup holds personal data and the site's `encryption_key` (needed to read encrypted fields after a restore). Store it
encrypted, restrict access, and never attach it to a ticket or chat. Retention and the off-site target are the owner's decisions
(owner-action-list item 18).

## Restore (destructive)

```bash
scripts/restore.sh /var/backups/nxerp/20261028T065641Z-app.example.test            # dry run: says what it would do
scripts/restore.sh --yes /var/backups/nxerp/20261028T065641Z-app.example.test      # does it
scripts/restore.sh --yes <dir> --migrate     # when the backup is OLDER than the code that is running
```

The script: verifies `SHA256SUMS` (refuses without it), takes a **safety backup of the current state**, switches maintenance mode on,
runs `bench restore --force` with files, optionally migrates, clears the cache, switches maintenance mode off, and runs
`healthcheck.sh`. If `bench restore` fails the site stays in maintenance mode on purpose; the safety backup path is printed.

**Restore drill (do this before you need it):** on a scratch host or the staging-like stack, restore the newest production backup, log
in, open a document with an attachment, confirm an encrypted field (e.g. an email account password) still works. Record date and result
here. **No drill has been done yet.**

## Verification after a restore

`scripts/healthcheck.sh` passes (ping, `/login` 200, expected apps installed, scheduler enabled); `NXERP_BASE_URL=https://... scripts/smoke.sh`
passes; log in as a real user and as a customer; the count of a business document equals what it was at backup time.

## What was tested (FACT, 2026-10-28, dev stack, site `nxerp-e2e.localhost`)

| Test | Result |
| --- | --- |
| `backup.sh` (4 runs, Windows host through Git Bash) | 801 tables in the dump, 6 files, checksums verified; after fixing a Windows path-conversion bug in `docker compose cp` |
| `restore.sh` dry run | printed the plan, changed nothing |
| `restore.sh --yes` with a modified database dump | refused: `checksum mismatch`, site untouched |
| `restore.sh --yes` of a good backup (2 runs) | safety backup taken, maintenance on, restored, maintenance off, `healthcheck.sh` healthy, exit 0 |
| Not tested | a restore onto a different host; an encrypted-field check; off-site upload; the scheduled backup; production-sized data |
