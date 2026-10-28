# Runbook: rollback

**When to use:** a deployed release is broken (health check fails, errors, wrong access behaviour) and you decided going back is
faster or safer than fixing forward. Fixing forward is `hotfix.md`. **Status:** `rollback.sh` and `deploy.sh`'s automatic rollback are
syntax-checked and shellchecked, and `rollback.sh`'s dry-run plan was printed; they have **not been executed** (no compose host
exists). The restore it relies on (`restore.sh`) was executed, see `backup-restore.md`.

## Decide: code only, or code + database?

| Situation | Rollback |
| --- | --- |
| The release failed **before** `migrate` ran, or it has no schema/patch change | `--code-only`: switch the image back; database untouched |
| `migrate` ran (successfully or not) | **restore the pre-migration backup** with the old image. Frappe cannot migrate down. Data entered since the backup is lost: say so before you do it |

## Commands

Automatic: `deploy.sh` rolls back by itself when `migrate.sh` or the health check fails (it records the previous tag first and uses
`$NXERP_BACKUP_DIR/LAST_BACKUP`). Pass `--no-rollback` to stop and look instead.

Manual (on the host; see `backup-restore.md` for the exported variables):

```bash
cat $NXERP_BACKUP_DIR/LAST_BACKUP                              # the backup migrate.sh took before the failed release
scripts/rollback.sh --previous-tag 0.1.0 --code-only           # dry run (prints the plan)
scripts/rollback.sh --yes --previous-tag 0.1.0 --backup "$(cat $NXERP_BACKUP_DIR/LAST_BACKUP)"
sed -i 's/^NXERP_IMAGE_TAG=.*/NXERP_IMAGE_TAG=0.1.0/' .env     # so a later `docker compose up` keeps the old tag
```

From GitHub: run **Deploy production** with `action: rollback`, `tag` = the tag to go back to, optional `backup_dir`
(`.github/workflows/deploy-production.yml`; needs the production Environment approval).

What `rollback.sh` does: maintenance mode on; `NXERP_IMAGE_TAG=<old> docker compose up -d --no-deps backend websocket queue-worker
scheduler`; waits for the old code to answer; `restore.sh --yes <backup>` (which verifies checksums, takes a safety backup of the failed
state for forensics, restores, maintenance off, health check). It refuses to run without either `--backup` or `--code-only`.

## Verify

`scripts/healthcheck.sh`; `NXERP_BASE_URL=https://app.example.test scripts/smoke.sh`; log in as an internal user and a customer; the
running tag is the old one: `docker compose ps` / `docker inspect`; the app versions match the old release (`bench --site <site> list-apps`).

## After

Keep the failed state's safety backup until the investigation ends. Open an incident (`incident-response.md`), write down what failed,
and make the next attempt a new tag (never re-tag).

## What was NOT tested

Everything about the compose-based switch of image tags, the wait loop, and the production workflow path. Do a rollback drill on the
staging-like stack as soon as a host exists (deploy N, deploy N+1 with a deliberately failing migration, watch the automatic rollback).
