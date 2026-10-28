# Phase 1 bootstrap evidence

Everything here was executed on 2026-10-27 on a Windows 11 workstation with Docker Desktop 29.6.1 (Compose v5.1.4, 8 GB RAM allotted). Passwords are never recorded in this repository; fake users use `*@example.test`.

## 1. Tooling check (Step 0)

| Tool | Result |
| --- | --- |
| docker / docker compose | present (29.6.1 / v5.1.4) |
| bench | **not on the host** (runs inside the pinned `frappe/bench` image: bench 5.31.0, Python 3.14.8, Node 24.21.0) |
| node / python / git / gh | v24.18.0 / 3.14.3 / 2.47.1 / 2.95.0 |
| `gh auth status` | logged in as a personal account with scopes `gist, read:org, repo, workflow` |
| NxERP repo permission (`gh repo view ... viewerPermission`) | **READ** |

## 2. One-command bootstrap

Command: `./deploy/dev/up.sh -d` (creates the git-ignored `deploy/dev/.env`, then `docker compose up`).

Clean from-scratch run (all volumes removed first, `docker compose -p nxerp-dev down -v`): **408 seconds** from `up` to `[bootstrap] ready:` (image layers and the host's Docker cache were warm; a first-ever run on a new machine downloads more).

Bootstrap log markers (verbatim):

```
[bootstrap] bench init: frappe v16.53.0
[bootstrap] payments @ cca07d9f93
[bootstrap] erpnext @ ade850bbd6
[bootstrap] telephony @ 9447577500
[bootstrap] helpdesk @ 1c6981cc51
[bootstrap] get-app nxerp (soft link to /workspace)
[bootstrap] bench build
[bootstrap] new-site nxerp.localhost
[bootstrap] install-app payments / erpnext / telephony / helpdesk / nxerp
[bootstrap] ready: http://nxerp.localhost:8100  (apps:  frappe 16.53.0 HEAD, payments 0.0.1 HEAD, erpnext 16.52.1 HEAD, telephony 0.0.1 HEAD, helpdesk 1.22.2 HEAD, nxerp 0.0.1 phase-1/foundation)
```

`bench --site nxerp.localhost list-apps` (run earlier on the first successful build, before `payments` was added):

```
frappe    16.53.0 HEAD
erpnext   16.52.1 HEAD
telephony 0.0.1   HEAD
helpdesk  1.22.2  HEAD
nxerp     0.0.1   phase-1/foundation
```

Every pin was checked against its exact commit by the bootstrap (it aborts on drift).

### Failures hit on the way (and fixes)

| # | Symptom | Cause | Fix |
| --- | --- | --- | --- |
| 1 | `bench build` failed: `ENOENT /home/frappe/sites/common_site_config.json` from `erpnext/banking/vite.config.ts` | Soft-linked apps resolve `../../sites` from their real path | Pinned apps are real clones in `apps/`; only `nxerp` is soft-linked |
| 2 | `set: pipefail: invalid option name` | My edit wrote CRLF line endings into `bootstrap.sh` on Windows | Normalised to LF; `.gitattributes` forces `eol=lf` |
| 3 | `bench setup procfile --skip-redis`: no such option | Wrong flag | `bench setup procfile`, then `sed` removes the redis/watch lines |
| 4 | Helpdesk tests: `DocType Payment Gateway not found` | ERPNext links to `Payment Gateway`, defined only by the separate `payments` app; ERPNext does not declare it; `bench get-app` skips dependencies | `payments` pinned in `deploy/apps.json`; full clean rebuild |
| 5 | 67 test errors `No module named 'freezegun'` | Test-only dependency not installed | `bench setup requirements --dev` added to the bootstrap |

Note: fix 5 was applied by running the same command in the live container and re-running the tests; the amended bootstrap was **not** re-run from scratch afterwards.

## 3. Site checks (observed)

| Request | Result |
| --- | --- |
| `GET /api/method/ping` | 200 |
| `GET /login` | 200, serves the customised NXERP login (`nxerp-login.css` present) |
| `GET /app`, `/apps` | 301 to `/desk` (Frappe 16: `/app` is only a redirect; canonical Desk is `/desk`) |
| `GET /desk` as Guest | 301 to `/login?redirect-to=%2Fdesk` |
| `GET /helpdesk`, `/helpdesk/home` | 200 (SPA shell, also for Guest) |
| `GET /v1/login`, `/api/v1/login`, `/login/helpdesk` | 404 |
| `GET /logout` | 200 |
| Realtime `http://localhost:9100/socket.io/` | 200 |

Login page (headless Chromium screenshot at 1280x800): dark hero panel with NXERP logo, "Smarter Systems for a Brighter Tomorrow" and four feature rows; right card "Welcome Back" with Email, Password, "Forgot password?", a "Continue" button and a "Contact IT Support" link. Renders correctly on Frappe 16.53.0. (The audit notes some CSS selectors, e.g. `.login-divider`, do not exist in the v16 template; the visible page is unaffected.)

First-time setup: `Installed Application.is_setup_complete = 0` for frappe, erpnext, helpdesk, telephony, nxerp, i.e. the setup wizard is pending, as designed.

## 4. Tests

| Suite | Command | Result |
| --- | --- | --- |
| nxerp scaffold | `bench --site nxerp.localhost run-tests --app nxerp` | **4 tests, OK** |
| Helpdesk backend (fork `1c6981cc5`, run on the shared ERPNext site) | `bench ... run-tests --app helpdesk` | First run: 492 pass, 67 error (all `freezegun` missing). After `bench setup requirements --dev`: **552 pass, 7 error** of 559 |
| Helpdesk 7 remaining errors | | All `frappe.exceptions.ValidationError: Throttled` (contact/invitation tests: `test_manager_role_is_applied_on_add`, `test_manager_role_survives_demotion_when_manager_elsewhere`, `test_permission_query_scopes_list`, `test_primary_contact_*`, `test_setting_primary_contact_makes_them_manager`). Probable cause: invitation throttling after repeated runs on one site (ASSUMPTION, not investigated; the same suite ran on a site that had been through two earlier runs) |
| Helpdesk Playwright e2e (28 specs) | not run | NOT RUN (needs the Helpdesk dev tooling and browsers) |
| Lint | `ruff check .`, `ruff format --check .` (ruff 0.17.2, isolated venv); YAML/JSON parse; `bash -n`; `deploy/check_pins.py`; `tools/check_architecture.py` (also with a planted violation, which it rejected) | pass |
| `pre-commit` hooks (gitleaks, shellcheck) | not run locally | NOT RUN |
| GitHub Actions `ci.yml` | **has not run on GitHub** | NOT RUN |

## 5. Seeded fake users

`nxerp.tests.seed_users.seed` (developer-mode only; password from `NXERP_SEED_PASSWORD`) created `admin@`, `agent@`, `manager@`, `erpuser@`, `customer@example.test`. Roles: System Manager / Agent / Agent Manager / Sales User + Accounts User / HD Customer (Website User).

## 6. Access baseline (HTTP status per user, today)

Produced by `tools/access_baseline.sh` against the rebuilt site. `guest` = no session. This is the behaviour Phase 2 must change deliberately; the matching static analysis is in `docs/research/`.

```
request (HTTP status)                                                 guest  admin  agent  manager erpuser customer
/desk                                                                 301    200    200    200     200     403
/desk/home                                                            301    200    200    200     200     403
/helpdesk/home                                                        200    200    200    200     200     200
/api/resource/Sales Invoice?limit_page_length=1                       403    200    403    403     200     403
/api/resource/Customer?limit_page_length=1                            403    200    403    403     200     403
/api/resource/HD Ticket?limit_page_length=1                           403    200    200    200     403     200
/api/v2/document/Sales Invoice?limit=1                                403    200    403    403     200     403
/api/method/frappe.client.get_count?doctype=Sales Invoice             403    200    403    403     200     403
/api/method/frappe.desk.form.load.getdoctype?doctype=Sales Invoice    403    200    200    200     200     200
/api/v2/doctype/Sales Invoice/meta                                    403    200    200    200     200     200
/api/method/frappe.apps.get_apps                                      403    200    200    200     200     200
/api/method/frappe.desk.desktop.get_installed_apps                    403    200    200    200     200     200
/api/v2/discovery/search?q=sales                                      403    503    503    503     503     403
/api/resource/Workspace?limit_page_length=1                           403    200    200    200     200     403
/api/resource/Report?limit_page_length=1                              403    200    200    200     200     403
/api/method/frappe.desk.desk_page.getpage?name=point-of-sale          403    200    403    403     200     403
/api/method/helpdesk.api.config.get_config                            200    200    200    200     200     200
/api/method/helpdesk.api.auth.get_user                                403    200    200    200     200     200
Guest /helpdesk HTML contains an "apps" list: not found (pattern `"apps": [...]`)
```

What it shows (FACT, this site):

- Data is protected by role/DocType permission: the agent and manager get 403 on Sales Invoice, Customer and sales data; the ERP-only user gets 403 on HD Ticket.
- Nothing stops a Helpdesk-only System User from opening `/desk` (200), and every user, including the customer, can fetch ERPNext DocType **metadata** (`getdoctype`, `/api/v2/doctype/.../meta`: 200). Workspace and Report lists are readable by every System User.
- The Helpdesk shell `/helpdesk/home` returns 200 for everyone including Guest; `get_config` is open to Guest.
- `/api/v2/discovery/search` answered 503 for all logged-in users (feature not enabled on this site; not investigated).

Launcher and landing (earlier probe on the first build, with the same seeded roles):

- `POST /api/method/login` returned `home_page: "helpdesk"` for **every** user, including the ERP-only user and Administrator; the customer got `message: "No App"`, `home_page: "/helpdesk"`.
- `frappe.apps.get_apps` over HTTP: Administrator sees ERPNext + Helpdesk tiles; agent and manager see Helpdesk only; the ERP-only user and the customer see **no tiles** (ERPNext's tile is hidden until ERPNext's own setup wizard completes, for non-System Managers).

## 7. Not verified

Realtime room checks, `before_request` vs token ordering, private-file/print checks (no seeded ERPNext documents), Helpdesk Playwright tests, browser-level behaviour of bare `/desk`, 2FA on non-password login routes, the bootstrap amended with `bench setup requirements --dev` from scratch, and everything on GitHub (CI, branch protection, PR).

## 8. Workspace consolidation and palette verification (2026-10-27, later the same day)

- The platform clone was moved into the workspace as `nxerp-platform/`, next to `helpdesk/`. A full rebuild from empty volumes (`down -v`, then `./deploy/dev/up.sh -d` from the new location) took **418 s** and installed Helpdesk from the local palette commit (`[bootstrap] helpdesk @ 9647f7664d (local /helpdesk-src feature/nxerp-palette)`). This run included the amended `bench setup requirements --dev` step, so that fix is now verified from scratch.
- `yarn theme:check`, in the container against the real frappe-ui: generated files up to date; coverage 384 frappe-ui tokens per mode, accent family complete (frappe-ui 1.0.0-rc.1); contrast 99 checks passed in light and dark; synced copies up to date. `yarn theme:audit`: no hardcoded colors.
- `bench run-tests --app nxerp`: 5 tests OK (adds the Desk-palette hook/asset test). `--module helpdesk.tests.api.test_theme`: 3 tests OK. `GET /assets/nxerp/css/nxerp-desk-theme.css`: 200.
- Found and fixed: the Helpdesk repo's `.gitignore` excluded `desk/src/theme/build/` and `build/lib/` (generic `build/`, `lib/` rules), so the palette generator was never in git.
- Screenshots (headless Chromium via `tools/screenshots.mjs`, light and dark): login; Helpdesk home and tickets; ERPNext Desk (Administrator is sent to the first-run setup wizard, which shows the palette). Observed: warm paper/sand surfaces, charcoal/amber actions, charcoal dark mode; the NXERP and ERPNext logo marks stay blue (brand assets) and status chips stay category colours. Images are not stored in the repository.
- Not run: Helpdesk Playwright `theme.spec.ts`.

## 9. Palette coverage and the nxerp-stable port (2026-10-27)

- **Coverage scan** (`tools/palette_scan.mjs`, headless Chromium, 1440x900, with `tools/seed_demo_data.py` data: 25 tickets over every status/priority): agent role 14 routes, Settings 15 tabs plus the first New/Add form of each (19 views), customer role 4 pages, guest 3 pages, desk role (ERPNext Desk report, ToDo, Sales Invoice form, `/me`, `/update-password`). Leaks (cool/violet colours outside status chips): 0 in Helpdesk, guest and customer views. In Desk, one Frappe status pill ("Enabled", Frappe's own blue indicator) and the ERPNext app icon remain. Status/tag chips (SLA states) are category colours by design.
- **Scanner self-check:** the first Settings run reported zeros because its "New/Add" click had matched a sidebar item; screenshots showed it, the click was restricted to the content pane, and the rerun opened the real forms (New SLA Policy, New Team).
- **Static gaps the scan could not see, found and fixed:** `#FFFFFF` mask-icon colour in `desk/index.html`; PWA manifest `background_color: #ffffff` and no `theme_color`; stock blue-grey hexes in email templates and the welcome-ticket HTML; a stock green in a dashboard chart; a stock gray default in the ticket report. Guards added: server-side audit (a literal colour in backend files must be a palette value), `check-tracked`.
- **Git guard proven both ways:** with the `.gitignore` exceptions removed, `check-tracked` fails and lists every ignored generator file; restored, it passes (29 palette files tracked, none ignored).
- **nxerp-stable port:** base `07f84a2c8` (Helpdesk 1.30.2, frappe-ui beta.24, Vite 4.5, Frappe v15.122.0). Palette commits cherry-picked; conflicts resolved by taking the palette side turned out to import non-palette behaviour from the newer line, found by reading the full diff and removed: the newer `toast()` API, the rc.1 radius scale, `dashboard.py`'s chart-config format (would have broken the dashboard), Black reformatting in `login.py`, an unused call-log table. The result is 82 files, palette-only. Verified in a sandbox mirroring the real layout (Frappe 15.122.0 `ui` as sibling): `theme:check` (406 frappe-ui tokens, 99 contrast checks), `theme:audit`, `check-tracked`, and a full `vite build` (built in ~38 s; the 6.3 MB CSS is inherent: the unmodified branch builds to 6.27 MB). Python: `py_compile` on all 11 changed files. **Not run:** the Frappe 15 backend and its tests, the SPA in a browser on that line, Playwright.
- **Found along the way:** `nxerp-stable`'s `yarn.lock` is already out of date with `desk/package.json` (`yarn install --frozen-lockfile` fails on the unmodified branch), so the new CI job there installs without `--frozen-lockfile`.
- **Push:** `07f84a2c8..8bb287a86` to `Sriainfotech/Frappe-Help-Desk` `nxerp-stable` (fast-forward, no force), verified with `git ls-remote`. The branch's `Build NXERP Helpdesk Image` workflow runs on push and publishes `ghcr.io/<repo>:nxerp-stable`. **That workflow ran for the push (run 40440655803, commit 8bb287a86) and succeeded** (`gh run view`: conclusion success, job Build success): the first build of the palette on the real Frappe 15.122 image path. The two builds before the last green one on this branch had failed (earlier, unrelated commits).

## 10. Phase 2 verification (2026-10-27)

- `bench --site nxerp.localhost run-tests --app nxerp` on the rebuilt Frappe 16.53 dev site: **115 tests, OK**
  (matrix 7, resolver 18, customer leaks 19, enforcement 39, ERPNext smoke 4, guard/admin 14, registry 9, scaffold 5).
- Helpdesk's own backend suite with the access layer active: **566 tests, 0 failures** (371 + 156 + 39 in three batches). The 7
  `Throttled` errors from section 4 are explained: Frappe's `throttle_user_limit` (default 60 new users per hour); storing it
  as the string `"100000"` instead of a number first produced 252 `TypeError`s (`bench set-config -p` stores a number).
- ERPNext smoke: an authorised user loads `/desk`, creates and reads a Customer and an Item over HTTP; the same business
  roles without the grant are refused on the same session and allowed the moment the grant is added.
- Static: bandit 1.9.4 (0 high, 0 medium, 1 low accepted), ruff check and format clean, architecture check, pin check.
- Test-environment notes: the bench container's `NXERP_ADMIN_PASSWORD` can be stale relative to `deploy/dev/.env`; pass it
  explicitly with `docker compose exec -e`. Tests create and delete committed fake users and records on the dev database.
- Not run: the GitHub Actions workflow (no write access to the repository), so no CI result exists.
