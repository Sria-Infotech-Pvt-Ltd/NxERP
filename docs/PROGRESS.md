# NXERP progress

Resume point for the next session. Update this file in every PR that changes phase status.

## Phase status

| Phase | Status |
| --- | --- |
| 1: Audit, research, ADRs, foundation | **Complete locally; not yet pushed** (see "Publishing") |
| 2: Platform access layer and server-side enforcement | **Complete locally; not pushed, no PR** (see "Phase 2") |
| 3: Unified login, launcher, routing | **Complete locally and browser-verified (55/55); not pushed, no PR** |
| 4: Helpdesk parity, CI/CD, release readiness, acceptance | **Built locally; nothing ran on GitHub; see `docs/acceptance/acceptance-report.md`** (9 BLOCKED-NEEDS-OWNER, most others PARTIAL) |

## Hybrid database programme, Phase 0: identity, ecosystem registry, worktrees (2026-11-18)

Branch `hybrid/phase-0-foundation` (from `feat/nxdesk-onboarding` at `8a4910610`). Not pushed, no PR. Documentation only: no application code, deployment configuration or production was touched.

**Done:** NXDESK shown as the umbrella in `README.md`, `docs/README.md`, `docs/architecture/overview.md`, `CONTRIBUTING.md` and the platform README (titles and intro lines only; technical identifiers unchanged);
planning registry for existing, planned and proposed applications in `docs/ecosystem/` (README plus `application-registry.md`); branch and worktree rules in `docs/governance/hybrid-programme-workflow.md`
(no `hybrid/track-*` branches, stacked phase branches, merge commits, one ADR-009 owner).

**Left alone on purpose (recommendations, not changes):** `hooks.py` `app_description`, `apps/nxerp_platform/pyproject.toml` description, the Frappe module name "NXERP Platform" (`modules.txt`, two DocType JSON files, one test),
the Dockerfile image label, the issue-template text, and historical documents (ADR text, audit, research, evidence), which ADR-008 says to read as "NXDESK platform". `README.md` still describes the old two-folder
workspace (`frapper sria/`), which ADR-007 superseded: a topology fix, separate from naming.

**Open for the owner:** "Royal HRMS" vs "AIRA HRMS" (A13), scope and priority of Project Management, Budget Management and CRM, push access for the branch chain.

## Public site design pass (2026-11-13)

Same branch (`feat/nxdesk-onboarding`). Owner request: the entry page looked flat and needs more modules. Added: grouped header menus (Products, Platform, Solutions, Company; a menu panel on small screens), a richer footer,
a deeper home page (capability chips, products, solutions by team, how it works, closing band), seven information pages (`/platform`, `/security`, `/solutions`, `/roadmap`, `/company`, `/partners`, `/get-in-touch`) driven by
`nxerp/public_catalog.py`, and **AIRA HRMS** as an announced product ("Coming soon", logo supplied by the owner in `public/images/`; not installed, no sign-up). The structure of the reference site was used only as inspiration
(grouped nav); all copy and design are our own, since that site's content is licensed CC-BY-NC-SA. DECISION (owner instruction): an announced product may be shown if clearly labelled; CLAUDE.md records the rule.
Page copy makes no customer, award, certification or uptime claim (a test checks for such words).

## NXDESK plan, Phase 2: accounts, get-started, onboarding (2026-11-12 / 13)

Branch `feat/nxdesk-onboarding`, **branched from `feat/nxdesk-public-site` (Phase 1), because Phase 1 is not merged into `develop`**. Not pushed, no PR. Merge Phase 1 first, then this.

**Built:** `/signup`, `/get-started`, `/welcome/<key>` (wizard and pending view), the no-access "Request access" button; DocTypes `NXERP Access Request` and `NXERP Onboarding`;
`nxerp/onboarding.py` + `api/account.py`, `api/onboarding.py`, `api/access_request.py`; router honours `/welcome/<key>`; `install.sync_signup_setting` + patch `enable_signup_when_configured`;
runbook `docs/runbooks/onboarding.md`; routes, code map and UI contract updated.

