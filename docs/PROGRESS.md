# NXERP progress

Resume point for the next session. Update this file in every PR that changes phase status.

## Phase status

| Phase | Status |
| --- | --- |
| 1: Audit, research, ADRs, foundation | **Complete locally; not yet pushed** (see "Publishing") |
| 2: Login, launcher, access, routing | Not started |

## Phase 1: what exists (evidence in `docs/audit/bootstrap-evidence.md`)

- Audit: `docs/audit/helpdesk-audit.md` (enhancements (a)-(f): none clearly IMPLEMENTED; (a) ABSENT, (b) ABSENT, (c) PARTIAL, (d) PARTIAL, (e) ABSENT on create, (f) PARTIAL)
- Research: `docs/research/frappe-access-and-routing.md` + two parts, including the surface coverage table
- ADR-001 to ADR-006, all Accepted
- Platform app `nxerp` (scaffold only, 4 tests passing), `deploy/` pins + dev stack, `tools/` checks, governance files, minimal CI
- One command (`./deploy/dev/up.sh -d`) brought up frappe + payments + erpnext + telephony + helpdesk + nxerp on one site in 408 s from empty volumes

## Decisions made (see ADRs)

- DECISION ADR-001: polyrepo; repo root is the `nxerp` app; Helpdesk is a company fork; Frappe/ERPNext are pinned upstream tags
- DECISION ADR-002: Frappe 16.53.0, ERPNext 16.52.1, Python 3.14, Node 24, MariaDB 11.8, Redis 8.6; Helpdesk target = upstream v1.31.0 plus the company commits (clean cherry-pick verified); interim pin = fork commit 1c6981cc5
- DECISION ADR-003: hybrid (roles stay the data source of truth; one thin resolver plus an `auth_hooks` app gate in `nxerp`)
- DECISION ADR-004: `/login`, `/nxerp/go`, `/nxerp/apps`, `/nxerp/no-access`, `/helpdesk/home`, `/desk` (`/app` redirects)
- DECISION ADR-005: platform owns login/launcher/branding; apps never import each other; enforced by `tools/check_architecture.py`
- DECISION ADR-006: Docker Compose dev stack

## Facts the next phase must respect (all verified on the dev site)

- `/desk` is open to every System User; ERPNext data is protected only by DocType roles
- Every login currently gets `home_page: "helpdesk"` (Helpdesk sets `Portal Settings.default_portal_home`)
- `/apps` is a redirect to `/desk` in Frappe 16; there is no `/apps` page
- Frappe has no app/module gate in the request path; module blocking is navigation-only
- DocType metadata endpoints answer any logged-in user

## Open items for the owner (blocking or needing a decision)

1. **Push access**: the GitHub account on this machine has READ on `Sria-Infotech-Pvt-Ltd/NxERP`. Grant write, or push from an account with access (steps below).
2. **Commit author**: local commits use the machine's global git identity (a personal name/email). Decide whether to amend before pushing (`git rebase -r --root --exec 'git commit --amend --reset-author --no-edit'` after setting `user.name`/`user.email` locally; local branch only).
3. **Helpdesk fork ownership**: it lives under `Sriainfotech`, the company org is `Sria-Infotech-Pvt-Ltd`.
4. **Uncommitted palette/theme work** in `helpdesk/` (43 modified + 8 untracked files): not in any commit, so not in the reproducible build; the partial-commit risks are in the audit.
5. **PR #1** (`codex/nxerp-integration`, 1,163 files) is open on NxERP and untouched: close it or not.
6. **`/login` vs "v1/login"**: confirm `/login` (`/v1/login` is a 404 in Frappe 16).
7. **Licence** for `nxerp` (`hooks.py` says `Proprietary` as a placeholder) and **CODEOWNERS** team names (placeholders; teams must exist).
8. **Branch protection** on `main` and required reviews: repository admin must enable.
9. **Helpdesk app title "NXERP"** conflicts with "Helpdesk is never NXERP": confirm renaming to "Helpdesk" (Phase 2).
10. A separate local `NXERP/nxerp` app (never committed) contains another login override: decide whether it is input for Phase 2.

## Phase 2 prerequisites

1. Push `phase-1/foundation`, open the PR, get it reviewed, enable branch protection, create CODEOWNERS teams.
2. Rebase the Helpdesk customisations onto upstream `v1.31.0` in the company fork; re-pin `deploy/apps.json`; rebuild from scratch (`down -v`, `up.sh -d`) and re-run the suites.
3. Commit the palette work in the fork (or drop it) so the build includes it.
4. Re-run the amended bootstrap from empty volumes (the `bench setup requirements --dev` step was verified by running the command in the live container, not from scratch).
5. Investigate the 7 `Throttled` Helpdesk test errors on a fresh site; decide whether Helpdesk tests run on a Helpdesk-only site in CI.
6. Spikes to prove before building: `auth_hooks` sees the right user for cookie, token and socket requests and can return 403 before dispatch; one landing target converges both redirect engines; Administrator first-run (setup wizard) is preserved.
7. Run the remaining unverified checks (realtime, private files/print, `before_request` ordering, 2FA on non-password routes) and extend `tools/access_baseline.sh` into automated Phase 2 acceptance tests: one per row of the coverage table.
8. Decide the Helpdesk-to-ERPNext Customer bridge policy (mirrored User Permissions/DocShares).
9. Review `desk_access` of the Agent roles and the implicit-role default (`desk_access = 1`).
10. Build real CI/CD: GitHub-hosted run of `ci.yml`, a registry, staging, secrets management. None of that exists yet.

## Publishing

Not pushed. The branch is local at `<local clone>` (`phase-1/foundation`). See the final report for exact steps.
