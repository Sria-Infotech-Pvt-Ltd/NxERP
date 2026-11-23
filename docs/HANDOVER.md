# NXDESK handover

Repository `github.com/Sria-Infotech-Pvt-Ltd/NxERP`, branch **`hybrid/phase-8-cutover`**. It contains every phase (1 to 8) plus the sign-up, themed pages and server guides. Written 2026-11-22. Read this first; every claim below says whether it was verified, and where.

## What NXDESK is

One platform with one sign-in and one front page (`nxdesk.nxsys.in`). Each product is its own site with its own database: NXERP (ERPNext) and Sria Helpdesk today, AIRA HRMS later. A small shared read database (a derived copy of a few reference fields such as customers and contacts, never authoritative) lets products see each other's reference data through an API. Products change each other's data only through the owner's command API. Details: `docs/architecture/overview.md`, `docs/adr/ADR-009-hybrid-database-architecture.md`.

## Domains and endpoints

| Name | What it serves | Status |
| --- | --- | --- |
| `https://nxdesk.nxsys.in` | the front page, the product list, sign-up, the one sign-in (identity site, `nxerp_site_role = identity`) | **to create** (DNS record, site, certificate: `deploy/baremetal/README.md`, step 4) |
| `https://helpdesk.nxsys.in` | Sria Helpdesk and all real data | live; new code not deployed yet |
| `https://nxerp.nxsys.in` | NXERP (ERPNext), no real data yet | DNS and site exist; new code not deployed yet |
| `https://aira.nxsys.in` | an AIRA app that already runs on the server (a separate codebase) | untouched; NXDESK shows "AIRA HRMS, Coming soon" at `/products/aira-hrms` |

### Public pages (every site that has the `nxerp` app)

`/` and `/nxerp/home` (front page), `/products`, `/products/<key>`, `/signup?app=<key>`, `/get-started?product=<key>`, `/welcome/<key>`, `/login`, `/update-password?key=...`, `/message`, `/404`, `/error`, `/platform`, `/security`, `/solutions`, `/roadmap`, `/company`, `/partners`, `/get-in-touch`. On the identity site `/` and `/products` list the connected apps and link to each app's own site. Full table with who may open what: `docs/architecture/routes.md`.

### Per product (the registry, `apps/nxerp_platform/nxerp/registry.py`)

| Product | Key | Where people land | Customer portal | Access role | Network paths gated |
| --- | --- | --- | --- | --- | --- |
| NXERP | `erpnext` | `/desk/home` | ERPNext website for `Customer` and `Supplier` | `NXERP Access: ERPNext` | `/desk`, `/app` |
| Sria Helpdesk | `helpdesk` | `/helpdesk/home` | `/helpdesk/my-tickets` | `NXERP Access: Helpdesk` (implies `Agent`, `Agent Manager`) | `/helpdesk` |
| AIRA HRMS | none yet | none | none | none | announced only; add it with `docs/architecture/adding-an-app.md` (one registry entry, one stack, one peer) |

After sign-in `/nxerp/go` decides where a person lands (`/nxerp/apps` is the launcher for people with two or more apps).

**India Compliance** (GST, e-invoice, e-way bill, TDS) is part of NXERP: pinned upstream release `v16.11.1` in `deploy/apps.json`, installed on the NXERP site only, covered by the ERPNext access grant. Verified on staging and with our test suites; **not yet installed on the live NXERP site** and filing against the GST portal is untested: `docs/runbooks/india-compliance.md`.

### Account and onboarding API (public, rate limited)

`POST /api/method/nxerp.api.account.sign_up` (email, full name, app; 10 per hour per IP; creates a customer-level Website User and emails the set-password link), `nxerp.api.onboarding.*` (first-run wizard), `nxerp.api.access_request.*` (request and decide access). Frappe's own `update_password` and `test_password_strength` serve the set-password page.

### App-to-app endpoints (never public; refused by the web entry on public names)

| Endpoint | Purpose | Who may call |
| --- | --- | --- |
| `nxerp.shared.feed.head / pull / ack / digest / snapshot / snapshot_by_ids` | an owner's outbox feed | role `NXERP Shared Feed Reader` (the projector) |
| `nxerp.shared.command.apply` | change another app's data (Helpdesk to NXERP), idempotent, run as the acting person | role `NXERP Command Caller`, mapped in site config `nxerp_command_callers` |
| `nxerp.federation.api.provision_user / deprovision_user / list_provisioned` | the identity site delivers grants to app sites | the provisioning service user |
| Read API `http://127.0.0.1:8210/v1/health`, `/v1/metrics` (JSON, or `?format=text`), `/v1/<entity>`, `/v1/<entity>/<id>` | read the shared layer; entities: `customer`, `contact`, `user_ref`, `org_unit`, `employee_ref`, `project_ref`, `ticket_summary` | per-app token and per-field grant |
| `helpdesk.integrations.shared.api.get_customer_card / update_customer / update_contact / get_status` | Helpdesk screens | signed-in Helpdesk agents |

