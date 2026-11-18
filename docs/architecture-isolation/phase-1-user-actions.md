# Phase 1: your actions (the human checklist)

Claude Code does the code, the documents and the checks. These are the steps that only a person can do, **in order**. Placeholders in angle brackets are values you
supply; nothing here contains a real secret. Steps marked *scratch* touch only a disposable copy; steps 1.3 and 1.9 touch the production host.

**Status of the code:** work packages 1A, 1B and 1C are on the branch `hybrid/phase-1-harden`. Nothing has been pushed or merged, and nothing has run on production.

## 1.1 Docker works
```bash
docker version
docker compose version
```
Expected: client and server versions, no error.

## 1.2 Install `age` and make the backup key pair (on your own machine, not the server)
```bash
# Windows: winget install --id FiloSottile.age     macOS: brew install age     Debian/Ubuntu: sudo apt install age
age --version
age-keygen -o nxerp-backup.key
```
Expected: `Public key: age1...` is printed. The file holds the **private** key. Copy it to **two offline places** (an encrypted USB stick and a password-manager
attachment), then delete it from the working folder. If every copy is lost, every encrypted backup is unreadable for good. Note the public key as `<age-public-key>`.

## 1.3 Take a read-only backup copy of production (off-peak; only after you decide to)
```bash
# on the production host, in the deployment directory
NXERP_ENV_FILES=.env NXERP_BACKUP_DIR=/var/backups/nxerp deploy/scripts/backup.sh
scp -r <user>@<prod-host>:/var/backups/nxerp/<dir> ./scratch-backup/
```
Keep the copy on an encrypted disk and delete it when finished: it holds personal data and the `encryption_key`.

## 1.4 Build a scratch copy of the stack (*scratch*)
```bash
cp deploy/env/staging-like/.env.example deploy/env/staging-like/.env
# edit .env: NXERP_IMAGE_TAG, NXERP_SITE; generate the two passwords:
python3 -c 'import secrets; print(secrets.token_urlsafe(24))'
chmod 600 deploy/env/staging-like/.env
export NXERP_COMPOSE_PROJECT=nxerp-scratch NXERP_ENV_FILES=deploy/env/staging-like/.env NXERP_HTTP_PORT=18080
docker compose -p nxerp-scratch --env-file deploy/env/staging-like/.env -f deploy/docker/compose/staging-like/compose.yaml up -d mariadb redis-cache redis-queue configurator
docker compose -p nxerp-scratch --env-file deploy/env/staging-like/.env -f deploy/docker/compose/staging-like/compose.yaml --profile init run --rm create-site
docker compose -p nxerp-scratch --env-file deploy/env/staging-like/.env -f deploy/docker/compose/staging-like/compose.yaml up -d
```
Check: `curl -s http://localhost:18080/api/method/ping` prints `{"message":"pong"}`. Undo: `docker compose -p nxerp-scratch down -v`.

## 1.5 Restore the production copy into the scratch stack (*scratch*)
```bash
NXERP_SITE=<site> NXERP_COMPOSE_PROJECT=nxerp-scratch NXERP_ENV_FILES=deploy/env/staging-like/.env \
  deploy/scripts/restore.sh --yes ./scratch-backup/<dir>
```

## 1.6 Neutralise the scratch copy (mandatory before anything runs; *scratch*)
It still holds real mail settings and webhooks, and could contact real people.
```bash
S="docker compose -p nxerp-scratch --env-file deploy/env/staging-like/.env -f deploy/docker/compose/staging-like/compose.yaml exec -T backend bash -lc"
$S 'cd /home/frappe/frappe-bench && bench --site <site> set-config mute_emails 1 && bench --site <site> disable-scheduler'
$S 'cd /home/frappe/frappe-bench && bench --site <site> mariadb' <<'SQL'
UPDATE `tabEmail Account` SET enable_incoming=0, enable_outgoing=0;
UPDATE tabWebhook SET enabled=0;
SELECT COUNT(*) AS active_email_accounts FROM `tabEmail Account` WHERE enable_incoming=1 OR enable_outgoing=1;
SQL
```
Expected: the last query prints `0`.

## 1.7 Run the measurement queries and record them (*scratch*)
Run U2 to U5, U9 and U15 to U18 from `docs/architecture-isolation/measurements.md`; paste **redacted** output there (placeholders such as `[Customer Name]`; counts only).

## 1.8 Record the baseline isolation audit (*scratch*)
```bash
NXERP_SITE=<site> NXERP_COMPOSE_PROJECT=nxerp-scratch NXERP_ENV_FILES=deploy/env/staging-like/.env scripts/isolation_audit.sh all
```
Save the PASS / FAIL / UNVERIFIED lines in `measurements.md`.

## 1.9 Schedule the nightly encrypted backup on the production host (production change: only with your explicit approval)
```bash
crontab -e
# add one line (02:15 every night):
15 2 * * * cd /opt/nxerp && NXERP_ENV_FILES=.env NXERP_BACKUP_DIR=/var/backups/nxerp NXERP_BACKUP_AGE_RECIPIENT=<age-public-key> NXERP_BACKUP_DELETE_PLAINTEXT=1 NXERP_BACKUP_KEEP_DAYS=30 deploy/scripts/backup.sh >> /var/log/nxerp-backup.log 2>&1
```
Check tomorrow: `ls -l /var/backups/nxerp` shows a `.tar.age` and no plain folder; `tail /var/log/nxerp-backup.log`. Set `NXERP_BACKUP_UPLOAD_CMD` to copy backups off the host.
The host needs the `age` binary installed. Undo: `crontab -e` and delete the line.

## 1.10 Run a restore drill from an encrypted backup (*scratch*)
```bash
NXERP_BACKUP_AGE_IDENTITY=./nxerp-backup.key NXERP_SITE=<site> NXERP_COMPOSE_PROJECT=nxerp-scratch \
  NXERP_ENV_FILES=deploy/env/staging-like/.env deploy/scripts/restore.sh --yes ./scratch-backup/<dir>.tar.age
deploy/scripts/healthcheck.sh
```
Write down how long it took (your real recovery time) in `docs/runbooks/backup-restore.md`.

## 1.11 Confirm the decisions
Open `docs/adr/ADR-009-hybrid-database-architecture.md`. For each of A1 to A13 write "confirmed" or your change in the "Owner's answer" column; record the hosting and
data-classification decisions under "Open points". When you are satisfied, set the status to Accepted yourself.
