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

## Hybrid database programme, Phase 5: independent stacks (2026-11-19, in progress)

Branch `hybrid/phase-5-stacks` from `hybrid/phase-1-harden`, built in the Track A worktree. ASSUMPTION: Phase 4 (shared layer, PR #15) is not merged yet, so `SHARED_SYNC_NETWORK=nxerp-api` is documented, not tested here.

**5A done.** `deploy/docker/compose/isolated/db.compose.yaml` (project `nxerp-db`: `mariadb-standard`, `mariadb-restricted`, two internal networks 172.30.10.0/24 and 172.30.20.0/24, no published ports, no-new-privileges, root passwords required) and `db.env.example`. FACT: `docker compose config` passes; the two servers started `healthy` and `docker network inspect` shows `Internal=true` for both. **Finding:** the root `.gitignore` did not ignore `deploy/env/isolated/db.env` (its rules match `.env` and `.env.*` only); added explicit rules, `git check-ignore -v` now quotes them.

**5B done.** `stack.compose.yaml` (one template, three instances), `id/erp/hd/app.env.example`, `stacks.list.example`, `deploy/scripts/stack.sh`, `NXERP_PASSTHROUGH` in `lib.sh`. FACT: `config -q` passes for id, erp, hd; `shellcheck` clean on `stack.sh` and `edge-gen.sh`; a stack name not in `stacks.list` is refused; `down -v` is refused without `NXERP_ALLOW_DESTROY=1`.
**Defects found by running it, all fixed:** (1) `bench new-site --no-mariadb-socket` silently overrides `--mariadb-user-host-login-scope`: the first sites got logins for host `%`; the flag is removed and the logins are now `172.30.10.%` and `172.30.20.%` (verified in `mysql.user`). (2) the failure cleanup called `bench drop-site` with an option it does not have, so a failed create left a database and login behind; fixed. (3) `create-site` could start before Docker's DNS resolved `redis-queue` (a parallel run failed with "Name or service not known"); it now waits for the database and both Redis servers. A leftover half-created database and login from defect (2) remain on the rehearsal restricted tier (my cleanup command was blocked by the safety check; harmless rehearsal data).

**5C files done.** `edge.compose.yaml`, `edge/nginx.conf.template`, `edge/server.block.template`, `deploy/scripts/edge-gen.sh`, `edge.env.example`, isolation audit subcommands `cross-read`, `reach`, `published`, `hostnames`, `stacks`, the CI `docker compose config -q` step for the new files (plus `nginx -t` on the generated config), README and `deploy.md` sections. FACT: `edge-gen.sh` renders three server blocks and the networks override; `nginx -t` passes on the generated file; actionlint passes. **No workflow has ever run on GitHub**: the new CI step is syntax-checked only.

**Phase 5 rehearsal results (2026-11-19, Docker Desktop, fake data).** FACT: `stack.sh db up`, `create-site` and `up` for `id`, `hd`, `erp`; `list-apps`: id `frappe nxerp`, hd `frappe telephony helpdesk nxerp`, erp `frappe payments erpnext nxerp`; edge on `127.0.0.1:8180`; `isolation_audit.sh cross-read reach published hostnames stacks`: 65 PASS, 0 FAIL, 0 UNVERIFIED. Six-site proof with three throwaway stand-ins made from `app.env.example` and one `stacks.list` line each, no change to any compose file: 152 PASS, 0 FAIL, full 6 by 6 cross-read matrix, 39 long-running containers. Stand-ins then removed with the new `stack.sh <n> drop-site` and `down -v`; the three real stacks still pass. The old develop stack stayed up and healthy throughout.
**More defects found and fixed:** the failure cleanup dropped the database but not the subnet-scoped login (now dropped, verified: the count of logins did not grow after a deliberately failing create with a nonexistent app); new sites have the scheduler disabled so `health` failed (the template now runs `enable-scheduler`; this one line is config-checked only, not yet exercised by a fresh create); `down -v` leaves a stack's database on its tier, so `drop-site` was added. Leftover from the first buggy runs: two unused logins and one database on the rehearsal tiers (blocked deletion, harmless).
**NOT DONE:** steps 5.1 to 5.3 (DNS, firewall, host nginx and certbot), 5.7 and 5.8 with real names on the server, and the old-stack comparison on the server: all wait for GATE G5. Not verified: env file mode 600 on this Windows machine (NTFS shows `-rw-r--r--`; on the Linux server `chmod 600` applies); the CI step has never run on GitHub (no workflow has).


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

## Hybrid database programme, Phase 3B and 3C: outbox, capture, relay, feed (2026-11-19)

Branch `hybrid/phase-3-outbox` (from `integration/hybrid-db`). Everything is **off by default**: with `nxerp_shared_publish` unset every capture handler, the relay, prune and the feed return at their first line. No change to Helpdesk or ERPNext code; `nxerp` still imports no other app and declares no `required_apps`.

**Built:** DocType `NXERP Outbox Event` (UUID name, unique `seq`, indexes on `(status, creation)` and `(entity_type, entity_id)`); `shared/outbox.py` (insert in the caller's transaction, never commits or enqueues); `shared/digest.py` (the one projection, shared by capture and feed); `shared/capture.py` (`on_change`, `on_trash`, `after_rename`, registered in `hooks.py` from the active contracts); `shared/relay.py` (`GET_LOCK`, batches of 1000, one transaction per batch, daily prune); `shared/feed.py` (`head`, `pull`, `ack` POST-only, `digest`, `snapshot`, `snapshot_by_ids`); role `NXERP Shared Feed Reader` (install hook plus idempotent patch in `patches.txt`); two `scheduler_events`; docs `capture-notes.md`, `spike-publication.md`, `feed-api-v1.md`.

**FACT, run 2026-11-19 on the dev bench (Frappe 16.53.0, MariaDB 11.8, site `phase3.localhost`):**
- `test_outbox` 17 tests OK; `test_feed` 21 tests OK (a real second database connection for the concurrency tests: an older uncommitted row is sequenced after newer committed ones, commit order wins).
- Existing suite with the feature unset, module by module as CI does: 15 modules OK (`test_access_resolver`, `test_add_app_checklist`, `test_architecture`, `test_branding`, `test_enforcement_unit`, `test_feed`, `test_grant_migration`, `test_guard_and_admin`, `test_onboarding`, `test_outbox`, `test_registry`, `test_routing`, `test_scaffold`, `test_shared_contracts`, `test_site_assets`); `test_architecture` shows OK but skipped all 17 tests there (no `scripts/` in the bench image), and `test_shared_contracts` skipped 21 for the same reason: both run in full locally and in CI.
- **Seven modules fail on this throwaway site and fail identically on the unmodified baseline** (same counts, run side by side): `test_unified_experience` 23, `test_public_site` 17, `test_onboarding_pages` 17, `test_public_catalog` 5, and a `setUpClass` error each in `test_erpnext_smoke`, `test_customer_leaks`, `test_access_matrix`. Cause: HTTP tests get `404 localhost does not exist` (the site has no setup wizard and is not the default host). They ran green on CI's prepared stack. Not caused by this work.
- End to end over real HTTP: a Customer insert plus edit wrote 2 pending rows; the **real scheduler's relay sequenced them within 21 s**; a service user holding only the feed role pulled both as valid envelopes (contract fields only, tenant `ORG-001`, a planted tax id never appeared); `ack` as GET is refused (403) and persists nothing, as POST it acks 2, again acks 0, beyond the head is 422; no-role and no-token callers 403, wrong secret 401; bad arguments 422.
- **Measured save overhead (Customer save, 100 saves per round, 3 rounds each): 40.5 ms off, 42.8 ms on, +2.3 ms (5.7%).** The 3A spike measured +0.6 ms for a bare extra insert; the real capture also builds the contract payload and its hash.
- `ruff check` and `ruff format --check` clean on every file added or changed; `bandit` (CI arguments) 0 findings on the whole app; `check_contracts.py` PASS for 7; `check_architecture.py` OK.

**Found and fixed while testing:** (1) my Phase 2 test modules loaded `scripts/check_contracts.py` at import time, which breaks test discovery wherever `scripts/` is absent (a bench image); they now skip, like `test_architecture`; (2) one Phase 2 test read a repo-only path; (3) the relay did not see a row committed elsewhere while it inherited an open REPEATABLE READ snapshot: it now ends the inherited transaction first; (4) ERPNext's own `Customer.after_rename` runs `db_set`, so a rename can emit an extra upsert before the delete+upsert (documented, harmless).

**Not done / UNVERIFIED:** CI has not run on GitHub for this branch (the PR run will show it); `test_shared_contracts`, the schema test and the envelope test skip some tests in the bench (no `scripts/`, no `jsonschema`) and run in full locally and in CI; the nudge (a deduplicated after-commit enqueue from `write_event`) was not built: the per-minute cron meets the 60 s lag target and 3B forbids enqueueing in a handler; `digest` lists live documents only (`deleted` is always 0; deletions are found by comparing id lists in Phase 4); feed behaviour on the Helpdesk site and for `HD Ticket` and `Company` was not exercised end to end (unit-level only for the projection).

**Leftovers in the scratch containers (outside the repository):** `/tmp/spike_keys` and `/tmp/feed_keys` hold API keys of users that no longer exist (dead keys; deleting them was blocked by a safety check and left to the owner), and `/tmp/spike_archive/` holds the moved spike files; the scratch bench has a `nxerp_baseline_*` directory next to `nxerp`.

## Hybrid database programme, Phase 4A and 4B: shared stack, accounts, views, projector (2026-11-19)

Branch `hybrid/phase-4-shared-layer` (from `integration/hybrid-db` after Phase 3 merged). PR titles now follow `type(scope): summary` (PR #13's `lint` failed only on its title, `hybrid: ...`).

**4A done.** `deploy/docker/compose/shared/shared.compose.yaml` (own MariaDB on an internal network, projector, Read API, one-shot tools; no host port; the root password is held only by the database server and the one-shot `shared-root-tool`), `shared.dev.override.yaml`, `deploy/env/shared/*.example`, `deploy/scripts/shared.sh` (`init-env`, `prepare`, `up`, `down`, `migrate`, `create-accounts`, `views`, `grants`, `tokens`, `rebuild`, `reconcile`, `stop`, `start`, `status`, `test`). In `nxerp/shared_service/`: `sqlutil.py`, `db.py`, `migrate.py` (ledger with checksums), `accounts.py` + `schema/0002_accounts_and_views.sql.tmpl` (passwords are bound parameters), `grants.py`, `views.py` (generated `v_<app>_<entity>`), `schema/0003_read_api_support.sql` (consumer_credential, sync_metric, tenant and audit detail, `ctl_*` views), `__main__.py`; `nxerp/shared/payload.py` (the frappe-free hash shared with the owners).

**4B done.** `config.py`, `feedclient.py` (stdlib, connect 3 s, read 20 s, `FeedUnavailable` vs `FeedRejected`), `metrics.py`, `apply.py` (one statement shape for upsert, tombstone and repair), `projector.py`, `fakeowner.py` (an in-process stand-in for an owner's feed), `docs/runbooks/shared-layer-recovery.md`.

**FACT, run 2026-11-19 against MariaDB 11.8.9 on the real stack (`deploy/scripts/shared.sh test`):** `shared.sh prepare` brought up the database, accounts, 2 migrations, 5 grants and 5 views; the grant matrix is exact (projector: SELECT, INSERT, UPDATE, DELETE on entity and sync tables only; Read API account: SELECT on views and 3 `ctl_*` views, INSERT on `ctl_read_audit`, nothing on any base table; no database-wide privilege; `docker ps` shows no published host port). T10-style refusals pass (the Read API account cannot read or write a base table, update a view, or create a view). Projector: 28 tests pass (T16 duplicate delivery is a no-op, T14 no loss across an outage, out-of-order versions, delete then late older upsert stays deleted, resurrection by a newer upsert, rows and cursor atomic under a kill before commit, lost ack recovered, dead letter without payload values, sequence gap stops the source, backoff 1 2 4 ... 60, a rejected source retried only every 300 s, one failing source does not block another, transient database error, per-event fallback after 5 attempts). Unit tests (views golden output, SQL helpers, account rendering, config, feed client) pass without a database. `ruff` clean; `bandit` strict (no skips) 0 findings on the whole of `shared_service`.

**Decisions and findings:** (1) the migrate account cannot read other accounts' grants, so `apply_object_grants` makes them exact by revoking everything on the database and each object and re-granting the matrix (converges from any state); (2) validation failures are dead-lettered at once (retrying a deterministic failure is pointless); only data errors on apply are retried (5 attempts, one event alone); (3) the lag gauge comes from the owner's `oldest_pending_age_seconds`, not from `source_modified` (the owner's timestamps are in its site time zone, not UTC); (4) `consumer_grant.tenant_id` is a new column (0003): a constant-tenant contract's grant carries its tenant, enforced inside the view; (5) the Read API needs credential rows and an audit write, so it reads them through `ctl_*` views and inserts through `ctl_read_audit`, never touching a base table.

**Not yet:** 4C (reconcile, rebuild), 4D (Read API, tokens), the runbook steps against the owner site (feed keys, backfill, one-hour soak, `scripts/shared_audit.sh`), and CI for the new test folder (the database tests need `shared.sh test`; the unit tests run anywhere).

## Hybrid database programme, Phase 4C: reconciliation, backfill and rebuild (2026-11-19)

**Done.** `nxerp/shared_service/reconcile.py` (recent scan from a watermark kept in the owner's own timestamps, full compare by id and payload hash, categories missing, extra, stale, hash_mismatch, ahead; repair owner to shared by the owner-truth rule; `Schedule` and `run_schedule` for the hourly and nightly runs), `rebuild.py` (one path for first fill and disaster recovery: snapshot, tombstone what the owner no longer has, cursor to the recorded head, replay through the projector, full compare), `__main__.py` (`reconcile --recent|--full`, `reconcile-loop`, `rebuild --source|--all`), a `shared-reconciler` service in the compose project (a separate process from the projector), `docs/architecture-isolation/shared-layer-jobs.md`, and the recovery runbook extended with reconcile and rebuild.

**FACT, run 2026-11-19 on MariaDB 11.8.9 (`shared.sh test`, 129 tests, 3 skipped for the absence of jsonschema and `scripts/` in the image):** T17: a change made at the owner without an event and without a new stamp is found by the full compare as `hash_mismatch` and repaired, and the next run reports drift 0; a row the owner deleted without an event is `extra` and tombstoned; a document created without an event is `missing` and copied; a newer stamp without an event is `stale` and copied; the recent scan misses a same-stamp change on an old document (the full compare finds it); the recent scan never reports `extra`. An unreachable owner (HTTP 500, 503) and a rejecting owner (403) are skipped and reported, and their rows are never marked extra; an entity the feed does not serve is left alone; a repair that would write a field outside the contract is refused and reported; a hash function difference fails loudly (`HashFunctionMismatch`) and repairs nothing; reports contain ids and counts, never values. T18: the shared database was dropped and recreated empty, `rebuild` restored it, `drift_after` 0, cursor equal to the owner's head and live, a second full compare 0; a rebuild while the owner kept creating, changing and deleting converged (the events after `start_seq` were replayed); an interrupted rebuild leaves the source `rebuilding` (the projector does not touch it) and the same command finishes it; a gap-stopped source is recovered by a rebuild.

**Decisions:** a repair tombstones an `extra` row with its own version stamp under the owner-truth rule (no clock arithmetic across the owner's time zone); the recent window is kept as a watermark in the owner's own timestamps, because the owner's `modified` is in its site time zone, not UTC; the compare holds one entity type's ids in memory (fine for reference data of this size, stated in the module).

**Not yet:** 4D (Read API, tokens, grants audit), the runbook steps against the owner site, and `scripts/shared_audit.sh`.

## Hybrid database programme, Phase 4D: Read API, tokens, audit (2026-11-19)

**Done.** `credentials.py` (scrypt-hashed per-app tokens: issue, rotate with grace, revoke, list), `readapi.py` (GET-only WSGI: entity, list, health, metrics; fields and tenant enforced from the grant; tombstones hidden; `min_version` wait up to 2 s then 202; rate limit; one audit row per call, denied included, batched), migration `0004_audit_outcome_width.sql`, `docs/architecture/read-api-v1.md` (calls, errors, caching and degradation advice, TLS statement).

**FACT, run 2026-11-19 on MariaDB 11.8.9 (`shared.sh test`):** 157 tests OK (3 skipped), 28 of them the Read API (T9: 401 no/garbage/expired/revoked token, 403 other app's token and field outside the grant, 404 tombstone and other tenant look alike, 405 for POST/PUT/DELETE/PATCH, audit for every outcome; T10: view with extra columns never leaks them, min_version wait and 202, 429, 503 with no SQL or trace). ruff and bandit clean for `shared_service`.

**Found while testing:** audit `outcome` was VARCHAR(16) and truncated `denied_unauthorized`, so those audit rows failed and were retried forever; widened by migration 0004 and a data error now drops the batch with an error log instead of looping.

**Not yet:** runbook steps against the owner site (feed keys, backfill, soak, `scripts/shared_audit.sh`). 12 I001 ruff findings in `nxerp/www/*` exist with ruff 0.16.9 (not touched here; CI pins another ruff).

**Soak result (2026-11-19, 10 minutes, not the 1 hour asked; ~1 owner edit/s, 600 edits plus contact inserts and deletes on a throwaway site).** FACT: the projector cursor moved from 759 to 1379 and every event applied; dead letters 0, gap 0. A full reconcile right after the load found drift 4 (deleted contacts the relay had not yet published) and repaired it; a second full reconcile found drift 0. UNVERIFIED: p95 end-to-end lag. The watcher started too late and recorded only 9 markers, so no valid figure exists; the relay is a one-minute cron, so p95 may exceed 60 s. Re-run for an hour before relying on a lag number.

## Hybrid database programme, Phase 6A: federation spike (2026-11-19)

Branch `hybrid/phase-6-identity` from `hybrid/phase-5-stacks`. `docs/architecture-isolation/spike-federation.md` answers items (a) to (h) with a real run on the Phase 5 `id` and `hd` stacks (`scripts/spike_federation_flow.py`). **FACT:** single sign-on works with userinfo only: `hd logged user after callback = user@example.test`; unknown user: 403 with Sign ups Deny, auto-created Website User with the portal role `HD Customer` with Allow; disabled user: "Not Allowed / User is disabled"; with `disable_user_pass_login` the password POST answers 401 with no `sid` and SSO still works; the `sid` cookie has no Domain (host-only). **Findings that change the plan:** the OAuth Client secret is a clear-text Data field of 10 hex characters when auto-generated (we set our own); OAuth Client `allowed_roles` is a real gate (an empty list allows nobody; a user without the role is refused at the identity site with `400 Invalid client_id`), so the identity site can enforce the grant; nothing reads the `roles` claim. Phase 5 follow-up in this branch: the edge now aliases every stack host name on each stack network. **DECISION (6A): GO.**

## Hybrid database programme, Phase 6B: app registry, safe routing, login button (2026-11-19, in progress)

`nxerp_site_role` (identity | app | unset), DocType `NXERP Peer`, `registry.active_entries()/allowed_origins()/normalise_origin()`, `routing.safe_target` accepts an absolute URL only for the exact origin of an enabled peer, launcher/landing use `origin + route` (`access.app_url`), `/login` on an app site shows one "Sign in with NXERP" button. **FACT:** `bench --site id.example.test run-tests --app nxerp --module nxerp.tests.test_identity_site`: 16 tests OK (registry with peers, strict origin normalisation, 28 cross-origin payloads refused, the 35 original hostile payloads refused with peers registered, FIVE apps (two real, three test-only dummies) for the gate, tiles, landing, router and origins; unset or unknown role changes nothing). `scripts/check_architecture.py` OK. **Deviation:** the new tests live in a new module `test_identity_site.py` (they need the same fixtures in three places) instead of being appended to `test_registry.py`, `test_routing.py` and `test_unified_experience.py`. **Finding:** Frappe turns a user without any desk-access role into a Website User, so a user holding only `NXERP Access: ...` roles is not a System User; tests add a plain desk role.

## Hybrid database programme, Phase 6C: grant provisioning (2026-11-19, in progress)

New package `nxerp/federation/` (`client.py`, `outbox.py`, `reconcile.py`, `api.py`), DocType `NXERP Provisioning Outbox`, patch `create_federation_roles` (role `NXERP Provisioner`, listed in `patches.txt`), `doc_events["User"]["on_update"]` and `scheduler_events` (all, daily) in `hooks.py` with `test_scaffold.py` updated deliberately to pin them, `guard.py` lets a verified provisioner change only the access role of this site's apps (flag set by server code only), `set_app_access` and `install.ensure_access_roles` understand the identity site (an identity site holds every app's access role). **FACT:** `bench --site id.example.test run-tests --app nxerp --module nxerp.tests.test_federation`: 25 tests OK (provision/deprovision idempotent by key and by state; Administrator, Guest and System Manager refused; a caller without the role refused including Guest; the API is off unless the role is `app`; rolled back grant change leaves no row; backoff 30 s doubling to 1 h then Failed after 8 attempts; `last_error` and the logs hold no token or secret even when the underlying error text does; delivery decides from the identity state at send time; reconcile repairs missing and extra users toward the identity site and a second run reports 0 differences; an unreachable peer is counted, not guessed; with no site role nothing is queued, sent or reconciled). ruff and bandit clean for `federation/`; `check_architecture.py` OK. **Deviation:** `nxerp/shared/outbox.py` is not in this branch (Phase 3 lives on another line), so the outbox is written here on the same pattern instead of reusing it.

## Hybrid database programme, Phase 6D: setup helpers, decision amendment, lockout safety (2026-11-19, in progress)

`nxerp/federation/setup.py` (`configure_identity_site`, `configure_app_site`): idempotent, secrets only from environment variables (NXERP_SSO_SECRET_<APP>, NXERP_SSO_CLIENT_SECRET), never in a result or a log, never touch System Settings. `docs/adr/ADR-003-amendment-2.md` (grants are roles on the identity site, business roles stay per app, no password leaves the identity site, local login disabled only after single sign-on is proved, customers' logins live on the identity site: ASSUMPTION A4), `docs/runbooks/login-recovery.md` section 6 (per-app break-glass, with a table of which commands were tested and which not), `docs/architecture/adding-an-app.md` (stack-template steps; the prompt cites blueprint section 2.12, whose "how a new app is added" content is section 2.8: ASSUMPTION), `docs/architecture-isolation/phase-6-user-actions.md` (the nine human steps). **FACT:** `bench --site id.example.test run-tests --app nxerp --module nxerp.tests.test_federation`: 30 tests OK (the 25 of 6C plus: the identity setup creates one gated client per peer and a second run changes nothing, the app setup creates the Social Login Key with Sign ups Deny and a second run changes nothing, no secret in a result, a log or the output, a short or missing secret is refused naming only the variable, the helpers never write System Settings).

## Phase 6: staging rehearsal and checks (2026-11-20)

**FACT, `python scripts/rehearse_federation.py` on the Phase 5 stacks (`id` identity, `hd` and `erp` app sites, fake data; sites in developer_mode so http origins are accepted): 31 PASS, 0 FAIL.** Steps 6.3 to 6.9 and tests T7 and T8: service users with exactly `NXERP Provisioner`; two peers (stored secret is not the secret); one gated OAuth client per peer made by the helper, a second run changes nothing; Social Login Keys with Sign ups Deny, second run changes nothing; `hd /login` shows "Sign in with NXERP"; a grant on `id` queues one row, is delivered, and `hd` has the user enabled with the access role and **no password**, `erp` has nothing; one sign-in at `id` lands on `hd` with no second password; the identity site refuses the sign-in to `erp` (no grant); with local login off a direct password POST on `hd` is refused with no `sid` and single sign-on still works (T7); the recovery lines make local login answer again; revoking on `id` disables the user on `hd` and removes the role, never deletes (T8); drift in both directions is repaired by the reconcile and a second run reports `0 differences`.
**FACT, unit tests on the clean scratch site (`phase3.localhost`, ERPNext + Helpdesk + nxerp, `nxerp_site_role` unset), Check 6.1:** `test_federation` 31, `test_identity_site` 16, `test_scaffold` 5, `test_registry` 14, `test_routing` 31 (35 hostile payloads still refused), `test_guard_and_admin` 14, `test_access_resolver` 18, `test_add_app_checklist` 31, `test_enforcement_unit` 39, `test_grant_migration` 2, `test_onboarding` 28, `test_branding` 3, `test_site_assets` 6: all OK.
**Existing modules that fail in this bench both before and after Phase 6 (so not caused by it):** `test_onboarding_pages` (17), `test_public_site` (17), `test_public_catalog` (5), `test_unified_experience` (23, HTTP), `test_access_matrix`, `test_customer_leaks`, `test_erpnext_smoke` (setup errors): they need HTTP access to the site (`NXERP_TEST_BASE`) that this container run does not provide; the same counts appear on the code of the 6A commit. `bench run-tests --app nxerp` as a whole cannot start here because two Phase 2 modules load `scripts/check_contracts.py` at import (fixed on another branch). **UNVERIFIED:** those modules against a stack with HTTP access.
**Defects found by running it and fixed:** (1) MariaDB 11.8's snapshot isolation rejected a stale outbox update when a worker and the scheduler overlapped (`QueryDeadlockError`): each row now gets a fresh snapshot and a conflict leaves the row Pending; (2) a Disable for a user the identity site does not know (found by the reconcile on a peer) failed with "user no longer exists": it is now delivered as Disable; (3) the OAuth Client secret is a 10-character clear-text field (setup supplies its own); (4) users holding only access roles are Website Users (a business role from the app's administrator is still needed).
**NOT DONE, waiting for a person:** GATE G6a (a browser sign-in), GATE G6b (disabling local login on any real site, which this phase never does). Production untouched: the rehearsal used only the local staging stacks.

**Found at GATE G6a (a real browser, 2026-11-20): the first sign-in looped back to the app's login page.** Cause: when a person is not yet signed in at the identity site, Frappe sends them to the identity `/login` carrying the single sign-on continuation (its own `authorize` endpoint) as an ABSOLUTE URL of that site; the NXERP router refuses unknown destinations and absolute URLs, so the continuation was dropped, the person landed on the app's login page, and clicking the button again repeated it. The scripted rehearsal had missed it because its identity session already existed. Fix in `routing.py`: on an identity site only, that one endpoint is honoured (a same-site path stays, and an absolute URL is accepted only when its host is this site's own, with no user-info, and returned as a plain path); nothing else changes. Tests: `test_identity_site` 18 OK (hostile variants: another host, user-info, another endpoint, suffix host, `javascript:`; refused off the identity site), `test_routing` 31 OK. FACT: the scripted first-time sequence (anonymous authorize, identity login, router, authorize, app callback, app router) now ends with the user logged in at `hd`.
**Rehearsal note:** the edge sends `Host: $host` (no port), so redirects Frappe builds from the request host omit `:8080`; only the local rehearsal uses a non-default port. Production uses https on 443.

**Second finding at GATE G6a (2026-11-20): the "Sign in with NXERP" button pointed at the app site itself.** Frappe joins the Social Login Key's Base URL onto its three relative URLs only when "Custom Base URL" (`custom_base_url`) is ticked; otherwise the link stays relative and goes to the app. The spike and the first scripts had built the authorize link themselves, so they never saw it. Fix: `federation/setup.py` sets `custom_base_url` = 1 (a unit test pins it), the spike and the user-actions document now say so, and `scripts/rehearse_federation.py` now asserts the button's link is an absolute URL on the identity origin. **FACT:** rehearsal 32 PASS, 0 FAIL; and a real Chrome (Playwright driving `chrome.exe`, name mapping on, fake user) went hd `/login` -> click -> identity login -> fill -> `hd.example.test:8080/helpdesk/home` (every navigation logged: 302 to the identity site, 301 to its login, router keeps the continuation, 302 back to the app callback, 301 router, 200 Helpdesk). Still waiting for the person's own browser (GATE G6a).

**GATE G6a passed (2026-11-20):** the owner signed in with a real browser (fake user, staging stacks) and reached Helpdesk with no second password prompt ("SSO OK"). Break-glass proof for GATE G6b: see below.
**Break-glass proof (FACT, 2026-11-20, staging stacks):** the local `Administrator` signs in with the stack's own password on `hd`, `erp` and `id` (local login still on), and the recovery lines (`frappe.db.set_single_value("System Settings", "disable_user_pass_login", 0)` then `frappe.clear_cache()`) made local login answer again after it had been off, in the rehearsal. UNVERIFIED: the same lines typed in an interactive `bench console` (needs a terminal).

**GATE G6b passed (2026-11-20): "GO DISABLE LOCAL LOGIN" for the STAGING app sites `hd` and `erp` only (throwaway stacks on the owner's machine, fake data).** Done with `frappe.db.set_single_value("System Settings", "disable_user_pass_login", 1)` and `frappe.clear_cache()`. FACT afterwards: `/login` on both sites shows no password form and the "Sign in with NXERP" button; a password POST with the real break-glass Administrator password answers 401 and issues no `sid` (T7); single sign-on in a real Chrome (fake user) still lands on `hd.example.test:8080/helpdesk/home`. Local login stays OFF on these two staging sites; to turn it back on: `deploy/scripts/stack.sh <hd|erp> bench console`, then `frappe.db.set_single_value("System Settings", "disable_user_pass_login", 0)`, `frappe.db.commit()`, `frappe.clear_cache()` (the same lines were proved non-interactively in the rehearsal; the interactive console is UNVERIFIED). NOT done and not in scope: any production site, the identity site's own local login (kept on), and the server install.

