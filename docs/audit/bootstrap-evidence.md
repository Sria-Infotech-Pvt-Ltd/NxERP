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
