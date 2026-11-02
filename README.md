# NXERP — Company ERP Platform

> **Frappe / ERPNext + customized Helpdesk** — integrated, branded, and maintained by Sria Infotech Pvt. Ltd.

[![CI — Tests](https://github.com/Sria-Infotech-Pvt-Ltd/NxERP/actions/workflows/ci.yml/badge.svg)](https://github.com/Sria-Infotech-Pvt-Ltd/NxERP/actions/workflows/ci.yml)

---

## Table of Contents

1. [Overview](#overview)
2. [Repository Layout](#repository-layout)
3. [Architecture](#architecture)
4. [Quick Start (Development)](#quick-start-development)
5. [Production Installation](#production-installation)
6. [Branch Strategy](#branch-strategy)
7. [Contributing](#contributing)
8. [Security](#security)
9. [Release Process](#release-process)

---

## Overview

NXERP is the company's ERP platform built on the [Frappe](https://frappeframework.com/) ecosystem. It ships:

| App | Role |
|-----|------|
| **Frappe Framework** | Core web framework, authentication, ORM, scheduler |
| **ERPNext** | Finance, sales, purchase, inventory, HR, projects |
| **Helpdesk** (customized) | Customer support tickets, SLAs, Knowledge Base |
| **NXERP** (branding app) | Login page, desk theme, logo, favicon |

All four apps run on the **same Frappe site** (Bench installation). Authentication is unified through Frappe — there is no separate credential store.

---

## Repository Layout

```
nxerp-integration/           ← this repository
├── apps/
│   ├── frappe/              ← upstream framework (pinned; retrieved by CI/Bench)
│   ├── erpnext/             ← upstream ERPNext (pinned; retrieved by CI/Bench)
│   ├── telephony/           ← upstream Helpdesk dependency (retrieved by Bench)
│   ├── helpdesk/            ← company-customized Frappe Helpdesk snapshot
│   └── nxerp/               ← NXERP branding app
├── .github/
│   ├── workflows/
│   │   ├── ci.yml           ← Python lint + syntax + tests + commit lint + theme check on every PR
│   │   ├── security.yml     ← Secret scanning, dependency audit, Semgrep
│   │   ├── cd-staging.yml   ← Deploy to staging (manual trigger; not yet configured)
│   │   └── release.yml      ← Create GitHub Release from a version tag
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── CODEOWNERS
├── docs/
│   ├── architecture.md
│   ├── branching.md
│   ├── deployment.md
│   ├── migration.md
│   ├── onboarding.md
│   └── source-pins.md
├── .editorconfig
├── .gitignore
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── CHANGELOG.md
└── README.md               ← this file
```

The official ERPNext and Frappe source checkouts are available locally at `erpnext-source/` and `frappe-source/` for inspection and are excluded from Git. ERPNext is a Frappe app, not a Bench installation. The integration repo now contains the customized Helpdesk and NXERP Frappe apps. Runtime installation and end-to-end validation are still in progress.

---

## Architecture

```
Frappe Bench
├── apps/
│   ├── frappe          ← upstream (pinned tag)
│   ├── erpnext         ← upstream (pinned tag)
│   ├── telephony       ← upstream (required by helpdesk)
│   ├── helpdesk        ← this repo: apps/helpdesk/
│   └── nxerp           ← this repo: apps/nxerp/
└── sites/
    └── nxerp.nxsys.in/
```

**ERPNext source:** `v16.52.1` (`ade850bbd6a7412e9994a9637d2c5c713771632a`)
**Compatible Frappe range:** `>=16.50.0,<17.0.0` (ERPNext declaration); Frappe `v16.53.0` is within that range. Source-level match only; runtime compatibility is not yet tested.
**Python:** 3.14+ (as declared by ERPNext and the current Helpdesk checkout)
**Node:** 24 LTS
**Database:** MariaDB 10.6+

See [docs/architecture.md](docs/architecture.md) for full dependency matrix and upgrade strategy.

---

## Quick Start (Development)

> **Prerequisites:** Python 3.14, Node 24, Yarn, MariaDB, and Redis. The local Docker directory has not yet been validated as a full NXERP development environment.

```bash
# 1. Install bench
pip install frappe-bench

# 2. Create a new bench
bench init --frappe-branch v16.53.0 ~/nxerp-bench
cd ~/nxerp-bench

# 3. Retrieve the pinned upstream apps
bench get-app erpnext --branch v16.52.1
bench get-app telephony https://github.com/frappe/telephony.git
cd apps/telephony && git checkout 9447577500a25d242088398157b72c654fa34b20 && cd ../..

# 4. Install the integrated apps from this checkout
bench get-app helpdesk /path/to/nxerp-integration/apps/helpdesk
bench get-app nxerp /path/to/nxerp-integration/apps/nxerp

# 5. Create a dev site
bench new-site nxerp.localhost --db-root-password root --admin-password admin

# 6. Install apps (NXERP declares ERPNext and Helpdesk dependencies)
bench --site nxerp.localhost install-app erpnext
bench --site nxerp.localhost install-app telephony
bench --site nxerp.localhost install-app helpdesk
bench --site nxerp.localhost install-app nxerp

# 7. Apply NXERP branding (only needed on a pre-existing site)
bench --site nxerp.localhost execute nxerp.branding.apply_branding

# 8. Start
bench start
```

The installation procedure has not been validated; a working integrated site is not yet available.

---

## Deployment

The deployment environment and staging architecture have not been verified. This repository is not ready to deploy. See [docs/deployment.md](docs/deployment.md) for the prerequisites; do not run these instructions against the live site.

---

## Branch Strategy

| Branch | Purpose | Protection status |
|--------|---------|-----------|
| `main` | Intended release branch | Not verified/configured |
| `feature/<id>-<slug>` | New features | No |
| `fix/<id>-<slug>` | Bug fixes | No |
| `hotfix/<id>-<slug>` | Urgent production fixes | No |
| `release/<version>` | Release stabilization | When active |

See [docs/branching.md](docs/branching.md) for the full workflow and daily developer guide.

---

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

Key requirements:
- One PR per logical change
- All CI checks must pass
- At least one reviewer approval required
- Migrations and auth changes require designated senior/security review; actual reviewers must be assigned manually until CODEOWNERS is configured
- Conventional Commits format for all commit messages

---

## Security

Report vulnerabilities privately via [SECURITY.md](SECURITY.md).

Do **not** open public issues for security findings.

---

## Release Process

See [docs/deployment.md](docs/deployment.md). Releases are tagged `vYYYY.MM.PATCH` (calendar versioning). A GitHub Release with auto-generated notes is created per tag.
