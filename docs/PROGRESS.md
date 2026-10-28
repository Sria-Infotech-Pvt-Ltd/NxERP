# NXERP progress

Resume point for the next session. Update this file in every PR that changes phase status.

## Phase status

| Phase | Status |
| --- | --- |
| 1: Audit, research, ADRs, foundation | **Complete locally; not yet pushed** (see "Publishing") |
| 2: Platform access layer and server-side enforcement | **Complete locally; not pushed, no PR** (see "Phase 2") |
| 3: Unified login, launcher, routing | **Complete locally and browser-verified (55/55); not pushed, no PR** |
| 4: Helpdesk parity, CI/CD, release readiness, acceptance | **Built locally; nothing ran on GitHub; see `docs/acceptance/acceptance-report.md`** (9 BLOCKED-NEEDS-OWNER, most others PARTIAL) |

## Phase 4 (2026-10-28)

See `docs/acceptance/acceptance-report.md` (traceability matrix), `docs/parity/helpdesk-parity.md`, `docs/governance/owner-action-list.md`.
The Phase 3 "NOT verified" items below were run on 2026-10-28: pages, recovery, journeys and flows all pass now (55/55 browser tests across suites);
the full run found and fixed 5 real defects (login redirects bypassing the router, phone login clipped, missing alt/h1/skip link). Python: nxerp 211 OK, Helpdesk 577 OK.

## Phase 3 (2026-10-27): unified login, launcher, routing

Branch `phase-3/unified-experience` (off `phase-2/access-layer`) in `nxerp-platform`, plus Helpdesk branch
`feature/nxerp-platform-login` (login removed, title "Helpdesk", Apps menu). **No PR exists**: the GitHub account is read-only
on the repository (Phase 4 handles git). Nothing was pushed.

**Built:** `/login` in `nxerp` (kill-switch `nxerp_stock_login`), router `/nxerp/go`, launcher `/nxerp/apps`, friendly
`/nxerp/no-access`, tile overrides, "All applications" row for multi-app users, test-only third app, grant-migration dry run
(`nxerp/migration.py`), runbook, routes doc, ADR-004 amendment, browser harness in `e2e/`.

**Verified by execution (FACT):**

- `bench run-tests --app nxerp` on the dev site: **160 tests OK** (includes 19 routing tests with about 35 hostile redirect payloads,
  24 HTTP tests of login/router/launcher/kill-switch/third app, grant migration, the Phase 2 matrix). Helpdesk's own suite: **569 OK**.
  ruff, ruff format and bandit clean; `tools/check_architecture.py` OK. (The 160-test run was before the final two commits' small
  test edits; the migration tests were rerun alone and pass.)
- Browser (Chromium, fresh site `nxerp-e2e.localhost`, real login form): first-run wizard flow 4/4; Case 3 3/3; journeys 20 of 21
  (Cases 1 and 2, customer, deep links, expired session, logout, wrong password, disabled user, five tampered `redirect-to`
  payloads); flows: two-factor (OTP via captured mail), lockout, sign-up disabled, social not configured, forgot-password
  non-disclosure, and the emailed reset link up to setting and using a new password all passed.

**NOT verified (be clear before relying on this):**

- `e2e/pages.test.mjs` (screenshots at desktop and phone widths, accessibility checks) and `e2e/recovery.test.mjs` (kill-switch,
  admin-password reset, break-glass admin) were **written but never run**. `docs/evidence/phase3/` has **no screenshots** from them, and
  no accessibility defects were looked for or fixed. The runbook commands are the real Frappe commands but are untested here.
- Journeys: the one failure (the "All applications" row on a fresh site) was fixed by syncing the navbar item on install
  and was **not re-run**. Flows: single-use reset link and the email-link login were fixed after failing and **not re-run**
  (the first failed on my assertion, the second on a rate limit that the fixtures now raise).
- The ERPNext smoke test is inside the 160; no separate run. CI (`.github/workflows/ci.yml`) has never run on GitHub.

