# Developer Onboarding Guide

Welcome to the NXERP engineering team. This guide gets you from zero to a running local development environment.

---

## Prerequisites

Install the following before starting:

| Tool | Minimum Version | Notes |
|------|---------------|-------|
| Python | 3.14 | Use `pyenv` or the system package manager |
| Node.js | 24 LTS | Use `nvm` or `fnm` |
| Yarn | 1.x | `npm install -g yarn` |
| MariaDB | 10.6 | Or use Docker (see below) |
| Redis | 6+ | Or use Docker |
| Git | 2.35+ | |

> **Tip:** Use the Docker Compose setup in `frappe-helpdesk-docker/` if you want to skip manual dependency installation.

---

## Repository Setup

### 1. Clone the integration repository

```bash
git clone https://github.com/Sria-Infotech-Pvt-Ltd/NxERP.git nxerp-integration
cd nxerp-integration
```

### 2. Configure your Git identity

```bash
git config user.name "Your Name"
git config user.email "you@sriainfotech.com"
```

### 3. Set up commit signing (recommended)

Follow the [GitHub guide to signing commits](https://docs.github.com/en/authentication/managing-commit-signature-verification) with a GPG key.

---

## Local Bench Setup

### Option A: Manual Bench

```bash
# Install bench
pip install frappe-bench

# Create a new bench with Frappe v16
bench init --frappe-branch version-16 ~/nxerp-bench
cd ~/nxerp-bench

# Get upstream dependencies
bench get-app erpnext --branch version-16
bench get-app telephony

# Link the company apps from your clone
bench get-app helpdesk /path/to/nxerp-integration/apps/helpdesk
bench get-app nxerp /path/to/nxerp-integration/apps/nxerp

# Create a local development site
bench new-site nxerp.localhost \
  --db-root-password root \
  --admin-password admin

# Install apps (ORDER MATTERS — nxerp last)
bench --site nxerp.localhost install-app erpnext
bench --site nxerp.localhost install-app telephony
bench --site nxerp.localhost install-app helpdesk
bench --site nxerp.localhost install-app nxerp

# Apply NXERP branding
bench --site nxerp.localhost execute nxerp.branding.apply_branding

# Start everything
bench start
```

Site is now at: `http://nxerp.localhost:8000`  
Login: `Administrator` / `admin`

### Option B: Docker Compose

```bash
cd frappe-helpdesk-docker
# Edit init.sh if needed to point to your cloned apps
docker compose up
```

---

## Frontend Development

The Helpdesk frontend (Vue 3 + Vite) lives in `apps/helpdesk/desk/`:

```bash
cd apps/helpdesk/desk
yarn install

# Development server with hot reload
yarn dev

# Build for production
yarn build

# Theme token validation
yarn theme:check
yarn theme:audit
```

The Vite dev server proxies API calls to your local Frappe bench.

---

## Running Tests

### Python server tests

```bash
cd ~/nxerp-bench

# All Helpdesk tests
bench --site nxerp.localhost run-tests --app helpdesk

# Specific test module
bench --site nxerp.localhost run-tests \
  --module helpdesk.integrations.erpnext.test_erpnext_integration

# With coverage
bench --site nxerp.localhost run-tests --app helpdesk --coverage
```

### Pre-commit hooks (strongly recommended)

```bash
cd apps/helpdesk
pip install pre-commit
pre-commit install
```

This runs linting automatically before every commit.

---

## Understanding the Codebase

### Login Page

The NXERP login page works by extending the Frappe framework's own login template:

```
frappe/www/login.html         ← upstream (never edit)
        ↓ extends
nxerp/www/login.html          ← NXERP layout + CSS, no auth logic
helpdesk/legacy_reference/    ← old login kept for reference; not routable
```

Authentication logic is 100% in the Frappe framework. The login pages only change the visual presentation.

### Auth Hook

`helpdesk/auth.py` is registered as `auth_hooks` in `hooks.py`. When `block_endpoints` is set in `site_config.json`, it restricts non-system users to specific API paths. This is additive — Frappe's own permission checks still run.

### ERPNext Integration

`helpdesk/integrations/erpnext/` contains event handlers that sync ERPNext data (Customers, User Permissions, DocShares) into Helpdesk. These fire via `doc_events` in `hooks.py`.

### Helpdesk DocTypes

All custom DocTypes are in `helpdesk/helpdesk/doctype/` and prefixed with `HD_`. Frappe handles migrations automatically when you run `bench migrate`.

---

## Common Tasks

### Create a new Helpdesk API endpoint

```python
# In helpdesk/helpdesk/api/my_module.py

import frappe

@frappe.whitelist()
def my_endpoint(ticket_id: str) -> dict:
    # frappe.only_for(["Agent", "Agent Manager"])  # role guard if needed
    frappe.has_permission("HD Ticket", throw=True)
    # ... implementation
```

Register in `helpdesk/helpdesk/api/__init__.py` or call via `frappe.call("helpdesk.api.my_module.my_endpoint")`.

### Add a patch (database migration)

```python
# In helpdesk/helpdesk/patches/v1_0/my_patch.py

import frappe

def execute():
    """Describe what this patch does and why."""
    if not frappe.db.has_column("HD Ticket", "new_field"):
        frappe.db.add_column("HD Ticket", "new_field", "varchar(140)", default="")
    frappe.db.commit()
```

Register it in `helpdesk/helpdesk/patches.txt`:
```
helpdesk.patches.v1_0.my_patch
```

Patches must be idempotent (safe to re-run).

---

## Getting Help

- **Slack:** `#nxerp-dev` for day-to-day questions
- **GitHub Issues:** for bugs and feature requests
- **GitHub Discussions:** for architecture questions
- **Frappe docs:** https://frappeframework.com/docs/
- **ERPNext docs:** https://docs.erpnext.com/

When asking for help, include:
1. Your bench version (`bench version`)
2. The error message and full traceback
3. The file and line number

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| `bench start` fails | Check `logs/` for Gunicorn/Worker errors; run `bench doctor` |
| Login page shows Frappe branding | `nxerp` app not installed last; reinstall with correct order |
| `migrate` fails | Check `logs/frappe.log`; most patches have descriptive errors |
| Frontend 404 on `/helpdesk` | Rebuild assets: `bench build --app helpdesk` |
| Import error on `helpdesk.integrations.erpnext` | ERPNext not installed; the integration is optional if ERPNext is absent |
| Pre-commit fails on `ruff` | Run `ruff check --fix apps/helpdesk apps/nxerp` |
