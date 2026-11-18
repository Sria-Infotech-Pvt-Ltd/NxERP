# ADR-003: Access model (authorisation, app visibility, landing)

- **Status:** Accepted
- **Date:** 2026-10-27
- **Evidence:** `docs/research/part-2-permissions-and-enforcement.md` (static, pinned source: sections 1-8, coverage table 8, implications 10) and `docs/research/part-1-authentication-redirect-launcher.md`; runtime probes in `docs/audit/bootstrap-evidence.md`.

## Context: what the installed code actually does

- **FACT** Frappe has no app or module check anywhere in the request path (`handler.py`, `api/*`, `permissions.py`, `database/query.py`). `block_modules`, Workspace/Page roles and `add_to_apps_screen.has_permission` are navigation filters; the source says so: "navigation reach only. Never call it from `has_permission`" (`frappe/frappe/utils/modules.py:50-52`).
- **FACT** Data access *is* enforced, per DocType, by DocPerm / Custom DocPerm / User Permissions / hooks (`frappe/frappe/permissions.py`), for `/api/resource`, `/api/v2/document`, `frappe.client`, reports, files and print. It works today only because Helpdesk and ERPNext use disjoint role names.
- **FACT (runtime, dev site)** A Helpdesk `Agent` gets 403 on `/api/resource/Customer`, `/api/resource/Sales Invoice` and `search_link` for Customer; an ERP-only user gets 403 on `/api/resource/HD Ticket`. But the same agent gets **200** on `/desk` and `/desk/home` (any System User reaches the Desk shell), and every user, including customers, gets 200 on `/helpdesk/home` (SPA shell).
- **FACT** Whitelisted methods are authorised only by their own body: ERPNext has 804 whitelisted functions, about 338 with no obvious permission call, 8 `allow_guest` (part 2, section 7.1; the heuristic count is an ASSUMPTION about permission-looking calls).
- **FACT** The single in-tree cross-cutting hook point is `auth_hooks`, which sees the authenticated user for cookie, OAuth and API-key requests (`frappe/frappe/auth.py:625-648,746-748`); Helpdesk already uses it (`helpdesk/hooks.py:169`). `before_request` likely sees Guest for token requests (to be proven, part 2 check 9.9).
- **FACT** Roles carry across apps: `System Manager`, `Desk User`, `All` hold rights on many doctypes of every app.

## Options

Scores: Y = meets, ~ = partly, N = does not. Criteria from the brief.

| Criterion | A. Roles only, one app-access role per app | B. Module Profile / Block Modules | C. Per-user app-grant DocType | **D. Hybrid: roles stay the data source of truth + one thin resolver/gate in `nxerp`** | E. Custom RBAC engine |
| --- | --- | --- | --- | --- | --- |
| Server-side enforceable on URLs and APIs | N alone (no app gate exists); DocType level only | **N** (navigation only, FACT) | Y only if a gate is added | **Y** for covered surfaces via the gate; data still by DocPerm | Y, if built end-to-end |
| Survives upstream upgrades | Y | Y | Y | Y (uses `auth_hooks`, `get_hooks`, no patching) | N: must shadow Frappe's checks |
| Manageable by admins in the UI | Y (User, Role Profile) | Y | ~ (new screen to build) | Y (same Role Profile screens) | ~ |
| Auditable | Y (Version log on User roles) | ~ | ~ (own audit needed) | Y (role assignment is the audit trail) | ~ |
| Minimal duplication | Y | Y | **N** (second source of truth next to roles) | Y (one source: roles; resolver is derived) | **N** |
| Customer-safe | Y (Website User, `/desk` already 403) | Y | Y | Y | ~ |
| Admin-lockout-safe | Y | Y | ~ | Y if `Administrator` always passes and resolver errors fail closed for others only | ~ |
| Performance | Y (cached roles) | Y | ~ extra lookups | Y (roles cached; one map lookup per request) | ~ |
| Testability | Y | Y | Y | Y | ~ |

## Decision: D (hybrid)

1. **Grants are Frappe roles.** One app-access role per app (for example `NXERP Access: Helpdesk`, `NXERP Access: ERPNext`), assigned through Role Profiles. Data permissions stay in DocPerm / User Permissions as today. No new grant table; no custom RBAC.
2. **One thin resolver in `nxerp`** (Phase 2) computes, for a user, `apps = installed ∩ registered ∩ granted`. It owns the three non-security questions (visibility: the launcher; landing: skip the launcher when exactly one app; no-access) so they cannot disagree.
3. **App registry through hooks**, not imports (ADR-005): each app declares route, title, logo and its access role in its own hooks; the platform reads them with `frappe.get_hooks`. Hooks only append (FACT), so apps cannot hide each other; the resolver is the only filter.
4. **Server-side app gate** on the `auth_hooks` slot: map the request to its owning app (path prefix; whitelisted dotted-path root; DocType via `frappe.modules.utils.get_doctype_app_map` -> `get_module_app`) and deny when the user lacks that app's access role. This is what turns "hidden" into "blocked" for `/desk`, `/api/method/<app method>`, `/api/resource/<doctype>`.
5. **Lockout safety:** `Administrator` always passes. Resolver or gate errors fail **closed for everyone except `Administrator`**. System Managers are not auto-granted every app.
6. **Customers** keep Frappe's Website User model (`/desk` already returns 403; restricted portal only); the gate never grants them desk access.

## What this does NOT cover (stated limits)

- **Static assets and public files** (`/assets/*`, public `/files/*`) are served by nginx without Python: no gate possible; they are capability URLs.
- **The `/helpdesk` HTML shell** is served without login (FACT); only data endpoints can be gated. Whether the page prints the installed-apps list is NOT VERIFIED.
- **Payload-carrying calls** (`run_doc_method`, `frappe.client.*`, `reportview`, `search_link`, `getdoctype`, `download_pdf`, `query_report.run`) need a resolver per argument kind; coverage must be built and tested surface by surface, not assumed.
- **Shared doctypes** (`User`, `File`, `ToDo`, `Comment`, `Communication`, `Contact`) belong to app `frappe`; app-aware behaviour must key on the referenced document's doctype.
- **Schema/metadata endpoints** (`getdoctype`, `/api/v2/doctype/<dt>/meta`, `/api/v2/discovery/*`) answer any logged-in user without a read check; the gate can narrow them, but meta is not data.
- **Helpdesk to ERPNext bridge** (mirrored User Permissions / DocShares on Customer, `ignore_permissions` inserts) is a deliberate exception that needs its own decision and test.
- **Realtime:** task rooms, Helpdesk `view_ticket`, and unscoped `publish_realtime` have independent gaps; which realtime server runs is NOT VERIFIED.
- **Whitelisted ERPNext methods without their own checks** stay as safe as their own code unless the gate covers them by path.
- **Two redirect engines** (ADR-004) are routing, not security.

## Consequences

- Phase 2 must first prove, with tests, that `auth_hooks` can see the right user for cookie, token and socket requests and can raise 403 before dispatch (spike, part 2 checks 9.4 and 9.9).
- Each enforcement surface in the coverage table needs a test that a user without the grant is refused by URL and API: that table is the Phase 2 acceptance list.
- Agent roles' `desk_access` (and roles created implicitly from DocPerm rows defaulting to `desk_access = 1`) must be reviewed as part of role design.
