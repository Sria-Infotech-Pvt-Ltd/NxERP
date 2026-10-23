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

## Pinned Versions

| App | Source | Pin Strategy |
|-----|--------|-------------|
| `frappe` | upstream | `>=16.0.0-dev,<18.0.0` (per helpdesk `pyproject.toml`) |
| `erpnext` | upstream | latest stable tag matching Frappe version |
| `telephony` | upstream | `>=0.0.1,<1.0.0` |
| `helpdesk` | **this repo** `apps/helpdesk/` | company branch (`main`) |
| `nxerp` | **this repo** `apps/nxerp/` | company branch (`main`) |

> **Upgrading Frappe/ERPNext:** Pin to a tested tag in `bench/apps.txt` or the site's `common_site_config.json`. Never pull `develop` on production.

---

## Authentication Architecture

**Single Frappe session for all apps.**

```
Browser
  │
  ▼
/login  ──rendered by──►  nxerp/www/login.html
                           (extends frappe/www/login.html)
                           (helpdesk/www/login.html is an alias)
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

1. **`nxerp/www/login.html`** is the canonical login page (installed last, so it takes priority).  
   It extends `frappe/www/login.html` — the form, session creation, 2FA, social login, and forgot-password flows are all the framework's own code.
2. **`helpdesk/www/login.html`** is an identical extension — it provides the same design when Helpdesk is the last installed app.  
   Both files call `frappe_login_context()` and only add NXERP layout and CSS.
3. **CSS** lives in `helpdesk/public/nxerp_login/css/nxerp-login.css` and `nxerp-theme.css`.
4. **Brand assets** live in `helpdesk/public/nxerp_login/images/`.
5. **`login.py`** (both apps) only sets branding context variables — it does not reimplement authentication.

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
│   │   │   ├── public/nxerp_login/   ← Login CSS, fonts, images
│   │   │   └── www/login.*  ← Custom login page
│   │   └── desk/            ← Vue/Vite frontend
│   └── nxerp/               ← NXERP branding app
│       └── nxerp/
│           ├── hooks.py     ← Logo, CSS, after_install hook
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

The current production deployment at `nxerp.nxsys.in` uses **Frappe Bench on a managed server** (confirmed from `frappe-helpdesk-docker/` and the deployment architecture). Docker is available for local development.

See [deployment.md](deployment.md) for the full procedure.