**Findings worth knowing (FACT):** controllers of hyphenated pages must be named with underscores, so Phase 2's `no-access.py`
never ran (fixed); Frappe caches site config per worker for up to 60 s (kill-switch takes up to a minute); Frappe's wizard gives
its owner every role, so the owner reaches the launcher; outgoing mail from Frappe is titled "Login To Frappe" (branding of emails is
not done); `bench execute` hides a function's real exception, so fixtures run with `python -m`.

**Dev-site incident (fixed):** ERPNext reloaded in a loop (`/desk` to `setup-wizard` to `/apps` to `/desk`). Cause: an early version of my
e2e fixtures marked the dev site's setup as complete without resetting Frappe's `desktop:home_page` default, which stays `setup-wizard` until the
wizard really finishes. Fixed by setting it to `workspace` (what a finished wizard sets); ERPNext then opened with no redirects. The fixtures
no longer touch the dev site (the browser suite uses its own fresh site). Not a platform-code bug, but a fresh site's setup-wizard UI was
not driven end to end by the tests (they finish the wizard through its API).

**Open decisions for the owner:** a User Invitation `redirect_to_path` is not validated by the platform; "Keep me signed in" is cosmetic;
Helpdesk's menu still links to Frappe support/docs; the grant migration heuristic over-suggests (a "Website Manager" role also has
ERPNext DocPerms), so review its dry-run output before applying.

**To finish Phase 3:** run `e2e/site.sh snapshot` once (done on the dev machine), then `e2e/run.sh` (about 25 minutes), read
`docs/evidence/phase3/`, fix what the pages suite finds, and rerun the two items above.

## Phase 2 (2026-10-27): access layer

Branch `phase-2/access-layer` (off `phase-1/foundation`) in `nxerp-platform`. Nothing upstream was modified.

- `nxerp/registry.py` (ERPNext, Helpdesk), `nxerp/access.py` (`get_user_apps`, `can_access_app`, `can_use_portal`, `resolve_landing`),
  `nxerp/enforcement.py` (auth hook gate, document and list hooks, response sanitiser), `nxerp/guard.py` (grant and lockout
  guard), `nxerp/api/access.py` (grant API), `nxerp/audit.py` (denial log), `nxerp/www/nxerp/no-access.*`.
- Tests: **115 passing** (`bench --site nxerp.localhost run-tests --app nxerp`); Helpdesk's own suite **566 passing, 0 failing**
  with the layer active; bandit and ruff clean.
- Docs: `docs/adr/ADR-003-amendment-1.md`, `docs/architecture/adding-an-app.md`, `docs/architecture/access-admin.md`,
  `docs/security/{shared-set,phase2-coverage,phase2-review,phase2-matrix}.md`.
- Bugs found by the tests and fixed: disabled accounts kept working on shared endpoints; customers received the assigned
  agent's email from Helpdesk's own ticket list; the last-administrator guard was blind on delete; DocType metadata leaked to
  every login.
- **Needs a decision (open):** with the layer on, existing users need the access roles (Helpdesk staff already have them
  through `Agent`/`Agent Manager`; ERPNext users need `NXERP Access: ERPNext`). Plan the grant migration before enabling it on a
  real site. Helpdesk's optional ERPNext integration no longer lets Helpdesk-only agents read ERPNext Customers (intended).
- **Phase 3 prerequisites:** launcher at `/nxerp/apps` and post-login router at `/nxerp/go` (ADR-004) using `resolve_landing`;
  login moved from the Helpdesk fork into `nxerp`; branding; setup-wizard-aware Administrator landing.

## Where the code lives (updated 2026-10-27)

One workspace folder, `frapper sria/`: `nxerp-platform/` (this repo, branch `phase-1/foundation`) and `helpdesk/` (Helpdesk fork, branch `feature/nxerp-palette`). `./deploy/dev/up.sh` runs both together. The earlier clone under `dev/NxERP` (outside the workspace) is an obsolete duplicate and can be deleted.

## Colour palette (completed 2026-10-27)

