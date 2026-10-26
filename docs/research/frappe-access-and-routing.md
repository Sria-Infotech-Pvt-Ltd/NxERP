# Frappe access and routing: research summary

Scope: how the **installed** Frappe 16.53.0, ERPNext 16.52.1 and the Helpdesk fork (`1c6981cc5`) authenticate users, authorise requests, route after login and build the launcher. This page is the entry point; the two detailed parts hold the file-and-line evidence.

| Part | Content | Basis |
| --- | --- | --- |
| [part-1-authentication-redirect-launcher.md](part-1-authentication-redirect-launcher.md) | Login and sessions, setup wizard and Administrator, user types, roles/profiles/Block Module, post-login redirect chain, launcher, Helpdesk layering, ERPNext/portal | Static reading of pinned source (955 lines) |
| [part-2-permissions-and-enforcement.md](part-2-permissions-and-enforcement.md) | DocType permissions, page/report/workspace gating, API/file/print authorisation, realtime, lifecycle hooks, request-to-app mapping, ERPNext and Helpdesk layering, **coverage table**, verification list | Static reading of pinned source (818 lines) |
| [../audit/bootstrap-evidence.md](../audit/bootstrap-evidence.md) | Runtime observations on the Phase 1 dev site | Executed and observed |

Labels used throughout: **FACT** (verified, with evidence), **ASSUMPTION**, **NOT FOUND** (searched in the pinned source), **NOT VERIFIED** (needs runtime we have not run). Static-source claims in the parts are FACT about the *code*; the section "Runtime-verified" below is FACT about the *running site*.

Pinned sources (read-only checkouts): `frappe` v16.53.0 `e8d41dd`, `erpnext` v16.52.1 `ade850b`, Helpdesk fork `1c6981cc5`, `telephony` `9447577`, `payments` `cca07d9`.

## Mechanism existence check (candidate names from the brief)

| Candidate | In the pinned version |
| --- | --- |
| `frappe.auth` (LoginManager, `on_login`, `on_session_creation` hooks) | EXISTS |
| `home_page`, `role_home_page`, `website_user_home_page` | EXISTS (`role_home_page` as `Role.home_page`; chain in part 1, section 5) |
| `add_to_apps_screen` hook | EXISTS (`frappe/hooks.py:579`, `erpnext/hooks.py:13`, Helpdesk `hooks.py:12`) |
| `/apps` page (`frappe/www/apps.*`) | **NOT FOUND**: `/apps` is a 301 to `/desk`; the launcher is the Desk "desktop" screen fed by `boot.app_data` |
| `login_redirect` function, `after_login` hook | **NOT FOUND** |
| `before_session_creation` hook | **NOT FOUND** (`before_login` trigger exists, nothing core subscribes) |
| `is_safe_redirect` | **NOT FOUND** (real: `sanitize_redirect` in `www/login.py`, JS `frappe.utils.sanitise_redirect`) |
| `frappe.desk.desk_access` | **NOT FOUND** (desk access is computed in `core/doctype/user`, `Role.desk_access`) |
| `User.home_page` field / `Home Settings` as routing | **NOT FOUND** (legacy hidden field, unused by routing) |
| `Portal User` DocType, SAML | **NOT FOUND** |
| `can_subscribe_doc`, single-file `frappe/realtime.py`, function `apply_user_permissions` | **NOT FOUND** (v16: `frappe.realtime.has_permission`, a package, `has_user_permission`) |
| `Role`, `Has Role`, `Role Profile`, `Module Profile`, `Block Module`, `Custom DocPerm`, `User Permission`, `DocShare`, `permission_query_conditions`, `has_permission`, `before_request`, `after_request`, `auth_hooks`, `override_whitelisted_methods`, `website_route_rules`, `website_redirects` | EXIST (details in the parts) |

The complete tables (including per-part NOT FOUND lists) are at the top of each part.

## Ten findings that drive the architecture

