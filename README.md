# NXERP — Company ERP Platform

> **Frappe / ERPNext + customized Helpdesk** — integrated, branded, and maintained by Sria Infotech Pvt. Ltd.

[![CI — Lint](https://github.com/Sria-Infotech-Pvt-Ltd/NxERP/actions/workflows/lint.yml/badge.svg)](https://github.com/Sria-Infotech-Pvt-Ltd/NxERP/actions/workflows/lint.yml)
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
│   ├── helpdesk/            ← company-customized Frappe Helpdesk (git subtree)
│   └── nxerp/               ← NXERP branding app
├── .github/
│   ├── workflows/
│   │   ├── ci.yml           ← Python lint + syntax + tests on every PR
│   │   ├── lint.yml         ← Commit lint, theme-token check, Semgrep
│   │   ├── security.yml     ← Secret scanning, dependency audit
│   │   └── cd-staging.yml   ← Deploy to staging (manual trigger)
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
│   └── onboarding.md
├── .editorconfig
├── .gitignore
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── CHANGELOG.md
└── README.md               ← this file
```

The upstream ERPNext repository is **not** vendored here. It is a regular Bench dependency pinned in `apps/nxerp/pyproject.toml` (or in the site's `apps.txt` / `common_site_config.json`). See [Architecture](docs/architecture.md).

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

**Frappe version:** `>=16.0.0-dev,<18.0.0` (per `helpdesk/pyproject.toml`)
**Python:** 3.14+
**Node:** 24 LTS
**Database:** MariaDB 10.6+

See [docs/architecture.md](docs/architecture.md) for full dependency matrix and upgrade strategy.

---

## Quick Start (Development)

> **Prerequisites:** Python 3.14, Node 24, Yarn, MariaDB 10.6, Redis.
> Use the Docker setup for a zero-config environment (see `frappe-helpdesk-docker/`).

```bash
# 1. Install bench
pip install frappe-bench

# 2. Create a new bench
bench init --frappe-branch version-16 ~/nxerp-bench
cd ~/nxerp-bench

# 3. Get apps (use this repository for helpdesk and nxerp)
bench get-app erpnext --branch version-16
bench get-app telephony
bench get-app helpdesk /path/to/nxerp-integration/apps/helpdesk
bench get-app nxerp /path/to/nxerp-integration/apps/nxerp

# 4. Create a dev site
bench new-site nxerp.localhost --db-root-password root --admin-password admin

# 5. Install apps (order matters: nxerp must be last)
bench --site nxerp.localhost install-app erpnext
bench --site nxerp.localhost install-app telephony
bench --site nxerp.localhost install-app helpdesk
bench --site nxerp.localhost install-app nxerp

# 6. Apply NXERP branding (only needed on a pre-existing site)
bench --site nxerp.localhost execute nxerp.branding.apply_branding

# 7. Start
bench start
```

The development site is then available at `http://nxerp.localhost:8000`.

---

## Production Installation

See [docs/deployment.md](docs/deployment.md) for the full procedure including:
- Pre-deployment checklist
- Database backup
- Migration steps
- Asset build
- Health check
- Rollback procedure

**Never run `bench migrate` on production without a verified backup.**

---

## Branch Strategy

| Branch | Purpose | Protected |
|--------|---------|-----------|
| `main` | Production-ready, deployed to nxerp.nxsys.in | ✅ Yes |
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
- Migrations and auth changes require senior review (see CODEOWNERS)
- Conventional Commits format for all commit messages

---

## Security

Report vulnerabilities privately via [SECURITY.md](SECURITY.md).

Do **not** open public issues for security findings.

---

## Release Process

See [docs/deployment.md](docs/deployment.md). Releases are tagged `vYYYY.MM.PATCH` (calendar versioning). A GitHub Release with auto-generated notes is created per tag.