**Facts found (Step 0):** Website Settings `disable_signup` was 1; Portal Settings `default_role` is **HD Customer**, which Frappe's `sign_up` adds to every signup (a Helpdesk portal role), so the wrapper removes it
unless the product's policy is `open_portal`; Frappe's `sign_up` returns "Already Registered" for a known email (the wrapper hides that), creates a Website User, and `mute_emails` = 1 on the dev site drops mail
(runbook section 4). Helpdesk `open_portal` needs a Contact and HD Customer record (Helpdesk internals), so **Helpdesk stays `request_access`**; `open_portal` is implemented generically (portal role only) and unit-tested with a patched registry.

**Decisions:** approving also gives the `Desk User` role (staff access ignores Website Users, and self-signed accounts are Website Users); product roles stay the administrator's call.
The login stylesheet is untouched: the new forms reuse its markup classes. Browser test `onboarding.test.mjs` was run against the dev site (not via `run.sh`).

**Verified by execution (FACT):** `onboarding.test.mjs` 7/7 (signup closed by default; Products to Get started to Create account to verification link read from a captured email to set password to `/welcome/helpdesk`
to wizard to request; exactly one Pending request and the gate still sends the user to `/nxerp/no-access`; the Request access button; an administrator approves through `decide`, deciding twice changes nothing, and the
user opens `/helpdesk`; 320px overflow, labels and Tab focus on every new page; screenshots at four widths in light and dark in `docs/evidence/ui/phase2/`). Python: `test_onboarding` 28, `test_onboarding_pages` 17, routing 31, scaffold, site assets,
registry and public site all OK; the full suite (259 tests) before the last two small test fixes showed the same 4 failures as the Phase 1 baseline plus one test of mine that was then fixed (a CSRF token only exists once a page issued one).
Login and no-access (without `?app`) are pixel-identical to baseline (`phase2/baseline` vs `phase2/after`). Rate limit: 12 calls to `sign_up` gave `403` x10 then `429` x2.
Not re-run after the final edits: the whole Python suite once more, the Phase 1 browser suite, `run.sh`. `submit` and `save_step` limits (10 and 60 per hour) are by decorator and were hit by accident, not tested on purpose.

## NXDESK plan, Phase 1: public site (2026-11-11 / 12)

Branch `feat/nxdesk-public-site` (off `develop`). Not pushed, no PR. Owner decisions D1 to D5 are in ADR-008 and `docs/design/ui-contract.md`.

**Built:** ADR-008 (NXDESK umbrella, NXERP / Sria Helpdesk display names; technical names unchanged); `nxerp/branding.py` (one place for names, logo paths, support link; typographic wordmark until logo files exist);
registry presentation fields and copy limits; public Home (`/` for guests), `/products`, `/products/<key>` (`nxerp/public_site.py`, `www/nxerp/home|products|product.*`, `templates/includes/nxdesk/`, `public/css/nxerp-site.css`);
`docs/design/ui-contract.md`; routes doc. Nothing creates an account or grants access.

