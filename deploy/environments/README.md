# deploy/environments/

Configuration templates for the two real environments. **Templates only: every value is a placeholder.** Status:
**ready, not executed.** No staging or production host, registry, domain or secret exists yet
(see [docs/governance/owner-action-list.md](../../docs/governance/owner-action-list.md)).

| Environment | Template | GitHub Environment | Deployed by |
| --- | --- | --- | --- |
| staging | [`staging/staging.env.example`](staging/staging.env.example) | `staging` (no reviewers) | `.github/workflows/deploy-staging.yml`, automatically after a release candidate |
| production | [`production/production.env.example`](production/production.env.example) | `production` (**required reviewers**) | `.github/workflows/deploy-production.yml`, manually (`workflow_dispatch`) |
| staging-like (rehearsal) | [`../staging-like/.env.example`](../staging-like/.env.example) | none | a person, on any Docker host |

## Where each kind of value lives

| Kind | Examples | Lives in | Never in |
| --- | --- | --- | --- |
| **Secret** | `DEPLOY_SSH_KEY`, `REGISTRY_PULL_TOKEN`, `SMTP_PASSWORD`, `BACKUP_REMOTE_CREDENTIALS` | GitHub Environment **Secrets** (deploy-time) | git, workflow YAML, logs, images, chat |
| **Host secret** | `NXERP_DB_ROOT_PASSWORD`, `NXERP_ADMIN_PASSWORD` | `.env` on the host, mode `600`, created once by the owner (not by CI) | git, GitHub (CI never needs them) |
| **Variable** | `DEPLOY_HOST`, `DEPLOY_PATH`, `STAGING_URL`, `NXERP_SITE`, `NXERP_IMAGE` | GitHub Environment **Variables** | secrets store (they are not secret) |
| **Pin** | Frappe/ERPNext/Helpdesk versions | `deploy/versions.env`, `deploy/apps.json` | an environment file (a pin is the same everywhere) |

The deploy workflows reference secrets only as `${{ secrets.NAME }}` and variables as `${{ vars.NAME }}`. The database root and
admin passwords are deliberately **not** GitHub secrets: the workflow SSHes to the host, where `docker compose` reads the host's
own `.env`, so the CI system never holds the keys to the database.

## Host layout (ASSUMPTION: one Docker host per environment)

```
/opt/nxerp/                 DEPLOY_PATH, owned by the deploy user
  compose.yaml              copy of deploy/staging-like/compose.yaml (same file for staging and production, see below)
  nginx.conf.template
  scripts/                  copy of deploy/scripts/ (the workflows sync it from the tag being deployed)
  .env                      host secrets + NXERP_IMAGE_TAG (mode 600)
/var/backups/nxerp/         NXERP_BACKUP_DIR (encrypted volume recommended)
```

DECISION: staging and production run the same compose file as the staging-like environment, so a deploy is rehearsed on the exact
topology it will use. Production-specific hardening is the owner's call and not done here: TLS termination and certificates,
managed or replicated MariaDB, off-host Redis, resource limits, log shipping, a firewall that exposes only 443.

## Create a GitHub Environment (UI, repository admin)

Repository **Settings > Environments > New environment** > name `staging` / `production`.
For `production`: tick **Required reviewers**, add at least two people or a team, tick **Prevent self-review**; under
**Deployment branches and tags** choose **Selected branches and tags** and add `main` (the deploy workflows run from `main` and check the release tag out themselves). Then add the
Secrets and Variables named in the template. `gh` equivalent: `gh api -X PUT repos/Sria-Infotech-Pvt-Ltd/NxERP/environments/production`
(needs admin; not run).
