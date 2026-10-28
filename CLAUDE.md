# NXERP project rules

Rules for every contributor and every AI assistant working in this repository.

## Product identity (non-negotiable)

- **NXERP** = the umbrella platform and brand. **ERPNext** = the ERP app inside it, keeping its technical identity: never rename it NXERP and never treat Helpdesk as the ERP.
- **Helpdesk** = a separate support/ticket app inside NXERP. Helpdesk is never "NXERP".
- **Frappe Framework** = underlying technology, not shown to business users as an application.
- Future apps (HRMS, Project Management, Budget Management, ...) are **not installed**. Make adding them cheap; never build, mock or display them as if they exist.
- A unified experience is not merged code: do not copy apps into one package or rename upstream packages.

## Repositories

- This repo: `nxerp` platform app + `deploy/` + CI + docs. Frappe and ERPNext are upstream tags pinned in `deploy/`; never vendored.
- Helpdesk: company fork with an `upstream` remote and a minimal, documented diff.
- Do not build on, repair or copy from the rejected earlier integration tree (`NXERP CORE/`, and the code of PR #1 `codex/nxerp-integration`). It is evidence of what went wrong.

## Identity and access

- One login (Frappe's `/login`), one identity per person, no per-app credentials.
- Access follows the user's actual grants, never "what is installed".
- Reuse Frappe's roles, DocType permissions, User Permissions and desk access. Do not build an RBAC engine unless evidence shows Frappe cannot meet a requirement, and then add the thinnest layer (see ADR-003).
- Keep four things distinct: authentication (who), authorisation (what is allowed), application visibility (which apps are shown), routing (where the user goes after login).
- **Hiding an icon is not security.** Enforce on the server, including direct URLs and API calls. The frontend is never the security boundary.
- Customers get the restricted customer portal only: never Desk access or internal ticket data.

## Architecture rules

- Apps never import each other. The platform resolves apps through hooks and registries (ADR-005).
- `nxerp` declares no `required_apps`.
- Platform code goes in `apps/nxerp_platform/nxerp/`; app-specific code stays in that app's repo.
- Every patch is idempotent and listed in `patches.txt`; fixtures and migrations are versioned.
- Version pins live in `deploy/versions.env` and `deploy/apps.json`; changing one needs an ADR-002 update.

## Evidence and honesty

- Do not claim anything works unless you ran it and saw it work. Reports label statements FACT (verified, with evidence), ASSUMPTION or DECISION.
- A workflow file in git is not a working pipeline. State plainly what has and has not run on GitHub.
- Never claim a push or merge happened unless verified (`git ls-remote`, `gh pr view`).

## Git safety

- Never force-push or rewrite shared history. No direct pushes to `main`: use a branch and a PR.
- Never commit secrets, `.env` files, production config, customer data or personal data. Use fake data such as `user@example.test`.
- Short-lived branches, small commits (`type: summary`), PRs with required reviews on sensitive paths (CODEOWNERS).

## Code style

- Match the surrounding code: Frappe conventions, tabs in Python, ruff config in `pyproject.toml`.
- Comments only where the reason is not obvious from the code.

## Working method

Inspect real state, plan, implement in small commits, test, verify, document, report. Keep `docs/PROGRESS.md` current so the next session resumes from the repository.
