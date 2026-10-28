# Ownership

Who is accountable for what. **People are not named here: every "Owner" below is a role to be filled by the repository owner**
(`[to be named]`). The GitHub teams in `CODEOWNERS` are placeholders and are not known to exist
(see [owner-action-list.md](owner-action-list.md)). Ownership means: you review changes in that area, you answer when it breaks, and you
keep its docs and tests current. It does not mean you are the only one allowed to change it.

## Matrix

| Area | Owner role (team placeholder) | Owns (paths / things) | Reviews | On call for |
| --- | --- | --- | --- | --- |
| **Platform** (`nxerp` app) | Platform lead (`nxerp-platform`) | `nxerp/` (registry, launcher, branding, hooks, patches), `scripts/`, ADR-005 rules, the app-addition process | every change under `nxerp/`; any app registering with the platform | login/launcher/router regressions, patch failures |
| **ERPNext integration** | ERP integration lead (`nxerp-platform` until a separate team exists) | how ERPNext is installed and pinned (`deploy/apps.json` entry), the ERPNext smoke test, ERPNext-facing enforcement rules, grant migration for ERPNext users | pins of `erpnext` and `payments`; changes that touch ERPNext DocType permissions | ERPNext upgrade rehearsal, "ERP user cannot see their app" |
| **Helpdesk** | Helpdesk lead (`nxerp-platform` until a separate team exists) | the company fork (separate repo, minimal documented diff vs upstream `v1.31.0`), its pin in `deploy/apps.json`, `helpdesk-regression`, customer-portal behaviour | the Helpdesk pin; any platform change that alters portal/customer access | Helpdesk regression, fork rebases onto upstream releases |
| **Security** | Security lead (`nxerp-security`) | access model (ADR-003), `nxerp/{enforcement,access,guard,routing}.py`, `www/login.*`, `patches/`, `.gitleaks.toml`, dependency/licence policy, `docs/security/`, advisories triage (`upstream-watch`) | all sensitive paths in CODEOWNERS; every exception to the licence or audit policy | incident response lead, secret rotation, advisory SLAs |
| **Release & deploy** | Release manager (`nxerp-devops`) | `.github/`, `deploy/`, `docs/runbooks/`, releases/tags, GitHub Environments, registry, backups, hosts | CI/CD changes, runbook changes, pin bumps (with ADR-002 owner) | releases, deploys, rollbacks, backup/restore drills |
| **Architecture** | Architecture owner (`nxerp-architecture`) | `docs/adr/`, `docs/architecture/`, the dependency rules | ADRs; anything that changes a rule in CLAUDE.md | disputes between areas |
| **Maintainers** | Repository owner (`nxerp-maintainers`) | `CLAUDE.md`, `CONTRIBUTING.md`, `CODEOWNERS`, branch protection, org/team administration | governance changes | access to GitHub admin (the only people who can apply `docs/governance/apply-branch-protection.sh`) |

Rules of thumb: one area has one accountable role; a person may hold several roles while the team is small, but a PR is never approved
only by its author. A change that crosses areas (e.g. a Helpdesk pin that changes access) needs a reviewer from each.

## Escalation

1. Area owner. 2. Architecture owner (design disputes) or Security lead (anything with data exposure). 3. Repository owner.
Incidents follow [docs/runbooks/incident-response.md](../runbooks/incident-response.md).

## Template: ownership entry for a new app

Copy into the matrix above when an app is approved. **None of HRMS, Project Management or Budget Management is installed, built or
approved today; these are blanks to fill, not commitments.**

```markdown
| **<App name>** | <App> lead (`nxerp-<app>`) | its repo (`<org>/<repo>`), its pin in `deploy/apps.json`, its roles and DocType permissions, its tests, `<app>-regression` CI job | the pin; the platform registration | <app>-specific regressions, upgrade rehearsal |
```

```text
# CODEOWNERS block (the team must exist first)
/docs/apps/<app>.md        @Sria-Infotech-Pvt-Ltd/nxerp-<app> @Sria-Infotech-Pvt-Ltd/nxerp-architecture
```

Checklist to add an app (ADR-005; details in `docs/architecture/adding-an-app.md`):

1. Decision recorded: ADR (or ADR-002 update) naming the app, why, owner role, upstream/fork, licence review.
2. Pinned in `deploy/apps.json` at an exact commit, before `nxerp` (nxerp stays last). `python3 -I deploy/check_pins.py` passes.
3. Registered with the platform through the registry extension point; **no import** between the app and `nxerp` or other apps.
4. Access roles added to the access model with server-side enforcement and a test that a user without the grant cannot reach the app by
   URL or API (persona x surface matrix extended).
5. CI: a `<app>-regression` job (the app's own suite on the stack) added to `ci.yml` and to the `needs:` list of `ci-gate`.
6. Dependency audit and licence check cover the app's Python and JS dependencies (they read `deploy/apps.json`).
7. Runbooks mention the app: backup/restore needs no change (one site), `migration-planning.md` lists its upgrade risks.
8. Only then: launcher tile, docs for users. Until the app is installed and granted, nothing about it is shown to anyone.

### Per-app starter entries (fill in; do not publish before the app exists)

| App | Starting point | Open questions the owner must answer first |
| --- | --- | --- |
| HRMS | `frappe/hrms` at a tag matching the Frappe line | licence, personal-data handling (HR data is sensitive), who may see which employee records |
| Project Management | decide: ERPNext Projects module vs a separate app | does it need a separate app at all; customer-visible parts |
| Budget Management | decide: ERPNext budgets vs a custom app | finance data classification, approval workflow owner |
