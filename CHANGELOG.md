# Changelog

All notable changes to NXERP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Releases follow calendar versioning (`vYYYY.MM.PATCH`).
Each tag also generates a GitHub Release with auto-populated notes.

---

## [Unreleased]

### Added
- Initial monorepo scaffold: `apps/helpdesk/` (customized Frappe Helpdesk snapshot) and `apps/nxerp/` (NXERP branding Frappe app).
- NXERP login page (`nxerp/www/login.html` + `login.py`) extending Frappe's own login template with NXERP branding, dark-mode toggle, and accessible markup; all authentication logic delegated to Frappe.
- NXERP desk theme (`nxerp/public/css/nxerp-desk-theme.css`) applying the NXERP palette to Frappe Desk.
- NXERP branding module (`nxerp/branding.py`) setting site name and logos on install.
- `nxerp/hooks.py` declaring ERPNext and Helpdesk as required apps to enforce correct installation order.
- CI workflow (`ci.yml`): Python syntax check, Flake8, conflict-marker detection, frontend build, theme-token validation, hardcoded-colour audit, server tests with MariaDB, and conventional-commit lint.
- Security workflow (`security.yml`): Gitleaks secret scan, pip-audit, yarn audit (fail on high/critical), Semgrep with Frappe rules, and environment-file safety checks.
- Release workflow (`release.yml`): creates a GitHub Release with auto-generated notes on `v*.*.*` tags.
- CD staging workflow (`cd-staging.yml`): placeholder; deployment is not yet configured.
- Engineering governance: `CODEOWNERS`, `PULL_REQUEST_TEMPLATE.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `.editorconfig`, `.gitignore`, `.env.example`.
- Documentation: `docs/architecture.md`, `docs/branching.md`, `docs/deployment.md`, `docs/migration.md`, `docs/onboarding.md`, `docs/source-pins.md`.
- ERPNext source pinned at `v16.52.1`; Frappe source pinned at `v16.53.0` (inspections only, excluded from Git).

### Fixed
- Removed reference to non-existent `lint.yml` from README; lint jobs reside in `ci.yml` and `security.yml`.

### Known Issues / Not Yet Completed
- `yarn audit` reports 118 advisories (70 high, 1 critical) in transitive frontend dependencies. CI is configured to fail on this; remediation required before CI can pass.
- Staging deployment is not implemented. See `docs/deployment.md`.
- Bench installation and end-to-end tests have not been executed; a Linux environment with Frappe Bench is required.
- GitHub branch protections and repository secrets have not been configured.
- Push to `origin/main` pending write-access authorization on `Sria-Infotech-Pvt-Ltd/NxERP`.

---

[Unreleased]: https://github.com/Sria-Infotech-Pvt-Ltd/NxERP/compare/HEAD...HEAD