**Decisions:** only a guest's `/` is re-pointed (hook `get_website_user_home_page`); signed-in users keep Frappe's answer so the router still decides. Kill-switch `nxerp_keep_login_home`. Registry gained `display_name` (not in the brief's field list) so the launcher keeps "ERPNext" / "Helpdesk" unchanged while public pages say "NXERP" / "Sria Helpdesk".

**Open (not done on purpose):** `/get-started` is a 404 until Phase 2 (the "Get started" buttons and the three steps point at it); the launcher tiles still say ERPNext / Helpdesk; the login still carries NXERP logo images and copy; the favicon is the existing NXERP one (placeholder); a signed-in non-holder sees "Get started" (request-access is Phase 2).

**Evidence:** `docs/evidence/ui/phase1/` (`baseline/`, `after/`, `screens/`, `contrast.json`, `baseline-tests.md`). Baseline tests had 4 pre-existing failures (see `baseline-tests.md`). After Phase 1: `bench run-tests --app nxerp` ran 210 + 17 tests with the same 4 failures and nothing new; `site.test.mjs` 10/10 on the dev site (not via `run.sh`); the other browser suites were not re-run. Launcher, no-access and login screenshots are pixel-identical to baseline (`after/` vs `baseline/`).
## Add Task form: Department and Designation removed (2026-11-05)

On `develop` (commit `98029e2`). The local `nxerp-develop` stack runs image `…-dirty.9` with this change (deployed
2026-11-05, see below). Changed: `apps/helpdesk/hd-frontend/src/pages/tasks/NewTaskDialog.vue`, `apps/helpdesk/docs/tasks.md`.

- Department and Designation removed from the form (the `HD Task` fields and existing records are unchanged; the form never
  sent them). Select Employee is disabled ("Select project first") until a project is chosen; changing the project clears
  the milestone and the employee. The employee list is still the full HRMS list; each option shows only the employee's
  name (the HRMS department/designation caption was removed; the id is appended only when two names are the same).
- DECISION (owner, 2026-11-05): no project/milestone-based employee filtering yet. FACT: no assignment data exists for it
  (HD Task Project has only `project_name`, HD Task Milestone only `milestone_name`/`project`, PBT has no team, HRMS shape unverified).
- Verified (FACT): `npm run build` of the Helpdesk frontend passes (exit 0, isolated throwaway container; only the usual
  chunk-size warning); prettier reports one pre-existing line only; `save()` and the backend are unchanged.
- Pending tests: task creation with an employee (needs reachable HRMS, PBT or a local HD Task Project; the develop site has
  0 projects/tasks/employees); `helpdesk.api.test_task*` on a throwaway site.
- Deployed `…-dirty.8` (Department/Designation removed) on 2026-11-05; no migration (all 109 schema files equal to dirty.5).
  Browser check found the Employee/Freelancer switch and Select Employee rendering nothing — present since `08a0a92`, also in
  dirty.5: the form used the pre-1.0 frappe-ui API (`TabButtons :buttons`, local `Autocomplete.vue` on Popover `#target`)
  while the installed frappe-ui is `1.0.0-rc.1` (`:options`, Popover `#trigger`). Fixed in `NewTaskDialog.vue`:
  `:options`, and frappe-ui's own `Combobox` (as in `TimezoneControl.vue`) with name-or-id search. `Autocomplete.vue` is now
  unused (left in place). Image `…-dirty.9` (`341eac484905`) built; its frontend passed 36/36 browser checks against the live
  site with dirty.9 assets substituted in the browser only and mocked lookup data (no DB writes, 0 tasks).
- **Deployed `…-dirty.9` on 2026-11-05 06:45 UTC** (backup `20261105T064347Z` first; only the 5 app containers recreated;
  MariaDB/Redis/nginx, volumes and `nxerp-taskdev` unchanged; no migration, schema equal to dirty.8). The same 36 browser
  checks pass on the deployed site without substitution. Rollback: `IMAGE=…-dirty.8`, `docker compose up -d`.
  Still untested: saving a task with an employee (needs reachable HRMS or real data).
- Incident (fixed): a check build wrote into the live backend container's `helpdesk/public/desk/` and
  `www/helpdesk/index.html` (the Vite config fixes its outDir); both were restored from the `dirty.5` image, checksums equal.
  Do not run `vite build` against the container's app tree to test; use a full copy or a rebuild.

## Local develop stack and Frappe 16 fixes (2026-11-04)

Committed and pushed to `develop` on 2026-11-05 (the seven commits after `35a74d0`). New stack `deploy/docker/compose/develop/` (project `nxerp-develop`, port 8012, site
`nxerp.localhost`, image from `deploy/docker/Dockerfile`). Verified by execution (FACT) in Chrome, by HTTP and in logs:

- Image build fixed: bench 5.31 rewrites `sites/apps.txt` in directory order; `install_apps.sh` restores apps.json order.
- Image defaults fixed: backend CMD is `application_with_statics()` (plain WSGI serves no `/assets`), HEALTHCHECK sends
  the site name, entrypoint refreshes the image's generated `sites/` files, sets `webserver_host`/`webserver_port`
  (socket auth callback) and drops the cached `assets_json` (stale map = 404 on every bundle after an image change).
- nginx template: upstreams re-resolved via Docker DNS; `/files/` served from the read-only sites volume (missing
  file 404, not Frappe's 500); dot-segment URIs refused (400). Helpdesk `socket.ts` uses the page origin, not port 9000.
- Login on Frappe 16.53.0: submit button lost `btn-primary btn-login` (restored by the page script), card shrank below
  its content on short viewports (`flex: none`), loading/error states follow `aria-busy` and the error banner,
  "Forgot password?" sits under the button; "Keep me signed in" removed.
- Tasks API: `get_tasks` / `get_task_counts` used string SQL in `fields` (Frappe 16 rejects it): version-aware `COUNT_NAME`.
- NOT verified: `staging-like/` was never started (config validated, `nginx -t` passed); Helpdesk/Tasks Python test suites
  were not run on this site; password reset email cannot be delivered (no outgoing Email Account); ERPNext setup wizard
  not completed (needs real company data from the owner); PBT/HRMS keys not configured.
## Retire the bare `/desk` gateway (2026-11-02)

Branch `feature/retire-bare-desk-gateway`. `/nxerp/apps` is the only gateway; ERPNext's tile now targets `/desk/home` and an exact
`GET /desk` is redirected to the user's router destination (ADR-004 amendment 1). `/desk/*` is untouched. Kill-switch:
`nxerp_keep_desk_root`. Not committed, no PR. Verified so far: Python suites against a fresh server (see the session report); the browser journeys did not run (e2e site fixture failed).

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
(`apps/nxerp_platform/nxerp/migration.py`), runbook, routes doc, ADR-004 amendment, browser harness in `apps/nxerp_platform/browser-tests/`.

**Verified by execution (FACT):**

- `bench run-tests --app nxerp` on the dev site: **160 tests OK** (includes 19 routing tests with about 35 hostile redirect payloads,
  24 HTTP tests of login/router/launcher/kill-switch/third app, grant migration, the Phase 2 matrix). Helpdesk's own suite: **569 OK**.
  ruff, ruff format and bandit clean; `scripts/check_architecture.py` OK. (The 160-test run was before the final two commits' small
  test edits; the migration tests were rerun alone and pass.)
- Browser (Chromium, fresh site `nxerp-e2e.localhost`, real login form): first-run wizard flow 4/4; Case 3 3/3; journeys 20 of 21
  (Cases 1 and 2, customer, deep links, expired session, logout, wrong password, disabled user, five tampered `redirect-to`
  payloads); flows: two-factor (OTP via captured mail), lockout, sign-up disabled, social not configured, forgot-password
  non-disclosure, and the emailed reset link up to setting and using a new password all passed.

**NOT verified (be clear before relying on this):**

- `apps/nxerp_platform/browser-tests/pages.test.mjs` (screenshots at desktop and phone widths, accessibility checks) and `apps/nxerp_platform/browser-tests/recovery.test.mjs` (kill-switch,
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

**Open decisions for the owner:** a User Invitation `redirect_to_path` is not validated by the platform; "Keep me signed in" was cosmetic (removed 2026-11-04);
Helpdesk's menu still links to Frappe support/docs; the grant migration heuristic over-suggests (a "Website Manager" role also has
ERPNext DocPerms), so review its dry-run output before applying.

**To finish Phase 3:** run `apps/nxerp_platform/browser-tests/site.sh snapshot` once (done on the dev machine), then `apps/nxerp_platform/browser-tests/run.sh` (about 25 minutes), read
`docs/evidence/phase3/`, fix what the pages suite finds, and rerun the two items above.

## Phase 2 (2026-10-27): access layer

Branch `phase-2/access-layer` (off `phase-1/foundation`) in `nxerp-platform`. Nothing upstream was modified.

- `apps/nxerp_platform/nxerp/registry.py` (ERPNext, Helpdesk), `apps/nxerp_platform/nxerp/access.py` (`get_user_apps`, `can_access_app`, `can_use_portal`, `resolve_landing`),
  `apps/nxerp_platform/nxerp/enforcement.py` (auth hook gate, document and list hooks, response sanitiser), `apps/nxerp_platform/nxerp/guard.py` (grant and lockout
  guard), `apps/nxerp_platform/nxerp/api/access.py` (grant API), `apps/nxerp_platform/nxerp/audit.py` (denial log), `apps/nxerp_platform/nxerp/www/nxerp/no-access.*`.
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

One workspace folder, `frapper sria/`: `nxerp-platform/` (this repo, branch `phase-1/foundation`) and `helpdesk/` (Helpdesk fork, branch `feature/nxerp-palette`). `./deploy/bootstrap/up.sh` runs both together. The earlier clone under `dev/NxERP` (outside the workspace) is an obsolete duplicate and can be deleted.

## Colour palette (completed 2026-10-27)

- Source of truth: `helpdesk/desk/src/theme/tokens/*.json`; `yarn theme:build` generates every output and syncs `nxerp-platform/nxerp/public/css/`.
- Committed on `feature/nxerp-palette` (5 commits). A blanket `build/` and `lib/` ignore rule had excluded the whole generator from git; fixed.
- The platform serves the Desk palette (`app_include_css`), so ERPNext/Framework Desk is themed from the platform, not from one app.
- Verified: `theme:check` (generated fresh, 384 frappe-ui tokens covered per mode, 99 contrast checks), `theme:audit` (no hard-coded colours), 5 platform tests + 3 Helpdesk theme tests, and screenshots in light and dark of the login, Helpdesk home/tickets and ERPNext Desk.
- **Extended 2026-10-27 (second pass):** server-rendered output (emails, welcome ticket, dashboard chart, report defaults, app shell, PWA manifest) now uses palette values from a generated `helpdesk/theme_tokens.py`; the audit covers backend files and `desk/index.html`/`vite.config.js`; `check-tracked` fails when any palette file is untracked or git-ignored (wired into `theme:check`, CI and pre-commit); generated files are pinned to LF.
- **Coverage measured, not assumed:** `scripts/palette_scan.mjs` renders real pages in headless Chromium and flags any cool/violet colour that is not a status chip. Result on the dev site with seeded data: 0 leaks across all agent pages, all 15 Settings tabs and their New/Add forms, customer portal pages, login/forgot, and ERPNext Desk list/form/report pages. Remaining blue = NXERP/ERPNext logo marks (brand assets) and Frappe's own status pills.
- **Pushed to the company fork's `nxerp-stable` branch** (Frappe 15 line, frappe-ui beta.24): palette ported as 4 commits (see below).
- Remaining (Phase 2): move the token source out of the Helpdesk repo into the platform repo (the palette is platform-wide); recolour logo assets (brand decision); theme the portal/website pages when the login moves to the platform; Helpdesk Playwright theme spec not run.

## Phase 1: what exists (evidence in `docs/audit/bootstrap-evidence.md`)

- Audit: `docs/audit/helpdesk-audit.md` (enhancements (a)-(f): none clearly IMPLEMENTED; (a) ABSENT, (b) ABSENT, (c) PARTIAL, (d) PARTIAL, (e) ABSENT on create, (f) PARTIAL)
- Research: `docs/research/frappe-access-and-routing.md` + two parts, including the surface coverage table
- ADR-001 to ADR-006, all Accepted
- Platform app `nxerp` (scaffold only, 4 tests passing), `deploy/` pins + dev stack, `scripts/` checks, governance files, minimal CI
- One command (`./deploy/bootstrap/up.sh -d`) brought up frappe + payments + erpnext + telephony + helpdesk + nxerp on one site in 408 s from empty volumes

## Decisions made (see ADRs)

- DECISION ADR-001: polyrepo; repo root is the `nxerp` app; Helpdesk is a company fork; Frappe/ERPNext are pinned upstream tags
- DECISION ADR-002: Frappe 16.53.0, ERPNext 16.52.1, Python 3.14, Node 24, MariaDB 11.8, Redis 8.6; Helpdesk target = upstream v1.31.0 plus the company commits (clean cherry-pick verified); interim pin = fork commit 1c6981cc5
- DECISION ADR-003: hybrid (roles stay the data source of truth; one thin resolver plus an `auth_hooks` app gate in `nxerp`)
- DECISION ADR-004: `/login`, `/nxerp/go`, `/nxerp/apps`, `/nxerp/no-access`, `/helpdesk/home`, `/desk` (`/app` redirects)
- DECISION ADR-005: platform owns login/launcher/branding; apps never import each other; enforced by `scripts/check_architecture.py`
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
7. Run the remaining unverified checks (realtime, private files/print, `before_request` ordering, 2FA on non-password routes) and extend `scripts/access_baseline.sh` into automated Phase 2 acceptance tests: one per row of the coverage table.
8. Decide the Helpdesk-to-ERPNext Customer bridge policy (mirrored User Permissions/DocShares).
9. Review `desk_access` of the Agent roles and the implicit-role default (`desk_access = 1`).
10. Build real CI/CD: GitHub-hosted run of `ci.yml`, a registry, staging, secrets management. None of that exists yet.

## Publishing

Not pushed. The branch is local at `<local clone>` (`phase-1/foundation`). See the final report for exact steps.

## Restructure (2026-10-28)

Repository reorganised into `apps/`, `deploy/`, `docs/`, `scripts/` (ADR-007). Follow-ups: split the flat platform modules into
`access/ login/ launcher/ branding/` packages once tests prove the hook paths (architecture rule 4); port Helpdesk's workflows to the
root `.github/`; run the new CI and the production image build on GitHub; decide the licence mix; the "Assignee follows Team" work lives
in a patch outside the repository.

## Hybrid database programme, Phase 1: decide, measure, harden (2026-11-18)

Branch `hybrid/phase-1-harden` (from `feat/nxdesk-onboarding` at `8a4910610`; the prompt names `feat/nxdesk-app-login`, which does not exist here: ASSUMPTION, same tip as the intended base). Work packages 1A, 1B, 1C committed; verified on the fake-data `nxerp-scratch` stack only. No production access: GATE G1 is still open.

**Verified (FACT, run on scratch, 2026-11-18):**
- `bash -n` and `shellcheck -x` pass on `scripts/isolation_audit.sh`, `deploy/scripts/backup.sh`, `deploy/scripts/restore.sh`; `docker compose ... config -q` exits 0; `scripts/check_architecture.py` OK.
- `scripts/isolation_audit.sh all` on scratch: one database-level grant, no global privilege, no GRANT OPTION, root password absent from backend/websocket/queue-worker/scheduler, one published service (proxy). **FAIL `grants-host-not-wildcard`**: the site login's host is `%` (finding, to record in `measurements.md` for the real site). 6 apps share the single login (the problem, measured).
- Check 1.1: plain backup = folder with dump, 2 file archives, `site_config_backup.json`, `MANIFEST`, `SHA256SUMS` (809 tables). Encrypted run = one `.tar.age` plus `.sha256`, no plain folder, last stdout line is the `.tar.age` path.
- Check 1.2: wrong key: `age: error: no identity matched any of the recipients`; `restore.sh` with the wrong key exits 1 before changing anything.
- Check 1.3: restore from `.tar.age` ran checksum, decrypt, safety backup, maintenance mode, `bench restore`: 44 s. First run exited 1 only because scratch had its scheduler disabled (health check FAIL scheduler); after `bench enable-scheduler` the health check passes.
- Check 1.5: `root-env` PASS for all four services; `docker inspect` shows `[no-new-privileges:true]`.

**Fixed while verifying:** `backup.sh` verified archives with `tar -tf "$f"`; GNU tar on Git Bash for Windows reads `C:` as a remote host and the backup aborted. Now `tar -tf - < "$f"` (portable). Existing behaviour elsewhere unchanged.

**Not done (needs the owner):** GATE G1 (assumptions A1 to A13 and `GO READ PROD`), runbook steps 1.3 to 1.10 against a real production copy, GATE G1a (key saved: the key generated for the drill was a throwaway, not the production key), GATE G1b (nightly cron), ADR-009 acceptance, `measurements.md` results.

**Owner decisions (2026-11-18):** assumptions A1 to A13 accepted as defaults (ADR-009 stays Proposed until the owner sets Accepted). **No production host exists yet** (owner: "NO PROD YET"): runbook steps 1.3 to 1.10 against a real production copy and the nightly cron line (G1b) are deferred until one exists; `GO READ PROD` / `GO INSTALL BACKUP JOB` were given but have nothing to act on. Real backup key pair generated outside git (public key `age1ttd9...`, private key on the owner's machine only); G1a (`KEY SAVED`) pending.

## Phase 1 update: production measured (2026-11-19)

Owner gave `GO READ PROD` for the live Hostinger host (read-only, counts and grants only, nothing copied off it, no install). **FACT:** production is bare-metal systemd with no Docker; NXERP and Helpdesk are two separate Frappe sites on separate benches with separate databases and `localhost`-only logins (not one shared site); MariaDB 10.11 not 11.8; at least 8 unrelated applications share the host; `tabCustomer` is absent from the Helpdesk database; NXERP site has 0 customers, Helpdesk has 53 tickets. Results are in `docs/architecture-isolation/measurements.md`; assumptions A1 and A2 corrected in ADR-009 and the blueprint (ADR-009 stays Proposed). **Not done:** nightly backup job (the Docker `backup.sh` does not fit; a bare-metal `mysqldump` plus `age` design is to be shown to the owner first), MariaDB root-level checks (`sudo` needs a password), Redis exposure, firewall rules, backups already on the host.

## Hybrid database programme, Phase 2A: contracts, registry, lint (2026-11-19)

Branch `hybrid/phase-2-contracts` (fast-forwarded to `hybrid/phase-1-harden` at `8309269ad`, then new commits). Not pushed yet. Files and tests only: no hooks, no database, no change to Helpdesk or ERPNext.

**Done:** `nxerp/shared/contract_schema.json`; seven contracts in `nxerp/shared/contracts/` (customer, contact, user_ref, org_unit, employee_ref, project_ref, ticket_summary); `nxerp/shared/registry.py` (no frappe import); `scripts/check_contracts.py` (rules C1 to C8, stdlib, reads the app registry with `ast`); `nxerp/tests/test_shared_contracts.py` (27 tests); CI step in `ci.yml`; `docs/architecture/shared-data-contracts.md`.

**FACT (run 2026-11-19):** `python -I scripts/check_contracts.py` prints PASS for 7 contracts; 27 unittest tests pass; `ruff check` clean; `check_architecture.py` OK. The lint rejects `tax_id`, a second contract for an entity with another owner, and class S3 (negative tests). **UNVERIFIED:** the CI step has not run on GitHub; the existing Frappe site test suites were not run (no site in this window).

**Decisions to confirm at GATE G2:** (1) `user_ref` owner is `identity`, status `planned` (no identity site exists; each app has its own User table), not an installed app; (2) `customer.display_name` is class S2 (an Individual's name), not S1; (3) `app_keys_granted` renamed `apps_granted` because the lint refuses the fragment "key"; (4) only installed apps are listed as consumers (planned consumers are added when those apps exist); (5) `ticket_summary.customer_id` needs a mapping HD Customer to ERPNext Customer, which is empty for customers with no ERPNext record, and `org_unit.disabled` has no source field (Company has none on the live site); both are marked `verify`.

## Hybrid database programme, Phase 2B: shared model, envelope, ADR-009 (2026-11-19)

Owner replied `APPROVE CATALOGUE` at GATE G2 (the seven contracts and the five judgement calls in the 2A entry stand). Files and tests only; no database server started, no account created, no Frappe code in `shared_service`.

**Done:** `nxerp/shared_service/schema/0001_shared_model.sql` (7 entity tables generated from the contracts plus `sync_cursor`, `sync_dead_letter`, `consumer_grant`, `read_audit`, `contract_registry`; utf8mb4; no foreign keys; no accounts or grants); `schema/generate_columns.py`; `nxerp/shared/envelope_schema.json` and `registry.event_problems`; tests `test_schema_matches_contracts.py` (14) and `test_envelope.py` (11); ADR-009 extended (corrected earlier rejection, triggers to reconsider, 11 unresolved items; status still Proposed); contracts guide extended.

**FACT (run 2026-11-19):** 27 + 14 + 11 unittest tests pass; `ruff check` clean on `shared`, `shared_service`, `scripts/check_contracts.py`; `check_contracts.py` PASS for 7; `check_architecture.py` OK; no `frappe` import under `shared` or `shared_service`. Check 2.2: a contract field with no column, a column with no contract field, a wrong type and a missing table are each named by the schema test. **UNVERIFIED:** the SQL has not been executed on MariaDB 11.8 (command for Phase 4: `mariadb --user=<migration account> < 0001_shared_model.sql` on an empty scratch server); CI has not run on GitHub; the existing Frappe site suites were not run.

**Design notes:** no credential column in `consumer_grant` (where the per-app credential hash lives is a Phase 4 decision); the SQL header documents the idempotent upsert guarded by `(source_modified, last_seq)`.

**Waiting:** GATE G2b (owner replies `ACCEPT ADR-009`).

## Hybrid database programme: ADR-009 accepted, integration branch (2026-11-19)

**GATE G2b answered:** owner replied `ACCEPT ADR-009`; ADR-009 status is Accepted (assumptions A1 to A13 accepted, A1 and A2 as corrected by measurement; open questions stay in its unresolved list). Phase 2 is complete apart from the UNVERIFIED items in the 2B entry (SQL not run on MariaDB 11.8, CI not run on GitHub, Frappe site suites not run).

**Branch route changed (owner decision):** Phases 0 and 1 reached `main` by pull request (#7, #9), because `feat/nxdesk-onboarding` was not on origin; PR #10 (Phase 2) merged into `hybrid/phase-1-harden`, not `main`. New long-lived branch `integration/hybrid-db` (from `hybrid/phase-1-harden`, with `main` merged in; contains Phases 0, 1, 2 and all of `main`; ancestry verified) is now the base of every later phase PR. `main` is promoted only deliberately. Details and the answer to "why is code in main" are in `docs/governance/hybrid-programme-workflow.md`.

## Phase 2 verification: the three UNVERIFIED items cleared (2026-11-19)

Branch `hybrid/phase-2-verification` (from `integration/hybrid-db`), before Phase 3.

**FACT, DDL on MariaDB 11.8.9** (`scripts/check_shared_ddl.sh`, throwaway container, random password never printed, container removed): `0001_shared_model.sql` runs twice (idempotent); 12 tables; utf8mb4; no foreign keys; real columns equal the contract for all 7 entities; upsert (older ignored, replay no-op, newer wins, tombstone sticks, late older cannot resurrect); cursor change rolls back with its transaction; dead letter refuses a duplicate `(source_app, event_id)`. Found and fixed: the SQL header used the MySQL 8 `AS new` upsert syntax (not MariaDB); and my first version of the check script could pass while comparing zero files (Windows path), now it fails unless it finds all 7 contracts.

**FACT, GitHub CI** (run 44479475504, dispatched on `integration/hybrid-db` at `b83eef2b6`): passed: `pins-and-architecture` (including the new contract step), `nxerp-tests`, `helpdesk-regression`, `erpnext-smoke`, `access-matrix`, `fresh-install-migrate`, `upgrade-from-previous-tag`, `e2e` flows, case3, pages, first-run, recovery, `docker-build`, `frontend`, `secret-scan`, `dependency-audit`, `codeql` x2. Failed: `lint` (bandit B404/B603 on my Phase 2 test `test_shared_contracts.py` importing `subprocess`: fixed in this branch, bandit 1.9.4 now reports 0), `license-check` (Unidecode, barcodenumber, pypdfium2 and regex outside `.github/license-policy`) and `e2e (journeys)` (two launcher-routing tests): **both already failed on `develop` on 2026-11-05, before any hybrid work**; `ci-gate` fails because it aggregates them. Those two are the team's to resolve (licence decision; routing tests).

**CI gap closed:** `ci.yml` ran only for PRs and pushes to `main` and `develop`, so PRs into `integration/hybrid-db` never ran CI and the bandit failure was not seen. It now also runs for `integration/**`.

**Still UNVERIFIED:** the CI run above was on the integration tip, not yet on this branch's fixes (the PR run will show it); the lint job and `ci-gate` stay red until the two older failures are fixed.

## Hybrid database programme, Phase 3A: spike (2026-11-19)

Branch `hybrid/phase-3-outbox` (from `integration/hybrid-db` at `5346b86c4`). Dev bench: the existing scratch stack (pinned Frappe 16.53.0, ERPNext 16.52.1) with the current `nxerp` code copied in and a fresh throwaway site `phase3.localhost`. Spike code lived only inside the scratch containers and was moved out afterwards; `hooks.py` there is restored to the repository version.

**Done:** `docs/architecture-isolation/spike-publication.md`: eight items (a) to (h) answered by running code, with evidence and confidence. **No contradiction** with the blueprint. **Recommendation: proceed with `on_change` capture** (plus `on_trash` and `after_rename`); the `before_commit` fallback is not needed.

**Five findings beyond the blueprint** (all in the document): GET requests never commit, so `ack` must be a POST; rename fires no `on_change` and delete fires `on_change` with `in_delete`; `frappe.db.set_value`, `frappe.db.delete`, `frappe.db.bulk_insert` fire nothing; the single worker is shared, so the relay must use bounded batches; a site's DB login created by `new-site` works only from the creating container unless `--mariadb-user-host-login-scope` is passed (the scheduler was refused until the host was widened).

**Measured save overhead for one extra INSERT in a handler:** about 0.6 ms (about 2%) per Customer save, within noise.
