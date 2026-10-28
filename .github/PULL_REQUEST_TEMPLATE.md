## What and why

<!-- One paragraph. Link the issue. The PR TITLE becomes the squash-merge commit: `type(scope): summary`
     (feat, fix, docs, chore, ci, test, refactor, perf, build, style, revert; max 100 characters). CI checks it. -->

## Type of change

- [ ] Feature / fix in the platform app (`nxerp/`)
- [ ] Access, routing or login (security-sensitive: security owners review, see CODEOWNERS)
- [ ] Version pin change (`deploy/versions.env`, `deploy/apps.json`)
- [ ] Deploy, CI or release tooling (`deploy/`, `.github/`)
- [ ] Docs / ADR / runbook only

## Scope check

- [ ] Touches only the area I own, or I have asked the owners of the other area (see CODEOWNERS and docs/governance/ownership.md)
- [ ] No app imports another app (the platform resolves apps; apps do not depend on each other)
- [ ] No secrets, customer data or personal data (use `user@example.test`-style fake data)
- [ ] Any new patch is idempotent and listed in `patches.txt`; any pin change updates `deploy/` and the matching ADR
- [ ] Access change? Enforced on the server (URLs and APIs), not only hidden in the UI

## Evidence

<!-- Paste what you ran and saw: test output, curl status codes, screenshots. "Should work" is not evidence.
     Say which checks ran locally and which only in CI. -->

## Migration and rollback

- [ ] No schema change / the migration is idempotent and was run twice on a copy
- [ ] A backup is taken before it runs in an environment (deploy/scripts/migrate.sh does this)

<!-- How to undo this if it misbehaves in an environment (revert, redeploy previous tag, restore backup). -->

## Docs

- [ ] User-visible or operator-visible change documented (README, runbook, architecture doc, ADR)
- [ ] `docs/PROGRESS.md` updated if a phase status changed
