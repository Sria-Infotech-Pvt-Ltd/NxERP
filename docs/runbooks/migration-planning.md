# Runbook: migration planning

**When to use:** a release contains patches, schema/DocType changes, or an upstream pin bump (Frappe, ERPNext, Helpdesk). Frappe has
**no down-migrations**: the rollback of a migration is a restore of the pre-migration backup. Plan accordingly.

## 1. Classify the change

| Change | Risk | What to prepare |
| --- | --- | --- |
| Only `nxerp` code, no patch, no DocType change | low | normal deploy; backup still taken by `migrate.sh` |
| New `nxerp` patch (`patches.txt`) or fixture | medium | patch is idempotent (CLAUDE.md), run twice on a copy of production data |
| Upstream patch release (Frappe/ERPNext `16.x.y`) | medium | read the upstream release notes; rehearse on the staging-like stack |
| Upstream minor/major, Helpdesk rebase onto a new release | high | full rehearsal with a production backup restored on staging; ADR-002 updated; maintenance window |
| Frappe 17 | highest | new ADR; never in a patch PR |

## 2. Rehearse on a copy

```bash
# on the staging(-like) host: restore last night's production backup, then run the new release on it
scripts/restore.sh --yes <production-backup-dir>
scripts/deploy.sh --tag <new version>          # backup, maintenance, migrate, healthcheck, auto-rollback on failure
NXERP_BASE_URL=https://staging.example.test scripts/smoke.sh
```

Measure and write down: the migrate duration (this is the maintenance-window length), disk used by the backup, patches that ran
(`bench --site <site> console` -> `frappe.get_all("Patch Log")`, newest), and any warning in the migrate output. Production data in
staging must be handled as production data (access, deletion afterwards).

## 3. Decide the window and the abort point

- Window = rehearsal duration x 2 + health/smoke time. Announce it.
- **Abort point:** if `migrate.sh` fails, the site stays in maintenance mode and `deploy.sh` rolls back automatically (image + restore of
  the backup it just took). If a *successful* migration later proves wrong, the same rollback works until new data is written; after
  that you lose the data entered since (decide in advance whether that is acceptable, and how long you will watch before closing the window).
- Patches that delete or rewrite data need an explicit data-loss statement in the PR.

## 4. After

`healthcheck.sh` + `smoke.sh` pass; record in the release issue: version, window, durations, anything unexpected.

## What was tested (FACT, 2026-10-28)

`migrate.sh` (backup, maintenance on, `bench migrate`, cache clear, maintenance off, `healthcheck.sh`) ran to completion, exit 0, on the
dev-stack site `nxerp-e2e.localhost` (no schema change pending, so it proved the mechanics, not a real upgrade). The CI job
`upgrade-from-previous-tag` would exercise a real nxerp upgrade; it has never run and is skipped until the first release tag exists.
Upstream upgrades have not been rehearsed.
