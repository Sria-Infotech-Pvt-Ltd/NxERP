# ADR-007: One repository with `apps/`, `deploy/`, `docs/`

- **Status:** Accepted (owner approved the target hierarchy). Supersedes the "polyrepo" decision and the local-workspace
  section of ADR-001.
- **Date:** 2026-10-28

## Decision

`apps/nxerp_platform` (Frappe app `nxerp`) and `apps/helpdesk` (company Helpdesk, snapshot of the fork) live in this
repository. Frappe and ERPNext stay pinned upstream in `deploy/` and are never vendored.

## What changes because of it

- `deploy/apps.json`: entries with a `path` live here; entries with a `url` are pinned upstream commits.
- `bench get-app <repo url>` cannot install a sub-folder, so the dev bootstrap soft-links the platform app and installs a
  git snapshot copy of Helpdesk (its frontend needs its real path inside `apps/`); the Docker build copies both folders.
- Helpdesk's own `.github/` is kept but inert (GitHub reads workflows only at the root).
- The app package name stays `nxerp`; only folders were renamed.

## Risks accepted

Helpdesk (AGPL-3.0) and the platform (licence placeholder) share a public repository: needs professional review.
Helpdesk history is not imported. The CI and image-build changes have not run on GitHub.
