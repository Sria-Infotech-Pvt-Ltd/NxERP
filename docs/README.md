# NXERP documentation index

Every document in `docs/`, by purpose. Start with the row that matches what you are doing. Statements in these documents are
labelled **FACT** (verified, with evidence), **ASSUMPTION** or **DECISION**; where a page says a thing was not verified, it was not.

| I want to... | Read |
| --- | --- |
| Get started on day one | [onboarding/day-1.md](onboarding/day-1.md) |
| Understand how the platform fits together | [architecture/overview.md](architecture/overview.md) |
| Know why something is the way it is | [adr/README.md](adr/README.md) (the decision log) |
| Add an app (HRMS, Project Management, ...) | [guides/how-to-add-an-app.md](guides/how-to-add-an-app.md) |
| Find out what is done and what is open | [PROGRESS.md](PROGRESS.md), [acceptance/acceptance-report.md](acceptance/acceptance-report.md) |
| Fix a login or environment problem | [runbooks/login-recovery.md](runbooks/login-recovery.md), [guides/troubleshooting.md](guides/troubleshooting.md) |

The project rules live in the repository root: [CLAUDE.md](../CLAUDE.md) (non-negotiable rules for people and AI assistants),
[CONTRIBUTING.md](../CONTRIBUTING.md) (branches, commits, reviews), [README.md](../README.md) (what NXERP is), and `CODEOWNERS`.

## Onboarding

| Document | Purpose |
| --- | --- |
| [onboarding/day-1.md](onboarding/day-1.md) | Day-1 developer onboarding: prerequisites, clone, bring up the dev stack, seed users, run the tests, make a change, open a PR, where to ask. Includes a record of following it from a clean clone |

## Architecture

| Document | Purpose |
| --- | --- |
| [architecture/overview.md](architecture/overview.md) | Components, request flow including the gate, sign-in flow and landing rules, login ownership and the kill-switch, the test harness, version matrix, repositories and branches, what is deliberately not built |
| [architecture/routes.md](architecture/routes.md) | Every route and endpoint the platform owns or depends on: who may open it, what happens otherwise; redirect safety; login flows |
| [architecture/access-admin.md](architecture/access-admin.md) | Managing application access: grant and revoke in Desk or by API, the administrator lockout guard, what a refused user sees, the denial log |
| [architecture/adding-an-app.md](architecture/adding-an-app.md) | The short reference for registering an app (the full checklist is [guides/how-to-add-an-app.md](guides/how-to-add-an-app.md)) |

## Architecture decision records

[adr/README.md](adr/README.md) is the log (number, title, status, decision, amendments). Read an ADR together with its amendments; the amendment wins where they differ.

| Document | Decision |
| --- | --- |
| [ADR-001](adr/ADR-001-repository-topology.md) | Repository topology and ownership (polyrepo; Helpdesk is a company fork; Frappe and ERPNext pinned, never vendored) |
| [ADR-002](adr/ADR-002-version-matrix.md) | Version matrix and upstream update policy |
| [ADR-003](adr/ADR-003-access-model.md), [amendment 1](adr/ADR-003-amendment-1.md) | Access model: roles are the grants; a thin resolver and a deny-only gate in `nxerp` |
| [ADR-004](adr/ADR-004-route-map.md), [amendment 1](adr/ADR-004-amendment-1.md) | Route map, ownership and redirect safety; what Phase 3 learned and every upstream file touched |
| [ADR-005](adr/ADR-005-code-placement-and-dependency-rules.md) | Where shared code lives; apps never import each other |
| [ADR-006](adr/ADR-006-dev-environment.md) | Dev environment: the Docker Compose stack and one-command bootstrap |

## Guides

