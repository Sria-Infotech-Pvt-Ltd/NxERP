# Code map: where each function lives

Paths are relative to the repository root.

| Function | Where |
| --- | --- |
| Shared login page (`/login`) | `apps/nxerp_platform/nxerp/www/login.html`, `login.py`; styles in `nxerp/public/nxerp_login/` |
| Post-login router (`/nxerp/go`) | `nxerp/www/nxerp/go.*`, `nxerp/routing.py` |
| Launcher (`/nxerp/apps`) and no-access page | `nxerp/www/nxerp/apps.*`, `no-access.html` + `no_access.py`, `nxerp/launcher.py` |
| App registry (which apps exist, tiles) | `nxerp/registry.py` |
| Access rules (who may enter which app) | `nxerp/access.py`; server-side gate `nxerp/enforcement.py` (hooks `auth_hooks`, `has_permission`, `after_request`) |
| Grant API and last-admin guard | `nxerp/api/access.py`, `nxerp/guard.py`, `nxerp/migration.py`, `nxerp/audit.py` |
| Install, roles, patches | `nxerp/install.py`, `nxerp/patches/`, `nxerp/patches.txt`, `nxerp/hooks.py` |
| Platform branding / palette | `nxerp/public/css/`, `nxerp/hooks.py` (`app_logo_url`, `website_context`) |
| Platform tests | `apps/nxerp_platform/nxerp/tests/` (unit and Frappe integration), `apps/nxerp_platform/browser-tests/` (Chromium) |
| Helpdesk backend (tickets, SLA, KB) | `apps/helpdesk/helpdesk/` (Python package): ticket doctype `helpdesk/helpdesk/doctype/hd_ticket/`, REST `helpdesk/api/ticket.py`, `comment.py`, `unseen.py`, hooks `helpdesk/hooks.py` |
| Helpdesk frontend (Vue SPA) | `apps/helpdesk/hd-frontend/` (`src/pages/ticket/`, `src/stores/`, `src/router/`, theme `src/theme/`) |
| Helpdesk realtime handlers | `apps/helpdesk/realtime/handlers.js` (name fixed by Frappe) |
| Helpdesk tests | backend `apps/helpdesk/helpdesk/**/test_*.py` and `helpdesk/tests/`; Playwright `apps/helpdesk/hd-e2e-tests/` |
| Deploy: pins | `deploy/apps.json`, `deploy/versions.env`, `deploy/check_pins.py` |
| Deploy: one-command dev install | `deploy/bootstrap/up.sh`, `bootstrap.sh`; compose `deploy/docker/compose/dev/` |
| Deploy: images and staging-like stack | `deploy/docker/` (Dockerfile, build.sh), `deploy/docker/compose/staging-like/`, ops scripts `deploy/scripts/`, env templates `deploy/env/` |
| Stand-alone stock Helpdesk quick start | `deploy/docker/helpdesk-local-dev/` |
| Checks and helpers | `scripts/` (architecture check, licences, upstream watch, theme build, CI stack) |
| Decisions, runbooks, security | `docs/adr/`, `docs/runbooks/`, `docs/security/` |
