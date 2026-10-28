# NXERP architecture overview

Status: Phase 1. Solid boxes exist today; dashed boxes are Phase 2+ and are **not built**.

```mermaid
flowchart TB
  user([Browser: employee / agent / manager / customer])

  subgraph NXERP["NXERP platform (one site, one login, one identity)"]
    direction TB
    subgraph PLAT["nxerp  (platform app, this repo)"]
      scaffold["Scaffold only in Phase 1<br/>hooks.py, module 'NXERP Platform'"]
      resolver["Access resolver / launcher / post-login router<br/>(Phase 2, ADR-003, ADR-004)"]:::future
    end
    subgraph APPS["Applications"]
      erp["ERPNext<br/>ERP app, keeps its identity<br/>/app/..."]
      hd["Helpdesk<br/>support app (company fork)<br/>/helpdesk/..."]
      later["HRMS, Project Mgmt, Budget Mgmt, ...<br/>NOT installed"]:::future
    end
    subgraph FW["Frappe Framework (technology, not shown as an app)"]
      auth["Authentication & sessions<br/>/login"]
      perm["Roles, DocType permissions,<br/>User Permissions, desk access"]
      api["/api/method, /api/resource,<br/>files, realtime"]
    end
  end

  db[("MariaDB 11.8")]
  redis[("Redis cache / queue")]

  user --> auth
  user --> erp
  user --> hd
  resolver -. decides visibility and landing .-> auth
  erp --> perm
  hd --> perm
  PLAT --> perm
  perm --> api
  FW --> db
  FW --> redis

  classDef future stroke-dasharray: 5 5,fill:#f4f4f4,color:#555;
```

## Naming and boundaries

| Layer | Name | Rule |
| --- | --- | --- |
| Platform / brand | **NXERP** | Umbrella. Owns the shared shell only |
| ERP application | **ERPNext** | Keeps its technical identity; never renamed |
| Support application | **Helpdesk** | Separate app; never "NXERP" |
| Technology | **Frappe Framework** | Not shown to business users as an application |

## Rules this overview implies

1. One login (Frappe `/login`), one identity per person. Authentication, authorisation, application visibility and routing are four separate concerns.
2. The platform app does not import apps and apps do not import the platform (ADR-005).
3. Hiding an icon is not security: enforcement happens in Frappe on the server (`docs/research/frappe-access-and-routing.md` has the surface-by-surface coverage table).
4. A unified experience is not merged code: Frappe and ERPNext are pinned upstream tags, Helpdesk is a pinned company fork, `nxerp` is our own app.

## Where things live

| Concern | Today (Phase 1) | Target |
| --- | --- | --- |
| Login page | Helpdesk fork `helpdesk/www/login.*` | Platform app (ADR-005) |
| Branding assets | Helpdesk fork `helpdesk/public/nxerp_login/*` | Platform app, per-app theme where needed |
| Launcher tiles | Frappe `/apps` fed by each app's `add_to_apps_screen` hook | Same mechanism, filtered by the access resolver (ADR-003) |
| Version pins | `deploy/versions.env`, `deploy/apps.json` | Same |