| Document | Purpose |
| --- | --- |
| [guides/how-to-add-an-app.md](guides/how-to-add-an-app.md) | The checklist for adding an app, with a test (`apps/nxerp_platform/nxerp/tests/test_add_app_checklist.py`) that exercises it |
| [guides/coding-standards.md](guides/coding-standards.md) | Python (tabs, ruff), no cross-app imports, comments, error handling, hyphenated `www` pages, commits |
| [guides/testing.md](guides/testing.md) | The test layers and how to run each, the fresh-site harness, the traps, the flaky-test policy |
| [guides/security-guidelines.md](guides/security-guidelines.md) | Server-side enforcement, redirect safety, secrets, logging without personal data, the review checklist |
| [guides/release-process.md](guides/release-process.md) | Versioning, release candidates, tags, changelog, rollback (concept) |
| [guides/troubleshooting.md](guides/troubleshooting.md) | Real problems met so far, with cause and fix |

## Security

| Document | Purpose |
| --- | --- |
| [security/phase2-review.md](security/phase2-review.md) | Threat-by-threat review of the access layer, each item mitigated with a test or accepted with a reason |
| [security/phase2-coverage.md](security/phase2-coverage.md) | Every enforcement surface, what enforces it, and the test that proves it |
| [security/phase2-matrix.md](security/phase2-matrix.md) | The persona x surface matrix produced by the test suite |
| [security/shared-set.md](security/shared-set.md) | What the app gate deliberately does not cover (Frappe core DocTypes, `frappe.*` methods) |

## Audit, research and evidence

| Document | Purpose |
| --- | --- |
| [audit/bootstrap-evidence.md](audit/bootstrap-evidence.md) | What was executed and observed when the dev platform was first built: tooling, bootstrap log, site checks, tests, the access baseline |
| [audit/helpdesk-audit.md](audit/helpdesk-audit.md) | Facts-only audit of the Helpdesk fork |
| [research/frappe-access-and-routing.md](research/frappe-access-and-routing.md) | Entry point of the research on how Frappe, ERPNext and Helpdesk authenticate, authorise, route and build launcher tiles |
| [research/part-1-authentication-redirect-launcher.md](research/part-1-authentication-redirect-launcher.md) | Authentication, user types, post-login routing, the launcher |
| [research/part-2-permissions-and-enforcement.md](research/part-2-permissions-and-enforcement.md) | Permissions, enforcement surfaces, the coverage table |
| [evidence/phase3/](evidence/phase3/) | Screenshots written by the browser suite (login, launcher, no-access, flows) |

## Runbooks (operating the platform)

| Document | Purpose |
| --- | --- |
| [runbooks/login-recovery.md](runbooks/login-recovery.md) | People cannot sign in or the login page is broken: the kill-switch, Administrator password reset, locked accounts, a break-glass System Manager |
| [runbooks/release.md](runbooks/release.md) | Cutting a release (the procedure behind [guides/release-process.md](guides/release-process.md)) |
| [runbooks/deploy.md](runbooks/deploy.md) | Deploying, verifying and rolling back an environment |

Further runbooks appear in [runbooks/](runbooks/) as the deployment owners add them. The build, environments, scripts and the staging-like stack are described in [../deploy/README.md](../deploy/README.md) and [../deploy/env/README.md](../deploy/env/README.md).

## Governance

| Document | Purpose |
| --- | --- |
| [governance/ownership.md](governance/ownership.md) | Who owns which part of the platform and who reviews what |
| [governance/branch-protection.md](governance/branch-protection.md) | The branch protection that must be enabled on `main`, and how to check it |
| [governance/contribution-policy.md](governance/contribution-policy.md) | How changes are proposed, reviewed and merged |
| [governance/owner-action-list.md](governance/owner-action-list.md) | What only the repository owner can do (access, teams, branch protection, publishing the branches), in priority order |

## Acceptance

| Document | Purpose |
| --- | --- |
| [acceptance/acceptance-report.md](acceptance/acceptance-report.md) | The release-readiness acceptance report: what was checked, with what result, and what was not verified |
| [PROGRESS.md](PROGRESS.md) | Phase-by-phase status and the resume point for the next session |

## Keeping this index honest

A new document is added here in the same pull request that creates it. A document that is out of date is fixed or marked so at its top, not left to mislead. Links in this index
to pages owned by other work streams (governance, runbooks, acceptance) are links to files that are written there; if one is missing in your checkout, it has not landed yet.
docs/restructure/ : the pre-work audit/plan (RESTRUCTURE_PLAN.md) and the baseline logs.