1. **There is no app or module gate anywhere in the request path.** `block_modules`, Workspace/Page roles and launcher `has_permission` are navigation filters; Frappe says so in code (`frappe/frappe/utils/modules.py:50-52`). Separation today = disjoint role names + per-DocType DocPerm + Helpdesk's own `agent_only` checks. (part 2, 5.3, 10.1)
2. **Data access is enforced per DocType** on `/api/resource`, `/api/v2/document`, `frappe.client`, reports, files (inherit the attached document's permission) and print. (part 2, sections 1, 3)
3. **`/desk` admits any System User** and refuses Website Users (`www/desk.py:50-62`); a Helpdesk agent with desk access can open it and sees ERPNext in the launcher, because `erpnext.check_app_permission` returns True for any non-website user (`erpnext/__init__.py:158-165`). (part 1, I5, I10)
4. **`/apps` is not a page in v16.** Both `/apps` and `/app` redirect to `/desk` (`hooks.py:68-72`); the launcher is Desk-internal and therefore not reachable by Website Users. (part 1, I1)
5. **Two redirect engines**: a fresh `/api/method/login` uses `get_home_page()` for System Users, every other flow uses `get_default_path()`; the same account can land differently. A hook cannot overwrite the response `home_page` (assigned after hooks run, `auth.py:171-177` vs `199-205`). (part 1, I2)
6. **Helpdesk's install changes global landing**: it sets `Portal Settings.default_portal_home = "/helpdesk"` and `default_role = "HD Customer"` (`helpdesk/setup/install.py:216-250`), so users without a role home page are routed to `/helpdesk`. (part 1, I4; runtime-confirmed below)
7. **Hooks only append**: a third app cannot hide or re-route another app's launcher tile; only post-filtering can. (part 1, I6)
8. **Setup redirect is client-side** in the Desk router, and `frappe.is_setup_complete()` ignores Helpdesk: landing straight on `/helpdesk/home` skips the first-time wizard. (part 1, I11)
9. **The only cross-cutting server hook** is `auth_hooks` (sees the final user for cookie/OAuth/API-key requests); `before_request` likely sees Guest for token requests (NOT VERIFIED). Static assets, public files and the `/helpdesk` HTML shell have no server gate. (part 2, 5, 8)
10. **Redirect safety**: `redirect-to` is same-origin-only on server and client, but `localStorage["last_visited"]` and User Invitation `redirect_to_path` are unvalidated. (part 1, finding 8)

## Coverage table (who enforces each surface today)

Condensed from part 2, section 8 (16 rows with file:line evidence there). "Stops a Helpdesk-only user from ERPNext data?": YES = code refuses by role/permission; PARTIAL = relies on role separation; NO = not checked.

| # | Surface | Enforced by | Checks | Stops Helpdesk-only user? | Main gap |
| --- | --- | --- | --- | --- | --- |
| 1 | `/desk`, `/desk/*` (`/app/*`, `/apps` redirect) | `www/desk.py` | Logged in; not Website User | NO | Any System User gets the shell |
| 2 | Desk metadata (`getpage`, `get_desktop_page`, Workspace/Report lists) | Page roles; list builders | Roles, `block_modules` (navigation) | PARTIAL | Enumerable by Desk User |
| 3 | `/helpdesk` SPA HTML | Nothing server-side | none | NO (shell only) | Served to Guest; SPA guard is client-side |
| 4 | `/assets/*` | nginx | none | n/a | Public by design |
| 5 | `/api/method/*`, `?cmd=` | `handler.py` + method body | Whitelist, guest flag, per-method code | PARTIAL | No app gate; 804 ERPNext whitelisted functions, ~338 with no obvious check (ASSUMPTION on heuristic) |
| 6 | `/api/resource/*`, `/api/v2/document/*` | `permissions.py`, query layer | DocPerm, user perms, hooks | YES by role names | `getdoctype`/`meta` readable by any login |
| 7 | Reports, report view | `query_report.py`, `reportview.py` | Report roles, `report` right | YES / PARTIAL for script reports | No app dimension |
| 8 | Print / PDF | `print_format.py`, `printview.py` | read/print on document | YES | share-key links work for anyone |
| 9 | Private file download | `File.has_permission` | attached document's permission | YES for attachments | Public `/files/*` is nginx-served |
| 10 | File upload | `handler.py` | doc write if `doctype` given | PARTIAL | Unattached uploads allowed |
| 11 | Realtime (socket.io) | node/python realtime + `has_permission` | doc-level room joins | PARTIAL | `task_*` rooms, Helpdesk `view_ticket`, global publish |
| 12 | Website / portal (`/me`, `/portal`, `/list`, web forms) | `www/*`, `has_website_permission` | DocPerm + website perms | YES for Website Users with only HD Customer roles | `doctype` taken from URL, no app filter |
| 13 | Launcher (`get_apps`) | tile `has_permission` | display only | NO for ERPNext tile | Not a boundary |
| 14 | `/login`, `/logout`, `/api/method/login` | `auth.py`, `www/login.py` | credentials, 2FA (password/LDAP flows only) | n/a | Other login routes skip 2FA |
| 15 | `/api/v2/mcp`, `/api/v2/discovery/*` | `api/v2.py` | `Desk User` role | PARTIAL | Reveals all apps' method surface |
| 16 | `/backups`, `/.well-known/*` | `app.py` | own checks | NOT VERIFIED | Not analysed |

## Runtime-verified on the Phase 1 dev site

See [bootstrap-evidence.md](../audit/bootstrap-evidence.md), sections "Access baseline" and "Landing and launcher": these are executed observations (status codes per user and URL) and they are the baseline Phase 2 must change deliberately.

## What was not verified

Realtime room behaviour and which realtime server process runs; `before_request` vs token-auth ordering; whether the built Helpdesk HTML prints the `boot` apps list (see the baseline script for the HTML probe); private-file and print checks (need seeded ERPNext documents); `/backups` and `/.well-known/*`; 2FA bypass on social/email-link logins; behaviour of a bare `/desk` in a browser. Each has a command in part 1, section 11 or part 2, section 9.
