# Runbook: incident response

**When to use:** production or staging misbehaves in a way users or monitoring notice: outage, wrong access (a user sees an app or data
they should not, a customer reaches Desk), suspected credential or data leak, failed deploy. **Status:** a template. No monitoring,
alerting or on-call rota exists, and the contacts below are placeholders for the owner to fill.

## Roles (fill in; see ownership.md)

| Role | Who | Contact |
| --- | --- | --- |
| Incident lead | [to be named] | [to be named] |
| Security lead | [to be named] | [to be named] |
| Release manager (deploy, rollback) | [to be named] | [to be named] |
| Business contact for customer communication | [to be named] | [to be named] |

## First 15 minutes

1. **Declare it**: open an issue titled `INCIDENT: <short>` (private repo, no personal data in it), note the time (UTC) and who leads.
2. **Classify**: availability (site down/slow), integrity (wrong data), confidentiality (access or data exposure), or deploy failure.
3. **Contain before you diagnose**, in this order of preference:
   - Access exposure: the kill-switch and recovery steps are in `docs/runbooks/login-recovery.md` (e.g. `nxerp_stock_login`); disable
     the affected account or role grant; for a customer-visible leak put the site in maintenance mode
     (`bench --site <site> set-maintenance-mode on` via `scripts/` helpers).
   - Bad release: roll back (`rollback.md`).
   - Credential suspected leaked: rotate it now (see below), then investigate.
4. **Preserve evidence**: take a backup (`backup.sh`), copy the web/worker logs (`docker compose logs --since 2h > incident-<date>.log`),
   Frappe's `Access Log`/`Error Log` records, and the platform denial log (`nxerp/audit.py`). Do not delete anything.

## Diagnose

```bash
scripts/healthcheck.sh                       # what is red
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs --tail 200 backend queue-worker scheduler proxy
```

## Rotate secrets (checklist)

Database root and site passwords, `Administrator` password (`bench --site <site> set-admin-password`), API keys/secrets of affected
users, SMTP password, `DEPLOY_SSH_KEY` and `REGISTRY_PULL_TOKEN` (GitHub Environment secrets), `HELPDESK_READ_TOKEN`, the site
`encryption_key` only with a plan (it makes encrypted fields unreadable). Invalidate sessions after a rotation.

## Communicate and close

- Customers/users: factual, what happened, what to do, no speculation; the business contact sends it.
- Personal-data exposure may carry legal notification duties: involve the owner and counsel; this runbook does not give legal advice.
- Close with a short post-incident review within a week: timeline, root cause, what detection would have caught it, actions with owners.
  Add a regression test or a check for every defect that reached production.

## Break-glass on GitHub

If `main` must change while CI or reviewers are unavailable, a repository admin relaxes exactly one protection setting, merges the
fix, restores the setting immediately, and logs who/when/why in the incident issue (`docs/governance/branch-protection.md`).

## What was tested

Nothing executes in this runbook. The recovery commands it points to (`login-recovery.md`) are the Phase 3 runbook; `docs/PROGRESS.md`
records that its kill-switch and break-glass steps were written but their browser tests had not passed on 2026-10-27, and the last
local browser run (2026-10-28, `/tmp/e2e-full.log`) still had failing tests, including an assertion in the `recovery` suite, so treat
those steps as unverified until the suite is green.
