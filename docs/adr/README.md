# Architecture decision log

Every decision that changes the architecture rules, the version pins, the access model or the routes is recorded as an ADR
and changed in the same pull request as the code (see [CONTRIBUTING.md](../../CONTRIBUTING.md)). ADR files are owned by the
architecture group in `CODEOWNERS`.

Statuses used: **Accepted** (in force), **Superseded** (replaced; the file says by what). An amendment is a separate file that
refines an Accepted ADR without changing its decision; read the ADR **and** its amendments together. Nothing here is
Proposed or Superseded today. "Accepted" records a decision, not that the owner has ratified every open item inside it.

| # | Title | Status | Decision in one line | Amendments |
| --- | --- | --- | --- | --- |
| [ADR-001](ADR-001-repository-topology.md) | Repository topology and ownership | Accepted (2026-10-27) | Polyrepo: this repo is the `nxerp` app (repo root is the app) plus `deploy/`, CI and docs; Helpdesk is a company fork with an `upstream` remote and a minimal documented diff; Frappe and ERPNext are upstream tags pinned by commit, never vendored. One local workspace folder holds both repos side by side | none. Open items for the owner are still open (Helpdesk fork under the company org, write access and branch protection, CODEOWNERS teams, PR #1, licence) |
| [ADR-002](ADR-002-version-matrix.md) | Version matrix and upstream update policy | Accepted (2026-10-27) | Frappe 16 line (`v16.53.0`), ERPNext `v16.52.1`, Python 3.14, Node 24, MariaDB 11.8, Redis 8.6; exact-commit pins in `deploy/versions.env` and `deploy/apps.json`; Helpdesk target is upstream `v1.31.0` plus the company commits, interim pin is the fork commit `1c6981cc5`; weekly upstream review, monthly batch updates, a new ADR for any major upgrade | none. Decision 5 ("the palette is uncommitted") is out of date: the palette is committed on the Helpdesk fork's branches (see [PROGRESS.md](../PROGRESS.md)); the interim Helpdesk pin and its re-pin are still open |
| [ADR-003](ADR-003-access-model.md) | Access model (authorisation, app visibility, landing) | Accepted (2026-10-27) | Hybrid: grants are Frappe roles (`NXERP Access: <App>`, assigned through Role Profiles) and stay the single source of truth; one thin resolver in `nxerp` derives apps = installed and registered and granted; a server-side gate on the `auth_hooks` slot turns "hidden" into "blocked"; `Administrator` always passes and errors fail closed for everyone else; customers keep Frappe's Website User model | [ADR-003 amendment 1](ADR-003-amendment-1.md): the registry is a declarative list in `nxerp` (not per-app hooks), implied roles (`Agent`, `Agent Manager` for Helpdesk), portal roles are not staff access, System Managers keep the Desk shell but not ERPNext data, no cache of our own, findings from Phase 2 (disabled accounts, customer data minimisation) |
| [ADR-004](ADR-004-route-map.md) | Route map, ownership and redirect safety | Accepted (2026-10-27) | `/login` (only one, owned by `nxerp`), post-login router `/nxerp/go`, launcher `/nxerp/apps`, `/nxerp/no-access`, `/helpdesk/home`, ERPNext at `/desk` (`/app` is a Frappe redirect); logout stays Frappe's; redirects are site-relative paths only, honoured only when the user may use the owning app | [ADR-004 amendment 1](ADR-004-amendment-1.md): rule 1 is **replaced in practice**: `routing.safe_target` is the redirect validator, not Frappe's `sanitize_redirect`; the login page points every sign-in at the router; the "All applications" row is a standard navbar item with a condition; the kill-switch `nxerp_stock_login`; the test-only third app; the 60 s site-config cache; the hyphenated-page controller rule; the full list of Helpdesk files touched. Read the amendment before relying on the original rule 1 |
| [ADR-005](ADR-005-code-placement-and-dependency-rules.md) | Where branding, login and launcher code lives; app dependency rules | Accepted (2026-10-27) | `nxerp` owns everything shared (login, router, launcher, no-access, branding, resolver); per-app code stays in the app; Helpdesk's title is "Helpdesk"; apps never import `nxerp` or each other and `nxerp` imports no app and declares no `required_apps`; `nxerp` is last in `deploy/apps.json`; enforced by `scripts/check_architecture.py` | Covered by ADR-003 amendment A1 (registry in `nxerp`, not a hook) and ADR-004 amendment 1 (upstream files touched). The checker now also verifies, when given the Helpdesk checkout (`--app-path`), that no app imports `nxerp` and that no platform code lives in an app; see [testing.md](../guides/testing.md) |
| [ADR-006](ADR-006-dev-environment.md) | Development environment and one-command bootstrap | Accepted (2026-10-27) | Docker Compose dev stack in `deploy/bootstrap/` (compose project `nxerp-dev`, ports 8100 and 9100): `./deploy/bootstrap/up.sh -d` builds a pinned bench and a site from `deploy/apps.json`, repo bind-mounted at `/workspace`, `nxerp` soft-linked; clone outside OneDrive; dev-only conveniences are guarded | none. Production images are a follow-up and were not claimed by this ADR |

## How to read the log

- Cite decisions as `ADR-004`, amendments as `ADR-004 amendment 1`, never by title alone.
- Where an original ADR and its amendment disagree, **the amendment wins**. The original text is kept unchanged so the history is honest.
- Findings that came from code or runs (not from a decision) live in [`../audit/`](../audit/bootstrap-evidence.md), [`../security/`](../security/phase2-review.md) and [`../PROGRESS.md`](../PROGRESS.md).

## Writing a new ADR

1. Copy the headings of an existing ADR: Status, Date, Context (with FACT / ASSUMPTION labels), Options considered, Decision, Consequences.
2. Number it next in sequence (`ADR-007-<slug>.md`). An amendment is `ADR-00N-amendment-M.md` and states what it amends and that the decision is unchanged.
3. Add a row here in the same pull request, and update the docs that cite the changed rule.
4. A change to a pin, an access rule, a route or an architecture rule is not merged without its ADR (or amendment).
