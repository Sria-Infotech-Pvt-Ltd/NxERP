# ADR-001: Repository topology and ownership

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** Phase 1 engineering (owner to ratify the open items below)

## Context

NXERP is an umbrella over Frappe, ERPNext, Helpdesk and future apps, maintained by 50+ developers. We need clear ownership boundaries, reproducible builds and a cheap way to add apps.

Verified state (2026-10-27):

- **FACT** `Sria-Infotech-Pvt-Ltd/NxERP` is public, default branch `main`, one commit ("Initial commit", README only). `git ls-remote` shows `refs/heads/main` and `refs/pull/1/*`. The account used for this work has `READ` permission only (`gh repo view ... viewerPermission`).
- **FACT** PR #1 "Integrate NXERP with ERPNext and Helpdesk" (head `codex/nxerp-integration`, 1,163 files, +363,590/-2) is open against `main`. It is the earlier integration attempt; it is **not** a base for this work and was not read or modified.
- **FACT** The Helpdesk customisations live in `Sriainfotech/Frappe-Help-Desk` (remote `company`), a *different GitHub owner* from the company organisation `Sria-Infotech-Pvt-Ltd`. Local `helpdesk/` has `origin` = `frappe/helpdesk` (upstream) and `company` = that fork; branch `feature/nxerp-login-page` @ `1c6981cc5`, 10 commits ahead of / 12 behind `origin/develop` (merge-base `58b82a6e2`).
- **FACT** Frappe apps are one repository per app: `bench get-app <url>` clones a repo whose root is the app (`telephony/pyproject.toml` + `telephony/telephony/`, same for ERPNext and Frappe).
- **FACT** A second, empty-history local repo exists at `frapper sria/NXERP/nxerp` (branch `master`, no commits, `origin` = NxERP) holding an earlier `nxerp` app with a login override (`apps/nxerp_platform/nxerp/www/login.*`, `nxerp/branding.py`). It was not used; its contents are Phase 2 input (see ADR-005).

## Options considered

1. **Polyrepo of upstream-shaped repos (chosen).** NxERP repo = `nxerp` platform app (repo root is the app) + `deploy/` + CI + docs. Helpdesk = company-owned fork with `upstream` remote and a minimal documented diff. Frappe/ERPNext = upstream tags pinned in `deploy/`, never vendored.
2. **Monorepo with subtrees** (Frappe, ERPNext, Helpdesk copied under one repo). Rejected: breaks `bench get-app` (needs an app at repo root), makes upstream security merges a manual subtree-merge exercise on ~4,000-file trees (`frappe` alone has 4,216 files), bloats history (the rejected PR #1 is the demonstration: 363k added lines), and gives 50+ developers one blast radius.
3. **Move Helpdesk customisations into the `nxerp` app** and run stock Helpdesk. Attractive (no fork) but not proven: the audit shows the customisation edits Helpdesk's own files (`helpdesk/hooks.py`, `desk/src/...` branding, `helpdesk/www/login.*`). Frontend branding inside the Helpdesk SPA cannot be overridden from another app without patching the bundle. Deferred as a long-term goal; not required for Phase 1.

## Decision

- **NxERP repo layout:** repo root is the `nxerp` Frappe app (`pyproject.toml`, `nxerp/` package) with `deploy/`, `docs/`, `.github/` alongside. Platform code, governance, CI, docs and the version pins live here.
- **Helpdesk** stays a company fork. It must live under the company organisation (open item 1), keep `upstream` = `https://github.com/frappe/helpdesk`, and carry a documented, minimal diff (`docs/audit/helpdesk-audit.md` lists it). Phase 1 pins the fork commit that exists on a remote today (`1c6981cc5`); ADR-002 sets the target base.
- **Frappe and ERPNext** are upstream tags pinned by commit in `deploy/versions.env` and `deploy/apps.json`. Never vendored or copied.
- **`telephony`** (a Helpdesk dependency) has no release tags (**FACT** `git ls-remote --tags`), so it is pinned by commit; forking it into the company org is recommended to remove the dependency on an unpinned upstream branch.
- **Ownership:** CODEOWNERS (placeholder teams) gates `nxerp/`, `deploy/`, `.github/`, `docs/adr/`.
- **PR #1** is left untouched; closing it is the owner's decision.

## Local workspace layout (added 2026-10-27)

The owner wants all code in one place. Decision: **one workspace folder, two repositories side by side**, not a monorepo: `nxerp-platform/` (this repo) and `helpdesk/` (the fork). The dev stack mounts both, so the whole product runs from one folder and one command, while upstream merges and ownership stay as decided above. Merging Helpdesk's ~1,100 tracked files into this repository remains rejected for the reasons in Option 2.

## Consequences

- Adding an app = one `deploy/apps.json` entry plus a registration in the platform (ADR-005); no code is copied.
- Upstream security fixes arrive by bumping a pin (Frappe/ERPNext) or by rebasing the fork on its `upstream` remote (Helpdesk).
- Two repos must be released together; the pin file is the contract.

## Open items for the owner

1. Move/fork Helpdesk into `Sria-Infotech-Pvt-Ltd` (currently `Sriainfotech`).
2. Grant write access (or a fork workflow) to whoever pushes `phase-1/foundation`; enable branch protection on `main`.
3. Create the GitHub teams named in CODEOWNERS or replace them.
4. Decide the fate of PR #1.
5. Confirm the licence for `nxerp` (`hooks.py` says `Proprietary` as a placeholder).
