# Runbook: deploy

**When to use:** put a released image tag on staging or production. **Status:** `deploy.sh` and the workflows are written and
syntax/lint-checked; **nothing has been deployed anywhere**: no host, registry package or GitHub Environment exists. The pieces it
calls were exercised against the dev stack as listed at the end.

## Topology (staging, production and the staging-like rehearsal)

One Docker host per environment running `deploy/staging-like/compose.yaml`: image `nxerp:<tag>` as `backend` (gunicorn), `websocket`,
`queue-worker`, `scheduler`; MariaDB 11.8; two Redis; an nginx `proxy` on port 8080 (HTTP only: TLS terminates in front of it).
Host layout and which values are secrets: `deploy/environments/README.md`. Configuration is written into `sites/common_site_config.json`
by the image entrypoint from non-secret environment variables; secrets stay in the host's `.env` (mode 600).

## First deployment of an environment (once)

```bash
cd /opt/nxerp                                   # after the workflow (or you) copied compose.yaml, nginx.conf.template, scripts/
cp /path/to/filled/.env .env && chmod 600 .env  # from deploy/staging-like/.env.example
scripts/deploy.sh --tag 0.1.0 --init            # pulls the image, starts the stack, creates the site, installs the apps, healthcheck
```

Then: configure the outgoing email account, create the first real administrator, change/lock the install `Administrator` password, run
`scripts/smoke.sh` from your laptop, take a backup and do the restore drill (`backup-restore.md`).

## Every later deployment

By workflow (normal path): staging happens automatically after a `-rc` release; production is **Actions > Deploy production > Run
workflow** (`action: deploy`, `tag: vX.Y.Z`), approved by the Environment's reviewers. By hand on the host (same logic):

```bash
cd /opt/nxerp
export NXERP_SITE=app.example.test NXERP_BACKUP_DIR=/var/backups/nxerp
scripts/deploy.sh --tag 0.1.0                    # pull -> verified backup -> maintenance -> migrate -> healthcheck
NXERP_BASE_URL=https://app.example.test scripts/smoke.sh      # from outside
```

`deploy.sh` rolls back automatically when migrate or the health check fails (`--no-rollback` to stop instead); see `rollback.md`.
Maintenance mode shows users a "site is being updated" page for the duration of the migration only.

## Verification (after every deploy)

1. `scripts/healthcheck.sh`: ping, `/login`, the expected apps installed (`NXERP_EXPECT_APPS`), scheduler enabled.
2. `scripts/smoke.sh` over the public URL: login renders; `/nxerp/apps`, `/nxerp/go`, `/helpdesk`, `/desk` redirect anonymous users to
   `/login`; `/api/resource/User` refuses anonymous callers.
3. Manual, for a release: log in as an internal user (lands on the launcher or the single app), as a customer (portal only, no Desk),
   open one ERPNext document and one Helpdesk ticket.
4. Browser journeys against staging are **not automated** (see the KNOWN GAP in `deploy-staging.yml`).

## What was tested (FACT, 2026-10-28, dev stack)

- `healthcheck.sh` against the dev site: passes with `NXERP_REQUIRE_SCHEDULER=0`; correctly **fails** when an expected app is missing
  and when the scheduler is disabled (a dev site has it disabled).
- `smoke.sh` against `http://localhost:8100` (dev site): all 8 checks pass; exits 1 when the URL is unreachable. The status codes it
  expects (301/302 to `/login`, 403) were observed on that site.
- `backup.sh`, `restore.sh`, `migrate.sh` on `nxerp-e2e.localhost`: see `backup-restore.md` / `migration-planning.md`.
- `docker compose config` of `deploy/staging-like/compose.yaml` with dummy values renders (and fails clearly without `NXERP_IMAGE_TAG`);
  the nginx template passes `nginx -t` in the `nginx:1.27-alpine` image.
- **Not tested:** starting the staging-like stack (needs the image), `deploy.sh`, `rollback.sh` execution, the SSH/registry steps, TLS, the
  GitHub Environment approval.
