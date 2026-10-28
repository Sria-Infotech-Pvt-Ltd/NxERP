# NXERP

NXERP is Sria Infotech's enterprise platform on the [Frappe Framework](https://github.com/frappe/frappe).

| Name | What it is |
| --- | --- |
| **NXERP** | The umbrella platform and brand: one login, one launcher, one identity |
| **ERPNext** | The ERP application inside NXERP. Keeps its own identity; never renamed |
| **Helpdesk** | A separate support / ticket application inside NXERP. Never "NXERP" |
| **Frappe Framework** | The underlying technology; not presented to business users as an application |
| **`nxerp` (this app)** | The platform app that lets the other apps feel like one product |

Future apps (HRMS, Project Management, Budget Management, ...) are **not installed** and are not shown anywhere.

> **Status: Phase 4 (release readiness), not released.** The `nxerp` app holds the registry, the access layer, the shared login, the router and the launcher. Nothing is pushed and CI has not run on GitHub. See [docs/PROGRESS.md](docs/PROGRESS.md), [docs/acceptance/acceptance-report.md](docs/acceptance/acceptance-report.md) and the [docs index](docs/README.md).

## One workspace, two repositories

Everything lives side by side in one folder; Helpdesk is one module of NXERP and keeps its own git history (ADR-001):

```
frapper sria/
  nxerp-platform/   this repo: platform app + deploy + docs   (company repo Sria-Infotech-Pvt-Ltd/NxERP)
  helpdesk/         Helpdesk module (company fork of frappe/helpdesk, incl. the NXERP login and palette)
```

`./deploy/dev/up.sh` mounts both: it installs the platform app from this folder and Helpdesk from `../helpdesk` (the branch currently checked out there), plus pinned ERPNext, so one stack runs the whole product.

## What this repository holds

```
nxerp/        the platform Frappe app (this repo root is the app, as bench expects)
deploy/       pinned versions, apps.json, dev stack and bootstrap (no secrets)
docs/         audit, research, ADRs, architecture, progress
.github/      CI, PR and issue templates
```

Frappe and ERPNext are **never vendored or copied here**; they are upstream tags pinned in `deploy/`. Helpdesk is a company fork with a documented minimal diff (see [ADR-001](docs/adr/ADR-001-repository-topology.md)).

## Responsibilities of the `nxerp` app (once built, Phase 2+)

- Resolve which apps a user may use (access follows the user's actual grants, never "what is installed")
- Own the shared shell: launcher, post-login routing, no-access page, platform branding
- Provide the one extension point other apps register with, so adding an app is cheap

## Non-responsibilities

- It does **not** contain ERPNext or Helpdesk code, and does not rename or fork them
- It does **not** replace Frappe authentication, sessions, roles or DocType permissions
- It does **not** import from other apps, and other apps must not import from it
- It is **not** the security boundary by hiding icons: enforcement is on the server
- It does **not** ship dev data (the seed script lives under `nxerp/tests/` and refuses to run outside developer mode)

## Quick start (dev)

Requires Docker with Compose v2 (Windows: run from Git Bash or WSL).

```bash
./deploy/dev/up.sh -d                       # builds a bench and a site; first run is slow
docker compose -p nxerp-dev logs -f bench   # wait for "ready:"
# then open http://nxerp.localhost:8100 (ERPNext Desk at /app, Helpdesk at /helpdesk)
```

Details, ports and how to seed fake users: [deploy/README.md](deploy/README.md).

## Contributing

Read [CLAUDE.md](CLAUDE.md) (project rules) and [CONTRIBUTING.md](CONTRIBUTING.md) (branches, commits, reviews).
