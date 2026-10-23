# NXERP Architecture

## Overview

NXERP is a customized ERP platform built on the [Frappe](https://frappeframework.com/) ecosystem. It consists of four Frappe apps installed on a single Frappe site managed by [Frappe Bench](https://frappeframework.com/docs/user/en/bench).

---

## Application Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    Frappe Bench                             │
│  ~/nxerp-bench/                                             │
│                                                             │
│  apps/                                                      │
│  ├── frappe          Framework (auth, ORM, scheduler, UI)   │
│  ├── erpnext         Finance, sales, HR, inventory          │
│  ├── telephony       Call integration (required by HD)      │
│  ├── helpdesk        Customer support + custom branding     │
│  └── nxerp           Login page + desk theme + branding     │
│                                                             │
│  sites/                                                     │
│  └── nxerp.nxsys.in/                                       │
│      ├── site_config.json  (NOT in version control)        │
│      ├── apps.txt           (installed app list)            │
│      └── ...                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Source Compatibility (verified 2026-10-23)

| App | Source | Pin Strategy |
|-----|--------|-------------|
| `frappe` | upstream | `v16.53.0` (`e8d41dd0061a32ee781caefe7d0b0d2bb7c15362`); satisfies ERPNext's declared `>=16.50.0,<17.0.0` |
| `erpnext` | upstream | `v16.52.1` (`ade850bbd6a7412e9994a9637d2c5c713771632a`), checked out at `erpnext-source/` |
| `telephony` | upstream | `>=0.0.1,<1.0.0` |
| `helpdesk` | **this repo** `apps/helpdesk/` | company branch (`main`) |
| `nxerp` | **this repo** `apps/nxerp/` | company branch (`main`) |

> These are compatible source declarations, not a validated installation. ERPNext is a Frappe app; running NXERP requires Bench, Frappe, its services, and the other apps. Do not deploy `develop`.

---

## Authentication Architecture

**Single Frappe session for all apps.**

```
Browser
  │
  ▼
/login  ──rendered by──►  nxerp/www/login.html
                           (extends frappe/www/login.html)
                           (the Helpdesk legacy copy is retained outside www/)
  │
  ▼  POST /api/method/login
Frappe authentication layer
  ├── Validates credentials against Frappe User doctype
  ├── Creates server-side session cookie (HTTP-only, Secure)
  └── Redirects to /app (Frappe Desk) or /helpdesk (Helpdesk)

/helpdesk  ──requires──►  Frappe session (same cookie)
/app       ──requires──►  Frappe session (same cookie)
```

**No second login when switching between ERPNext Desk and Helpdesk.** Both check the same Frappe session.

**Custom auth hook (`helpdesk/auth.py`):** When `block_endpoints` is set in site config, the Helpdesk auth hook restricts non-system users to the explicitly allowed API paths. This is additive — Frappe's own permission checks remain in force.

---

## Login Page Design

The custom NXERP login page works as follows:

1. **`apps/nxerp/nxerp/www/login.html`** is canonical. `required_apps` makes NXERP depend on ERPNext and Helpdesk so its route is loaded after them.
2. It extends `frappe/www/login.html` — form, session creation, 2FA, social login, and password recovery remain Frappe's own code.
3. The old Helpdesk login template/context are retained under `apps/helpdesk/legacy_reference/`, outside `www/` so they cannot register a competing route. Helpdesk customer portal routes remain in place.
4. Login CSS and generated theme are served from `apps/nxerp/nxerp/public/css/`; logos, fonts, and favicon are served from `apps/nxerp/nxerp/public/`.
5. `apps/nxerp/nxerp/www/login.py` calls Frappe's stock context helper and only adds branding context.

---

## Repository Layout

```
nxerp-integration/
├── apps/
│   ├── helpdesk/            ← Frappe Helpdesk, company-customized
│   │   ├── helpdesk/        ← Python app package
│   │   │   ├── auth.py      ← Auth hook (endpoint allowlist)
│   │   │   ├── hooks.py     ← Frappe app hooks
│   │   │   ├── nxerp_branding.py  ← Branding application script
│   │   │   ├── integrations/erpnext/  ← ERPNext event handlers
│   │   │   └── legacy_reference/ ← Historical login source, not routable
│   │   └── desk/            ← Vue/Vite frontend
│   └── nxerp/               ← NXERP branding app
│       └── nxerp/
│           ├── hooks.py     ← Logo, CSS, required apps, after_install hook
│           ├── branding.py  ← apply_branding() script
│           └── www/login.*  ← Login page override (installed last)
├── .github/
│   ├── workflows/
│   │   ├── ci.yml          ← Lint + tests on PR
│   │   ├── security.yml    ← Secrets, CVEs, Semgrep
│   │   ├── cd-staging.yml  ← Staging deploy on main push
│   │   └── release.yml     ← GitHub Release on tag
│   ├── CODEOWNERS
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
├── docs/
│   ├── architecture.md     ← This file
│   ├── branching.md
│   ├── deployment.md
│   ├── migration.md
│   └── onboarding.md
├── .editorconfig
├── .gitignore
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
└── README.md
```

---

## ERPNext Integration

The Helpdesk app integrates with ERPNext through `helpdesk/integrations/erpnext/`. The integration handles:

| File | Purpose |
|------|---------|
| `customer.py` | Mirror ERPNext Customer → HD Customer on insert/update/rename/delete |
| `user_permission.py` | Sync User Permissions affecting Helpdesk access |
| `doc_share.py` | Handle DocShare events for Helpdesk-related sharing |
| `mirror_sync.py` | Bidirectional sync utilities |
| `api.py` | API endpoints for ERPNext-specific Helpdesk data |
| `utils.py` | Shared helpers |

These integrations are registered via `doc_events` in `helpdesk/hooks.py`.

---

## Helpdesk DocTypes

Custom DocTypes are prefixed `HD_`:

| DocType | Purpose |
|---------|---------|
| HD Ticket | Core support ticket |
| HD Ticket Activity | Timeline events |
| HD Ticket Comment | Agent/customer comments |
| HD Ticket Status | Configurable statuses |
| HD Ticket Priority | Priority levels |
| HD Ticket Type | Ticket categorization |
| HD Ticket Template | Ticket forms |
| HD Agent | Agent profile |
| HD Team | Agent teams |
| HD Customer | Linked customer |
| HD Service Level Agreement | SLA policies |
| HD Settings | Global Helpdesk settings |
| HD Article / HD Article Category | Knowledge Base |
| HD Saved Reply | Canned responses |

---

## Upgrade Strategy

### Frappe / ERPNext Upstream Upgrades

1. Create a `chore/upgrade-frappe-v17` branch
2. Update the version pin in `apps/helpdesk/pyproject.toml`
3. Run tests on a staging bench
4. Review upstream changelogs for breaking changes in:
   - `frappe.www.login` (login page template)
   - `frappe.auth` (authentication flows)
   - DocType schema changes
   - Hook API changes
5. Update the `NXERP` login page template if the base template changed
6. Open a PR with test evidence; require senior review
7. Deploy to staging, verify, then promote to production

### Never auto-upgrade upstream dependencies on production without staging validation.

---

## Deployment Model

The deployment architecture for `nxerp.nxsys.in` has not been independently verified. `frappe-helpdesk-docker/` contains a Docker Compose file, but that alone does not establish production architecture. Treat the site as production; do not deploy or migrate against it.

See [deployment.md](deployment.md) for the full procedure.