## What was verified

| Claim | Evidence |
| --- | --- |
| The new code migrates the **real** Helpdesk database (53 tickets, 5 customers, 21 agents, 192 messages) without losing data | staging copy of the 2026-11-21 backup: `bench migrate` exit 0 in 6 s; counts identical; column renamed; roles created |
| The new code migrates the real NXERP database | staging copy: exit 0 in 7.6 s; login, signup, products and set-password pages answer |
| Shared layer works on the server's MariaDB (10.11.19) | 178 tests OK on 10.11.19 (5 skipped by design) |
| The server's Python has what the shared layer needs | read-only check: Python 3.14.9, `pymysql`, `werkzeug`, `yaml`, `requests` present in both bench environments |
| Sign-up creates the account and sends the verification email with a working link | local bench: account created, mail sent to the local test inbox; the link was missing its port and is fixed |
| Set-password, message, not-found and error pages are in the NXDESK look | screenshots and 4 unit tests; checked on 4 sites |
| Shared layer end to end (publish, project, read, command, outage banner) | staging, Phases 3 to 7 (see `docs/PROGRESS.md`) |
| Single sign-on id to app, grants revoked by the identity site | staging, Phase 6 rehearsal |
| Cutover tools (freeze, clone, reconcile, delta replay) | two clean rehearsals on a fake-data copy (`docs/architecture-isolation/rehearsal-1.md`, `rehearsal-2.md`) |
| Production has the settings signup mail needs | read-only: Helpdesk `mute_emails` 0, `host_name https://helpdesk.nxsys.in`, default outgoing Gmail account |

## What was NOT verified (do these, in this order)

1. **Gmail delivery from this code.** Production Helpdesk already has a working Gmail sender, but a real signup email has never been sent by the new code to a real inbox. Test after the deploy (`docs/runbooks/hostinger-deploy-steps.md`, step 6). The `nxerp` site and the identity site need their own outgoing Email Account.
2. **The production deploy itself** (never run). Backup, maintenance mode, deploy, migrate: `hostinger-deploy-steps.md`.
3. **The identity site on the server, its sign-in links to both apps, and the shared layer as server services.** Written (`deploy/baremetal/`) and tested in Docker and on MariaDB 10.11, never run on the server.
4. **Single sign-on after the real-data copy.** Verified in Phase 6; the staging link was erased when the real data replaced that site, so redo `phase-6-user-actions.md` 6.2 to 6.8 on the server and test with a fake user.
5. **Browser tests (Playwright) and `vue-tsc`.** Not run in this environment. 17 older page tests that fetch pages over HTTP fail on the test bench with a 404 on login (an environment problem that predates this work); the same pages were checked with curl and screenshots.
6. A real 2FA secret through the identity copy (no 2FA exists in production data today).

## Decisions and open items

| Item | State |
| --- | --- |
| Self-signup | open to anyone (owner, 2026-11-21); how to gate it again: `docs/features/signup-gate.md` |
| Where new accounts live (identity site or each app site) | open; today a sign-up started from the identity site's tile happens on the app's own site |
| Identity site as a second site on the `nxerp` bench | chosen for the first go-live (`deploy/baremetal/README.md`) |
| Separate restricted database server for finance data | postponed, NXERP holds no data yet |
| Removal of the old Helpdesk to ERPNext sync (8D) | written on a local branch, **do not merge before the decision point** (`docs/runbooks/isolation-cutover.md`, step 8.8) |
| Still the default Frappe look | `/me`, `/update-profile`, `/third_party_apps`, `/qrcode`, and the HTML of the welcome and reset emails |
| AIRA HRMS | announced only; the live `aira.nxsys.in` app is a different codebase |
| An older service `nxdesk-web` on the server | unrelated to this repository; ask before using the name `nxdesk` for anything else |

## Where to start

`README.md`, `CLAUDE.md` (the project rules), `docs/PROGRESS.md` (everything done, with evidence), then `docs/runbooks/hostinger-deploy-steps.md`, `docs/runbooks/domains-and-dns.md`, `deploy/baremetal/README.md`, `docs/runbooks/shared-layer-recovery.md`, `docs/runbooks/isolation-rollback.md`.
