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

## Encrypted backups (optional, off unless configured)

A plain backup folder holds personal data and the site's `encryption_key`. With [age](https://github.com/FiloSottile/age) it can be
written as one encrypted file that only the holder of a private key can open. Nothing changes while the variables below are unset.

1. **Make the key pair once** (on your own machine, not on the server): `age-keygen -o nxerp-backup.key`. It prints `Public key: age1...`.
   The file holds the **private** key.
2. **Keep the private key safe:** two offline copies (an encrypted USB stick and a password-manager attachment), then delete it from
   the working folder. **Never keep it on the host that stores the backups**, never commit it, never paste it in a ticket or chat.
   If every copy is lost, every backup encrypted to it is unreadable for good.
3. **Turn it on:** set `NXERP_BACKUP_AGE_RECIPIENT=<the age1... public key>` in the host's `.env` (the public key is safe to store).
   Optionally `NXERP_BACKUP_DELETE_PLAINTEXT=1` removes the plain folder after the encrypted file is written and checked.

```bash
NXERP_BACKUP_AGE_RECIPIENT=age1... NXERP_BACKUP_DELETE_PLAINTEXT=1 scripts/backup.sh
# last line: /var/backups/nxerp/<stamp>-<site>.tar.age   (next to it: <stamp>-<site>.tar.age.sha256)
```

`NXERP_BACKUP_UPLOAD_CMD` receives the `.tar.age` file when encryption is on, so the plaintext never leaves the host.
`NXERP_BACKUP_KEEP_DAYS` also removes old `.tar.age` files. A missing `age` binary or a recipient that does not start with `age1`
stops the script before anything is written.

**Restore from an encrypted backup** (run where the private key is, never copy the key to the server):

```bash
NXERP_BACKUP_AGE_IDENTITY=/path/to/nxerp-backup.key scripts/restore.sh --yes /var/backups/nxerp/<stamp>-<site>.tar.age
```

The script checks `<file>.sha256`, decrypts into a private temporary folder, then continues exactly as for a plain directory
(checksums inside the backup, safety backup, maintenance mode, `bench restore`, health check). The temporary folder is removed on exit,
also on failure. A wrong key or a modified file fails at the decryption step, before anything is changed.

## Restore (destructive)

```bash
scripts/restore.sh /var/backups/nxerp/20261028T065641Z-app.example.test            # dry run: says what it would do
scripts/restore.sh --yes /var/backups/nxerp/20261028T065641Z-app.example.test      # does it
scripts/restore.sh --yes <dir> --migrate     # when the backup is OLDER than the code that is running
```

The script: verifies `SHA256SUMS` (refuses without it), takes a **safety backup of the current state**, switches maintenance mode on,
runs `bench restore --force` with files, optionally migrates, clears the cache, switches maintenance mode off, and runs
`healthcheck.sh`. If `bench restore` fails the site stays in maintenance mode on purpose; the safety backup path is printed.

**Restore drill (do this before you need it):** on a scratch host or the staging-like stack (compose project `nxerp-scratch`,
never the live site), restore the newest backup, and for an encrypted one use the commands above. Then:

1. Run `deploy/scripts/healthcheck.sh` and log in; open a document with an attachment; confirm an encrypted field (for example an
   email account password) still works (if it does not, the `encryption_key` of the backup is missing on the scratch site).
2. Neutralise a restored copy of real data before it runs: `bench --site <site> set-config mute_emails 1`, `disable-scheduler`, and
   disable Email Accounts and Webhooks, so it cannot contact real people.
3. Record in the table below: date, backup file, time the restore took (your real recovery time), result, who ran it.

| Date | Backup | Encrypted | Restore took | Result | By |
| --- | --- | --- | --- | --- | --- |
| *(none recorded yet)* | | | | | |

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