- Source of truth: `helpdesk/desk/src/theme/tokens/*.json`; `yarn theme:build` generates every output and syncs `nxerp-platform/nxerp/public/css/`.
- Committed on `feature/nxerp-palette` (5 commits). A blanket `build/` and `lib/` ignore rule had excluded the whole generator from git; fixed.
- The platform serves the Desk palette (`app_include_css`), so ERPNext/Framework Desk is themed from the platform, not from one app.
- Verified: `theme:check` (generated fresh, 384 frappe-ui tokens covered per mode, 99 contrast checks), `theme:audit` (no hard-coded colours), 5 platform tests + 3 Helpdesk theme tests, and screenshots in light and dark of the login, Helpdesk home/tickets and ERPNext Desk.
- **Extended 2026-10-27 (second pass):** server-rendered output (emails, welcome ticket, dashboard chart, report defaults, app shell, PWA manifest) now uses palette values from a generated `helpdesk/theme_tokens.py`; the audit covers backend files and `desk/index.html`/`vite.config.js`; `check-tracked` fails when any palette file is untracked or git-ignored (wired into `theme:check`, CI and pre-commit); generated files are pinned to LF.
- **Coverage measured, not assumed:** `tools/palette_scan.mjs` renders real pages in headless Chromium and flags any cool/violet colour that is not a status chip. Result on the dev site with seeded data: 0 leaks across all agent pages, all 15 Settings tabs and their New/Add forms, customer portal pages, login/forgot, and ERPNext Desk list/form/report pages. Remaining blue = NXERP/ERPNext logo marks (brand assets) and Frappe's own status pills.
- **Pushed to the company fork's `nxerp-stable` branch** (Frappe 15 line, frappe-ui beta.24): palette ported as 4 commits (see below).
- Remaining (Phase 2): move the token source out of the Helpdesk repo into the platform repo (the palette is platform-wide); recolour logo assets (brand decision); theme the portal/website pages when the login moves to the platform; Helpdesk Playwright theme spec not run.

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
4. **Palette branch** `feature/nxerp-palette` in `helpdesk/` is committed locally and not pushed; decide where it merges (the fork's `nxerp-stable` / `develop`) and push it with write access.
5. **PR #1** (`codex/nxerp-integration`, 1,163 files) is open on NxERP and untouched: close it or not.
6. **`/login` vs "v1/login"**: confirm `/login` (`/v1/login` is a 404 in Frappe 16).
7. **Licence** for `nxerp` (`hooks.py` says `Proprietary` as a placeholder) and **CODEOWNERS** team names (placeholders; teams must exist).
8. **Branch protection** on `main` and required reviews: repository admin must enable.
9. **Helpdesk app title "NXERP"** conflicts with "Helpdesk is never NXERP": confirm renaming to "Helpdesk" (Phase 2).
10. A separate local `NXERP/nxerp` app (never committed) contains another login override: decide whether it is input for Phase 2.

## Phase 2 prerequisites

1. Push `phase-1/foundation`, open the PR, get it reviewed, enable branch protection, create CODEOWNERS teams.
2. Rebase the Helpdesk customisations onto upstream `v1.31.0` in the company fork; re-pin `deploy/apps.json`; rebuild from scratch (`down -v`, `up.sh -d`) and re-run the suites.
3. Push and merge the palette branch in the company fork (committed locally; see "Colour palette").
4. (Done 2026-10-27) The amended bootstrap was re-run from empty volumes and passed.
5. Investigate the 7 `Throttled` Helpdesk test errors on a fresh site; decide whether Helpdesk tests run on a Helpdesk-only site in CI.
6. Spikes to prove before building: `auth_hooks` sees the right user for cookie, token and socket requests and can return 403 before dispatch; one landing target converges both redirect engines; Administrator first-run (setup wizard) is preserved.
7. Run the remaining unverified checks (realtime, private files/print, `before_request` ordering, 2FA on non-password routes) and extend `tools/access_baseline.sh` into automated Phase 2 acceptance tests: one per row of the coverage table.
8. Decide the Helpdesk-to-ERPNext Customer bridge policy (mirrored User Permissions/DocShares).
9. Review `desk_access` of the Agent roles and the implicit-role default (`desk_access = 1`).
10. Build real CI/CD: GitHub-hosted run of `ci.yml`, a registry, staging, secrets management. None of that exists yet.

## Publishing

Not pushed. The branch is local at `<local clone>` (`phase-1/foundation`). See the final report for exact steps.
