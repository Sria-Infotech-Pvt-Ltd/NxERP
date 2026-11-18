# Part 2 - Permissions and enforcement surfaces (Frappe v16 / ERPNext / Helpdesk)

Status: source-based research, no runtime. Purpose: give ADR authors evidence on how the installed code authorises requests and what each enforcement surface checks. This document describes; it does not design.

## 0. Scope, pins, conventions

Sources read (read-only), under `.../scratchpad/src/`:

| Short name | What | Pin |
|---|---|---|
| `frappe/` | Frappe framework (package path `frappe/frappe/...`, node realtime at `frappe/realtime/`) | v16.53.0 (e8d41dd0) |
| `erpnext/` | ERPNext (package path `erpnext/erpnext/...`) | v16.52.1 (ade850bb) |
| `helpdesk-fork/` | Company-customised Helpdesk (app package is `helpdesk-fork/helpdesk/...`, node realtime handler at `helpdesk-fork/realtime/`) | 1c6981cc5 |
| `telephony/` | Telephony app (required by Helpdesk) | not pinned in the brief |
| `frappe_docker/` | Used only as evidence for how nginx / socketio are deployed | present in src dir, not in the brief's pin list |

Labels used for every claim:

- FACT: read in source, `repo/path:line` given.
- ASSUMPTION: inferred, not proven by a line of code.
- NOT FOUND: searched, absent in these versions.
- NOT VERIFIED: needs a running site (see section 9).

Path convention: `frappe/frappe/permissions.py:108` means repo `frappe`, package `frappe`, file `permissions.py`, line 108.

## Table of contents

0. Scope, pins, conventions
- Mechanism existence check (table)
1. DocType permissions
2. Page, report and workspace role gating
3. API / resource / method / file / print authorisation
4. Realtime / websocket
5. Request lifecycle hooks and where a central gate could run
6. Mapping a request to its owning app
7. How ERPNext and Helpdesk use these mechanisms
8. Coverage table (per enforcement surface)
9. Runtime verification list
10. Implications for NXERP
- Appendix A. Helpdesk endpoints that are guest-reachable, use `ignore_permissions`, or lack an agent guard

---

## Mechanism existence check

Candidate (from the brief or general knowledge) -> result in the pinned versions.

| Candidate | Result | Evidence |
|---|---|---|
| `frappe.permissions.has_permission` | EXISTS | `frappe/frappe/permissions.py:81` |
| `get_doc_permissions` | EXISTS | `frappe/frappe/permissions.py:229` |
| `get_role_permissions` | EXISTS | `frappe/frappe/permissions.py:284` |
| permlevels | EXISTS | `permissions.py:317` (`cint(perm.permlevel) == 0` for doc-level), `model/meta.py:731` (`get_permlevel_access`) |
| `if_owner` | EXISTS | `permissions.py:257-264`, `database/query.py:1665-1667` |
| `Custom DocPerm` replacing `DocPerm` | EXISTS | `model/meta.py:637-650`, `permissions.py:507-527`, `permissions.py:695-699` |
| `Role Permission for Page and Report` | EXISTS (a UI doctype that writes `Custom Role`) | `frappe/frappe/core/doctype/role_permission_for_page_and_report/role_permission_for_page_and_report.py:27-100` |
| `Custom Role` (storage of page/report role overrides) | EXISTS | `frappe/frappe/core/doctype/custom_role/custom_role.py:34-41` |
| `User Permission` (`apply_user_permissions`) | EXISTS, but the function is `has_user_permission`, there is no function named `apply_user_permissions` | `permissions.py:353`, `core/doctype/user_permission/user_permission.py:95` |
| `ignore_user_permissions` | EXISTS (DocField flag, query arg, `frappe.flags` key) | `permissions.py:428`, `database/query.py:243,285`, `desk/search.py:97-107` |
| `DocShare` | EXISTS | `permissions.py:179-207`, `frappe/frappe/share.py` |
| `permission_query_conditions` hook | EXISTS, supports `"*"` key | `database/query.py:1705-1710` |
| `has_permission` hook | EXISTS, supports `"*"` key, deny-only | `permissions.py:483-500` |
| `frappe.get_list` / `get_all` / `frappe.db.get_*` | EXISTS | `__init__.py:1363`, `__init__.py:1386`, `__init__.py:1411` |
| `frappe.only_for` | EXISTS | `__init__.py:551` |
| `frappe.has_permission` | EXISTS | `__init__.py:603` |
| Administrator bypass | EXISTS | `permissions.py:108`, `permissions.py:306`, `__init__.py:558` |
| `ignore_permissions` flag | EXISTS (`doc.flags.ignore_permissions`, `get_list(..., ignore_permissions=)`); a global `frappe.flags.ignore_permissions` exists only as ad-hoc use | `model/document.py:646`, `database/query.py:269`, `email/doctype/email_group/email_group.py:132` |
| `Has Role` child on Page | EXISTS | `core/doctype/page/page.py:136` |
| `frappe.desk.desk_page.getpage` | EXISTS, `allow_guest=True` | `desk/desk_page.py:24-31` |
| `frappe.desk.query_report` (`run`, `export_query`, `get_script`) | EXISTS | `desk/query_report.py:210,255,442` |
| Workspace roles + module filter | EXISTS | `desk/desktop.py:67-103` |
| `Block Module` / `User.block_modules` | EXISTS, navigation only | `core/doctype/user/user.py:881`, `utils/modules.py:26-57` |
| Custom blocks permission | EXISTS (`Has Role` rows on the block) | `desk/desktop.py:216-231` |
| Number card / dashboard chart permissions | EXISTS (`has_permission` + `permission_query_conditions` hooks) | `hooks.py:116-150`, `desk/doctype/number_card/number_card.py:84-121` |
| `frappe.handler.handle`, `execute_cmd`, `is_whitelisted`, `allow_guest`, `xss_safe`, `methods=` | EXISTS | `handler.py:46,65`, `__init__.py:439-497`, `handler.py:99-110` |
| REST v1 (`/api/resource`, `/api/method`) | EXISTS | `api/v1.py:145-153` |
| REST v2 (`/api/v2/document`, `/api/v2/method`, ...) | EXISTS | `api/v2.py:277-321` |
| `frappe.client.*` | EXISTS | `client.py` |
| `frappe.desk.reportview`, `frappe.desk.search`, `frappe.desk.form.load` | EXISTS | `desk/reportview.py`, `desk/search.py`, `desk/form/load.py` |
| `/files`, `/private/files`, `download_file` | EXISTS | `app.py:138`, `app.py:556`, `handler.py:259`, `middlewares.py:14` |
| `frappe.utils.file_manager.download_file` | EXISTS only as a rerouted legacy name | `hooks.py:423` |
| `frappe.utils.print_format.download_pdf`, `/printview` | EXISTS | `utils/print_format.py:374`, `www/printview.py:45` |
| `frappe.model.rename_doc` permission check | EXISTS | `model/rename_doc.py:377-382` |
| `frappe/realtime.py` (single file) | NOT FOUND as a file; it is a package `frappe/frappe/realtime/` (Python server) plus node `frappe/realtime/` (repo root) | `frappe/frappe/realtime/__init__.py`, `frappe/realtime/index.js` |
| `frappe.realtime.get_user_info`, `can_subscribe_doc` | `get_user_info` EXISTS (`realtime/__init__.py:151`); `can_subscribe_doc` NOT FOUND in frappe (only in Helpdesk's allow-list string, `helpdesk-fork/helpdesk/auth.py:14`); replaced by `frappe.realtime.has_permission` (`realtime/__init__.py:126`) |
| Room names `doc:`, `user:`, `all`, `task_progress` | EXISTS (also `doctype:`, `open_doc:`, `website`) | `realtime/__init__.py:167-188`, `realtime/handlers.py:15-32` |
| `publish_realtime` | EXISTS | `realtime/__init__.py:30` |
| Hook `before_request` | EXISTS | `app.py:219`, `hooks.py:476` |
| Hook `after_request` | EXISTS | `app.py:185`, `hooks.py:483` |
| Hook `auth_hooks` | EXISTS (consumed; not declared in frappe's own `hooks.py`) | `auth.py:746-748` |
| Hook `before_job` / `after_job` | EXISTS | `utils/background_jobs.py:269,312` |
| Hook `on_session_creation` | EXISTS | `auth.py:241`, `hooks.py:97` |
| Hook `boot_session` | EXISTS | `boot.py:99-100` |
| Hook `extend_bootinfo` | EXISTS | `sessions.py:173-174` |
| Hook `override_whitelisted_methods` | EXISTS | `__init__.py:1582-1585`, `handler.py:67`, `api/v2.py:38` |
| Hook `override_doctype_class` | EXISTS | `model/document.py:137-155` |
| Hook `website_route_rules`, `website_redirects`, `page_renderer`, `website_path_resolver` | EXISTS | `website/path_resolver.py:56-109,140,233` |
| Hook `before_login` | EXISTS | `auth.py:147` |
| Hook `before_session_creation` | NOT FOUND | grep across `frappe/frappe` returns no consumer |
| Hook `on_login`, `on_logout` | EXISTS | `auth.py:171,366` |
| Hook `add_to_apps_screen` with `has_permission` callable | EXISTS (new in v15/16) | `apps.py:51-58`, `boot.py:295-300` |
| Hook `has_website_permission` | EXISTS | `__init__.py:676` |
| `frappe.get_doctype_app`, `frappe.get_module_app`, `frappe.local.module_app`, `Module Def.app_name`, `frappe.get_doc_module` | `get_doctype_app` EXISTS (`__init__.py:1470`); `get_module_app` EXISTS only as `frappe.modules.utils.get_module_app` (`modules/utils.py:320`; also reachable as `frappe.modules.get_module_app` via `from .utils import *`, `modules/__init__.py:1`), there is no top-level `frappe.get_module_app` (`__init__.py` only imports it locally at `:858`); `module_app` EXISTS (`__init__.py:1073-1084`); `Module Def.app_name` EXISTS (`core/doctype/module_def/module_def.json:15`); `frappe.get_doc_module` NOT FOUND as a top-level name, the function is `frappe.modules.utils.get_doc_module` (`modules/utils.py:46`) |
| MCP endpoint (not in the brief) | EXISTS - extra surface | `api/v2.py:278`, `mcp/transport.py:29-60` |
| API discovery endpoints (not in the brief) | EXISTS - extra surface | `api/v2.py:280-293`, `api/discovery.py` |

NOT FOUND list (for the hand-off): `before_session_creation` hook; single-file `frappe/realtime.py`; `can_subscribe_doc` and `can_subscribe_doctype` in Frappe; a function literally named `apply_user_permissions`; top-level `frappe.get_module_app` and `frappe.get_doc_module` (both live in `frappe.modules.utils`); any module-level or app-level check in `handler.py`, `api/*` or `permissions.py` (searched for `is_module_visible`, `get_blocked_modules`, `block_modules` consumers - only desk navigation and chart/card list filters use them, see 2.5).

---

## 1. DocType permissions

### 1.1 What the core check does (`frappe.permissions.has_permission`)

FACT, `frappe/frappe/permissions.py:81-226`. Order of evaluation:

1. `user == "Administrator"` returns True immediately (`permissions.py:108`).
2. `ptype == "share"` is refused when `System Settings.disable_document_sharing` (`:112`).
3. Child tables (`frappe.is_table`) delegate to the parent (`:121`, `has_child_permission` at `:817-911`, which also checks the permlevel of the parent's table field).
4. With a `doc` (or a Single): `get_doc_permissions(doc, user, ptype)` (`:138-142`). Without a `doc`: `get_role_permissions(meta, user)` only (`:163-169`), and `submit`/`import` flags are checked first (`:155-161`).
5. If role check said no and `ignore_share_permissions` is not set, `DocShare` is consulted (`:209-211`, body at `:179-207`). Only `read, write, share, submit, email, print` (plus custom ptypes) can be shared (`:180-185`).
6. `select` falls back to `read` (`:214-224`).

`get_doc_permissions` (`:229-281`) layers, in order: controller `has_permission` hooks (can only deny) -> role permissions -> `if_owner` override -> `has_user_permission` (User Permission). If User Permission denies and the user owns the doc, the `if_owner` permissions survive, with `create` forced to 0 (`:266-275`).

Gotcha (FACT): doc-level hooks (`has_permission` hook) and User Permissions run only when a `doc` is present (`permissions.py:138-142` vs `:163-169`). A doctype-level check such as the one in `get_list` (`database/query.py:1432-1437`, `frappe.has_permission(doctype, "select")`) never calls the `has_permission` hook. For lists the equivalent hook is `permission_query_conditions`.

### 1.2 Role resolution

FACT, `permissions.py:542-576`: roles are `Has Role` rows of the user (minus automatic roles) plus `All`, `Guest`, and `Desk User` when `user_type == "System User"`. Cached in redis hash `roles` (`:570`). Administrator gets every role (`:551-552`). `Guest` gets only `["Guest"]` (`:547-548`).

`user_type` is derived: `System User` iff some role of the user has `desk_access = 1` (`core/doctype/user/user.py:434-445,462-471`), unless a non-standard `User Type` is set. `Role.desk_access` defaults to 1 (`core/doctype/role/role.json:73-77`). Helpdesk's install explicitly sets `desk_access = 0` only on `HD Customer` and `HD Customer Manager` (`helpdesk-fork/helpdesk/setup/install.py:216-225`). Roles `Agent` / `Agent Manager` are created implicitly by DocType permission rows (`core/doctype/doctype/doctype.py:1994` `make_module_and_roles`) and therefore keep the default `desk_access = 1` (ASSUMPTION: no explicit role record found for `Agent` in the fork; runtime state NOT VERIFIED).

Consequence (FACT chain, runtime NOT VERIFIED): a Helpdesk agent is a System User, gets the automatic `Desk User` role, can open `/desk` (`www/desk.py:56-57` only blocks `Website User`), and is subject to every doctype row granted to `Desk User`/`All` (see 1.8).

### 1.3 `DocPerm` vs `Custom DocPerm`

FACT:

- Standard rules ship as `DocPerm` child rows of the DocType JSON. `Meta.set_custom_permissions` replaces them wholesale if any `Custom DocPerm` row exists for that doctype (`model/meta.py:637-650`).
- `get_valid_perms` mirrors this: Custom wins per doctype, DocPerm used only for doctypes without Custom rows (`permissions.py:507-527`).
- Any UI/API change (`add_permission`, `update_permission_property`) first copies every `DocPerm` row into `Custom DocPerm` (`setup_custom_perms`, `permissions.py:695-699`; `copy_perms`, `:742-747`). From then on migrate/app updates to the shipped DocPerm for that doctype no longer take effect.
- Helpdesk does exactly this to core doctypes at install: `add_permission("File"|"Contact"|"Email Account"|"Communication", "Agent", 0)` and Agent Manager rules (`helpdesk-fork/helpdesk/setup/install.py:177-196,198-215`), and to `HD Ticket` when `allow_anyone_to_create_tickets` is switched on (Guest read/write/create/if_owner, `helpdesk-fork/helpdesk/helpdesk/doctype/hd_ticket/hd_ticket.py:1449-1459`).

### 1.4 Permlevels, `if_owner`, field masking

FACT: `get_role_permissions` evaluates only `permlevel == 0` rows for doc access (`permissions.py:316-317`); higher permlevels gate fields via `Meta.get_permlevel_access` (`model/meta.py:731-739`) and `apply_fieldlevel_read_permissions` (called in `api/v1.py:82`, `api/v2.py:69`, `handler.py:339`). `if_owner` is evaluated per doc (`permissions.py:257-264`) and as a SQL `owner = user` condition in lists (`database/query.py:1665-1667`). v16 also has field masking (`model/meta.py:195-209`, `desk/form/meta.py:76-77`). The ERPNext/Helpdesk code base mostly does not use these; relevant only as available levers.

### 1.5 `User Permission`

FACT:

- Stored per user as `{allow: DocType, for_value: name, applicable_for?, is_default, hide_descendants}`; loaded as a dict doctype -> list and cached in redis hash `user_permissions` (`core/doctype/user_permission/user_permission.py:95-149`). Never applies to `Administrator` or `Guest` (`:100-101`).
- Applied (a) on a doc of that doctype itself (`permissions.py:385-411`), and (b) on every Link field of the doc and its children unless the field has `ignore_user_permissions` (`permissions.py:418-471`); (c) in lists as `WHERE` conditions (`database/query.py:1532-1590`).
- Semantics: a user with no rows for a doctype is not restricted at all. User Permission can restrict which records are visible through a link; it cannot express "no access to this app" (ASSUMPTION from the semantics above).
- Sent to the browser in boot (`user_permission.py:85-86`, hook `extend_bootinfo`, `hooks.py:507-510`).
- Helpdesk mirrors User Permissions and DocShares between `HD Customer` and ERPNext `Customer` (see 7.3).

### 1.6 `DocShare`

FACT: shares are consulted as a fallback when role permission is absent (`permissions.py:209-211`) and OR-ed into list queries: "shared docs trump all other restrictions" (`database/query.py:1594-1603,1679-1683`). If the user has no role read at all, only shared docs are listable (`:1653-1660`). `File` has its own handling (`core/doctype/file/file.py:1033-1040`).

### 1.7 Hooks: `permission_query_conditions` and `has_permission`

FACT:

- `permission_query_conditions`: `{doctype_or_"*": "dotted.path"}`; called as `fn(user, doctype=...)`, returns a SQL fragment string; all fragments are AND-ed with role/user-permission conditions (`database/query.py:1697-1734`, key lookup `:1705-1706`: `hooks.get(doctype, []) + hooks.get("*", [])`). Also supported through Server Scripts (`:1720-1726`). Applies only to queries made with permissions on (`get_list`, `/api/resource`, reportview, `get_query(ignore_permissions=False)`).
- `has_permission`: `{doctype_or_"*": "dotted.path"}`; called as `fn(doc=, ptype=, user=, debug=)` through `frappe.call`, evaluated in reverse hook order, a falsy return denies, there is no way to grant (`permissions.py:483-500`, docstring "Controllers can only deny permission").
- Both are merged across installed apps (`__init__.py:965-988`, `append_hook`), cached in `client_cache["app_hooks"]` (`:1009-1012`); changes need a hook reload (migrate / cache clear) (ASSUMPTION on exact invalidation points).
- Frappe's own hooks list: `frappe/frappe/hooks.py:116-164` (ToDo, User, Notification Log, File, Comment, Communication, Number Card, Dashboard Chart, ...).
- Static controller `get_list(query)` on a v2 resource is applied after permission conditions (`api/v2.py:140-160`).

### 1.8 Doctypes that every logged-in or every desk user can reach (role rows in JSON, FACT)

From the shipped DocPerm JSON (`frappe/frappe/<module>/doctype/<dt>/<dt>.json`), read with a script:

| Doctype | Module | Rows relevant to cross-app exposure |
|---|---|---|
| File | Core | `All` RWCD, `System Manager` RWCD; real scoping is in the `File` hooks (6.5, 3.5) |
| ToDo | Desk | `All` RWCD; scoped by ToDo hooks (`hooks.py:118,144`) |
| Notification Log | Desk | `All` R; scoped to `for_user` (`notification_log.py:103-116`) |
| Module Def | Core | `All` R (any user can list modules incl. `app_name`) |
| Workspace | Desk | `Desk User` RWCD, no `permission_query_conditions` or `has_permission` hook (`hooks.py:116-164`) |
| Report | Core | `Desk User` R |
| Number Card / Dashboard Chart | Desk | `Desk User` R, narrowed by hooks (`number_card.py:84-121`) |
| Desktop Icon | Desk | `Desk User` RWCD |
| Dock | Desk | `Desk User` R |
| Contact | Contacts | `All` RWCD if_owner plus ERPNext business roles |
| Communication | Core | `All` R if_owner (+hook) |
| User / Role | Core | `Desk User` row with no rights; `System Manager` RWCD |
| Page | Core | only `Administrator`, `System Manager` |
| DocType | Core | only `Administrator`, `System Manager` |

Implication to note: the role rows on `Workspace`/`Report`/`Module Def` say "any System User can read the doctype". The role gating of individual Workspaces/Reports (section 2) is applied by loaders, not by `/api/resource/Workspace` (see 2.4).

### 1.9 Which Python APIs check permissions and which do not

FACT:

| API | Permission check | Evidence |
|---|---|---|
| `frappe.get_list` | Yes (doctype `select`/`read`, user permissions, query-condition hooks, if_owner, shares, permlevel fields) | `__init__.py:1363-1383`, `model/qb_query.py:124-135,213` -> `database/query.py:288-289,349,1590-1685` |
| `frappe.get_all` | No: forces `ignore_permissions=True` | `__init__.py:1405` |
| `frappe.db.get_value`, `get_values`, `exists`, `sql`, `count` | No (DB layer) - ASSUMPTION from layering; `frappe.get_value` is an alias of `local.db.get_value` | `__init__.py:1411-1423` |
| `frappe.qb.get_query(...)` | Default `ignore_permissions=True`; callers must pass `False` | `database/query.py:242`; v2 passes `False` at `api/v2.py:137` |
| `frappe.get_doc(dt, name)` | No by default; `check_permission=True/"write"` opts in | `__init__.py:391-400` |
| `doc.insert()` / `doc.save()` / `frappe.delete_doc` / `frappe.rename_doc` | Yes unless `ignore_permissions` (`insert` calls `check_permission("create")`) | `model/document.py:699,646-657`, `model/delete_doc.py:293`, `model/rename_doc.py:377-385` |
| `frappe.has_permission(..., throw=True)` | Yes | `__init__.py:603-649` |
| `frappe.only_for(roles)` | Role membership only; Administrator passes | `__init__.py:551-574` |
| `doc.flags.ignore_permissions = True` / `ignore_permissions=True` kwarg | Disables doc-level checks | `model/document.py:646-647` |

`frappe.only_for` takes roles, not apps. ERPNext uses it for a small number of admin actions (`Accounts Manager`, `System Manager`, `Projects Manager`; e.g. `erpnext/erpnext/accounts/doctype/chart_of_accounts_importer/chart_of_accounts_importer.py:87`).

### 1.10 Administrator

FACT: Administrator bypasses `has_permission` (`:108`), role permissions (`:306-308`), `only_for` (`__init__.py:558`), `is_item_allowed` (`desk/utils.py:56-57`) and Helpdesk's `is_agent` (`helpdesk-fork/helpdesk/utils.py:54-55`). `System Manager` is NOT a global bypass in Frappe core, but it is a row on almost every doctype in all three apps (e.g. all HD doctypes, see 7.2) and is hard-coded as an exception in `Number Card` hooks (`number_card.py:88,109`), `check_app_permission` (`permissions.py:962-966`) and `can_export` (`permissions.py:657-658`).

---

## 2. Page, report and workspace role gating

### 2.1 Page

FACT:

- Roles are `Has Role` child rows on the `Page` doc; overrides live in `Custom Role` (`core/doctype/page/page.py:132-147`). For pages the custom roles are appended to the standard ones (`:138-139`); for reports they replace them (`core/doctype/report/report.py:150-153`).
- A page with no roles is permitted for everyone including Guest (`page.py:141-142`).
- Loader: `frappe.desk.desk_page.getpage(name)` is `@frappe.whitelist(allow_guest=True)` (`desk/desk_page.py:24-31`); it loads the Page with `frappe.get_doc` (no doctype permission), then `page.is_permitted()` and raises 403 otherwise (`:7-21`). `load_assets` ships the page's JS/CSS/HTML to the client (`page.py:149-205`).
- Standard pages without roles in the three apps: `dashboard-view`, `print` (Frappe). ERPNext pages are all role-gated with ERPNext roles (`point-of-sale`, `sales-funnel`, `stock-balance`, ...) - listed by script over `*/page/*/*.json`. Helpdesk ships no desk Pages.
- Pages are metadata plus JS. Data comes from whitelisted methods the page calls; the page gate does not protect those methods.

### 2.2 Report

FACT, `desk/query_report.py`:

- `get_report_doc` (`:29-63`): `Report.is_permitted()` (roles / `Custom Role`; empty roles = everyone), then `frappe.has_permission(ref_doctype, "report")`, then `disabled` check. Used by `get_script` (`:209-243`) and `_run` (`:293`).
- `run` (`:253-275`): `validate_filters_permissions` (Link filter values must be readable/selectable by the user, `:1212-1241`), `get_report_doc`, a second `report` permission check (`:294`), then executes. The `user` parameter is ignored in `run` (kept for compat, `:258,266-275`).
- After execution, result rows are post-filtered with `get_filtered_data(ref_doctype, columns, result, user)` (`:152-153`, `:974`) using User Permissions on linked columns.
- `export_query` (`:441-475`): `frappe.permissions.can_export(ref_doctype)`; note `can_export` returns True for any `System Manager` (`permissions.py:657-658`). The export re-uses `_export_query`, which runs the report again.
- Script Reports run arbitrary Python from the owning module (`execute(filters)`); ERPNext reports build SQL by hand and apply `build_match_conditions` themselves (e.g. `erpnext/erpnext/accounts/report/general_ledger/general_ledger.py:333-335`). Whether a given ERPNext script report enforces row-level rules is per report (ASSUMPTION; a spot-check list exists in the grep output but no exhaustive audit was done).
- Report builder style views use `frappe.desk.reportview` (3.6).

Standard `Report` records with no roles and `is_standard == "Yes"` are visible to every user who has `report` permission on `ref_doctype` (`report.py:155-159`). `Report.set_doctype_roles` copies the doctype's permlevel-0 roles into new non-standard reports (`report.py:136-143` region).

### 2.3 `Role Permission for Page and Report`

FACT: this is a Single doctype used as a UI to create/update `Custom Role` documents (`core/doctype/role_permission_for_page_and_report/...:27-100`). It does not enforce anything itself. Enforcement is in `Page.is_permitted`, `Report.is_permitted`, `Workspace.is_permitted` and the boot builders that read `Custom Role` (`desk/desk_views.py:146-230`).

### 2.4 Workspace

FACT:

- `Workspace.is_permitted()` (`desk/desktop.py:67-103`): (a) private page of the same user always visible, (b) `is_module_visible(self.doc.module)` i.e. the user's `block_modules`, (c) `Has Role` rows + `Custom Role` (page type), empty = visible to all.
- Contents (`build_workspace`, `:168-175`) are filtered per widget: links/shortcuts/quick lists via `is_item_allowed` (`desk/utils.py:36-80`: DocType -> `can_read` + domain + `frappe.has_permission`; Page -> `allowed_pages`; Report -> `allowed_reports`; Dashboard; Workspace), charts and number cards via `frappe.has_permission(..., doc=)` (`:273-343`), custom blocks via role rows (`:216-231`, `:346-362`).
- `frappe.desk.desktop.get_desktop_page(page)` is `@frappe.whitelist()` and builds a workspace's contents from the client-supplied page dict without calling `is_permitted()` (`desktop.py:365-390`, `Workspace.__init__` `:35-65`); only the per-widget filters apply. Consequence (FACT of control flow, result NOT VERIFIED): a System User can request the content of a workspace whose roles/module do not allow it, but receives only widgets that pass the widget filters.
- `get_workspaces()` (`:429-523`) is the list builder used by boot; each page is tested with `Workspace.is_permitted()` (`:488-492`) and tagged with `page["app"] = get_module_placement(page["module"])` (`:504`), source comment: "there is no `Workspace.app` any more, so the module decides which app a workspace belongs to" (`:500-503`).
- `Workspace` doctype itself is `Desk User` RWCD with no `has_permission` / `permission_query_conditions` hook (JSON + `hooks.py:116-164`). So `GET /api/resource/Workspace` lists every workspace to any System User (FACT of config; result NOT VERIFIED). Workspace roles are a presentation filter, not a record-level security control.

### 2.5 `Block Module` / `User.block_modules` / `Module Profile`

FACT:

- Stored in `User.block_modules` (child `Block Module`), populated from a `Module Profile` or a non-standard `User Type`'s allowed modules (`core/doctype/user/user.py:322-324,881-883`; `core/doctype/user_type/user_type.py:87-95`).
- Consumers (complete list from grep over `frappe/frappe`, `erpnext/erpnext`, `helpdesk-fork/helpdesk` excluding tests/patches): `boot.py:406-408`, `desk/desktop.py:84-93` (Workspace), `desk/doctype/desktop_icon/desktop_icon.py:137-140`, `desk/doctype/dock/dock.py:1036-1090`, `desk/doctype/sidebar/sidebar.py:1635,1762-1775`, `desk/doctype/workspace/workspace.py:1257-1262`, and the module filters in `Dashboard`, `Dashboard Chart`, `Number Card` list conditions (`dashboard.py:86`, `dashboard_chart.py:45`, `number_card.py:93,237`). Nothing in `handler.py`, `api/`, `permissions.py` or `database/query.py` reads it.
- The framework states the intent in source: "`is_module_visible` ... This is navigation reach only. Never call it from `has_permission`. Document access is decided by DocPerm, and routing it through here would turn a navigation preference into a security boundary. Hiding a module hides the way to a document, never the document itself." (`frappe/frappe/utils/modules.py:50-52`).
- `code_only_modules` (hook) is explicitly "not a permission gate" (`utils/modules.py:80-84`).

### 2.6 Desk shell: what the server enforces vs the client

- `/desk` and `/desk/<path>`: hard-wired in the path resolver before cache/redirect/renderers (`website/path_resolver.py:44-45`) and routed to `www/desk.py:get_context`: Guest -> redirect to login, `Website User` -> 403, any other user -> gets the boot payload (`www/desk.py:50-62`). No role, module or app check.
- Legacy `/app/*` and `/apps` are 301 redirects to `/desk/*` and `/desk` (`hooks.py:68-72`).
- Boot payload (`boot.py:34-138`) is the server's view for the desk: `DeskViews.build_entities` (allowed pages/reports/workspaces/dashboards), `bootinfo.module_app`, per-app dock with permission-filtered entry sets, `boot_session` and `extend_bootinfo` hooks, `bootinfo.user.user_permissions`. The Vue/JS desk router then decides which route to show. For an unlisted route the browser still tries to load the doctype/page; the server answers according to sections 1 and 3, not according to the client router. The client router is not a security control (ASSUMPTION based on the above; no client code read).
- App visibility on the launcher: `frappe.apps.get_apps` calls each app's `add_to_apps_screen[].has_permission` callable (`apps.py:36-73`; `boot.py:295-322` for `app_data`). It returns names/routes only. See 7.1 for what each of the three apps returns.

---

## 3. API / method / resource / file / print authorisation

### 3.1 Request routing

FACT, `frappe/frappe/app.py:108-178` (`application`): order of dispatch after `init_request` and `validate_auth`:

1. `request.method == "OPTIONS"` (`:118`).
2. `frappe.form_dict.cmd` present: legacy RPC, any path (`:121-130`).
3. path starts with `/api/` -> `frappe.api.handle` (`:132-133`).
4. `/backups` (`:135`), `/private/files/` (`:138`), `/.well-known/...` (`:141-148`).
5. GET/HEAD/POST else -> website renderer `get_response()` (`:150-151`).
6. Else 404.

Only in dev mode (`serve()` sets `application_with_statics`) werkzeug serves `/assets` and public `/files` from Python (`app.py:551-558`, `middlewares.py:14-44`). In the reference docker deployment nginx serves them directly (3.9).

### 3.2 `frappe.handler.execute_cmd` and `is_whitelisted`

FACT, `handler.py:65-86`, `__init__.py:439-497`:

- `override_whitelisted_method` hook applied first (`handler.py:67`).
- Server Script API methods (`_api`) are looked up and run before Python methods (`:70-72`).
- `frappe.get_attr(cmd)` (`:75`): first dotted segment must be an installed app (`__init__.py:1134-1136`).
- `is_whitelisted(method)` (`:83`): method must have been decorated with `@frappe.whitelist`; Guest additionally needs `allow_guest=True`; for Guest, `form_dict` string values are HTML-sanitised unless `xss_safe` (`__init__.py:479-497`).
- `is_valid_http_method` (`handler.py:99-110`): HTTP verb must be in `methods=` (default GET/POST/PUT/DELETE, `__init__.py:454-455`).
- `run_doc_method` skips the whitelist test for itself, then tests the controller method (`handler.py:82,293-351`); it loads the doc with `check_permission=True` (`:307,311`).
- Authorisation of the method body is entirely up to the method. The framework supplies no role, module or app check here. There is a `require_type_annotated_api_methods = True` hook in Helpdesk and Frappe that validates argument types only (`hooks.py:177` / Helpdesk `hooks.py:10`).

### 3.3 REST v1 (`/api/resource`, `/api/method`)

FACT, `api/v1.py:145-153`, `api/__init__.py:23-84`:

| Route | Handler | Check |
|---|---|---|
| `GET /api/resource/<dt>` | `document_list` -> `frappe.client.get_list` -> `frappe.get_list` | doctype select/read + user perms + query-condition hooks (`v1.py:12-32`, `client.py:26-76`) |
| `POST /api/resource/<dt>` | `frappe.new_doc(...).insert()` | `check_permission("create")` (`v1.py:44-47`, `document.py:699`) |
| `GET /api/resource/<dt>/<name>` | `read_doc` | `doc.check_permission("read")` (`v1.py:75-89`); also `apply_fieldlevel_read_permissions` |
| `PUT` | `update_doc` | `doc.check_permission("write")` (`v1.py:50-65`) |
| `DELETE` | `frappe.delete_doc(...)` | delete permission inside `delete_doc` (`v1.py:68-72`) |
| `POST /api/resource/<dt>/<name>?run_method=` | `execute_doc_method` | `doc.is_whitelisted(method)`, GET -> read, POST -> write (`v1.py:116-130`) |
| `/api/method/<path>` | `handle_rpc_call` -> `frappe.handler.handle` | section 3.2 |

`api.handle` already resolves a doctype -> app and a method -> first path segment for telemetry only (`api/__init__.py:71-82`: `get_doctype_app_map().get(doctype)`, `method.split(".", 1)[0]`), inside `suppress(Exception)`. It is a ready-made hook point; it currently only records.

### 3.4 REST v2 (`/api/v2/...`)

FACT, `api/v2.py`:

- `document_list` builds `frappe.qb.get_query(..., ignore_permissions=False)` (`:129-138`), then optional controller static `get_list(query)` (`:140-158`).
- `read_doc`/`update_doc`/`copy_doc`/`execute_doc_method` use `doc.check_permission(...)` (`:66-77,196-210,185-193,224-242`); `PERMISSION_MAP` GET->read, POST->write (`:24-27`).
- `create_doc` -> `doc.insert()` (`:173-182`); `delete_doc` -> `frappe.client.delete_doc` (`:213-216`).
- `GET /api/v2/doctype/<dt>/meta` -> `frappe.only_for("All")` then `frappe.get_meta(doctype)` (`:219-221`). `All` = any logged-in user (Guest roles = `["Guest"]` only, `permissions.py:547-548`). No doctype read check: schema of any doctype is returned to any logged-in user (FACT of code; result NOT VERIFIED).
- `/api/v2/method/<method>` and `/api/v2/method/<doctype>/<method>` -> `handle_rpc_call`: override hook, Server Script, `get_attr`, `is_whitelisted`, `is_valid_http_method` (`:30-53`).
- Extra surfaces: `/api/v2/mcp` (`:278`), `/api/v2/discovery/*` (`:280-293`). Discovery: every handler starts with `frappe.only_for("Desk User")` and lists every whitelisted method of every installed app, with source when `expose_discovery_source = True` (`api/discovery.py:29-110`, `hooks.py:576`). MCP: POST only, Guest refused, requires `Desk User`, tools reuse v2 document permissions and "call existing APIs without changing their whitelist or permission rules" (`mcp/transport.py:29-48`, `mcp/tools/documents.py:3`, `mcp/tools/methods.py:3`).

### 3.5 `frappe.client.*` (RPC form of the resource API)

FACT, `client.py`: `get_list` (`:26-76`) -> `frappe.get_list`; `get_count` -> `reportview.get_count`; `get` (`:94-117`) -> `doc.check_permission()`; `get_value` (`:120-172`) -> `frappe.has_permission(doctype)` (`:135`) then `get_list`; `get_single_value` (`:175-180`) -> `has_permission`; `set_value`, `insert`, `insert_many`, `save`, `submit`, `cancel`, `delete`, `bulk_update`, `rename_doc` -> doc-level checks through `doc.save()`/`frappe.delete_doc`/`rename_doc`; `get_password` -> `only_for("System Manager")` (`:346-354`); `get_time_zone` allow_guest (`:363`). Helpdesk's non-system-user allow-list names many of these (`helpdesk-fork/helpdesk/auth.py:45-52`).

### 3.6 Desk list/report/search/form endpoints

FACT:

- `frappe.desk.reportview.get|get_list|get_count|export_query` -> `DatabaseQuery(...).execute` from `model/qb_query.py` (permissions on) (`desk/reportview.py:19,30-118,121-122,444-475`); `DISALLOWED_PARAMS` strips `ignore_permissions`, `user` from client input (`:24`). Export requires `can_export` (`:530-544`).
- `frappe.desk.search.search_link` / `search_widget` (`desk/search.py:37-300`): `frappe.get_list` with permissions, except `ignore_permissions=doctype == "DocType"` (`:272`). A custom `query=` must itself be whitelisted (`:149`). `ignore_user_permissions` accepted only if the referencing Link field is flagged (`:97-107`, `validate_ignore_user_permissions` `:302`). `get_names_for_mentions`, `awesomebar_search`, `get_link_title` have their own logic (`:491-611`).
- `frappe.desk.form.load.getdoc` -> `doc.check_permission("read")` (`:24-60`); `getdoctype` -> `get_meta_bundle(doctype)` with no permission call (`:62-90`); it returns the doctype meta including `permissions`, client scripts, print formats and workflow docs through `FormMeta` (`desk/form/meta.py:30-77`). Any logged-in user can request it for any doctype (FACT of code; runtime NOT VERIFIED). Helpdesk's own allow-list names it (`auth.py:58`), i.e. it is intended to be reachable.
- `get_docinfo`, `get_communications`, `get_filtered_attachments`, `desk/doc_preview.get_preview`, `desk/notifications.get_open_count` all load docs with `check_permission` (`form/load.py:93-103,208-211,255-259`, `doc_preview.py:8-13`, `notifications.py:264-265`).
- `frappe.desk.form.save.savedocs`, `cancel`, `discard` -> doc methods with checks (`form/save.py`).

### 3.7 File upload, download, private files

FACT:

- `POST /api/method/upload_file` (`handler.py:128-238`): Guest allowed only if `allow_guests_to_upload_files` (`:131-145`). For a logged-in user, `check_write_permission(doctype, docname)` runs only when `doctype` is given (`:174-175,241-255`); without `doctype` the file is created as an unattached `File` (doctype perm: `All` RWCD; row-scoping in `File` hooks). Non-desk users are limited to a MIME allow-list (`:215-218`).
- `GET /private/files/<path>` (`app.py:138-139`, `utils/response.py:294-306`): Guest -> 403; `find_file_by_url(path)` loads `File` rows for the URL and calls `is_downloadable()` = `has_permission(file, "read")` (`core/doctype/file/utils.py:462-475`, `file.py:916-917`). `File.has_permission` (`file.py:1022-1059`): public files readable; owner; shared; otherwise inherits the attached doctype/doc read (or write) permission through `ref_doc.has_permission`. So private attachments follow the permissions of the document they are attached to (good for cross-app: an ERPNext document's attachment obeys ERPNext doc permissions).
- `File` list queries have their own SQL conditions: non-system users only see their own files; system users see public files, own unattached files, and files attached to doctypes they can read, narrowed by if_owner and User Permissions (`file.py:1062-1112`).
- `GET /api/method/frappe.core.doctype.file.file.download_file` and `frappe.utils.file_manager.download_file` are rerouted by `override_whitelisted_methods` to `frappe.handler.download_file` (`hooks.py:423-424`), which is `allow_guest=True` and relies on `find_file_by_url` (`handler.py:258-274`).
- `/files/<path>` (public): served by nginx or the dev static middleware straight from `sites/<site>/public/files`; no Python check, no session (`middlewares.py:33-44`, nginx `location /` + `try_files .../public/$uri`, `frappe_docker/resources/core/nginx/nginx-template.conf:53-65`). A public file URL is a capability link.
- Private files in nginx: Python authorises, then `X-Accel-Redirect` to the internal `/protected/` location (`utils/response.py:334-340`, nginx `:35-38`).

### 3.8 Print / PDF

FACT:

- `frappe.utils.print_format.download_pdf` is `allow_guest=True` (`utils/print_format.py:371-409`) and calls `validate_print_permission(doc)`.
- `validate_print_permission` (`www/printview.py:536-550`): `read` or `print` on the doc, else `has_website_permission`, else a valid `Document Share Key` (`key=` param), else deny. `get_html_and_style`, `get_rendered_raw_commands` and `print_utils.get_print` call it too (`printview.py:404-440,475-497`, `utils/print_utils.py:125-128`).
- `/printview` page: `www/printview.py:45-` renders via the same gate. `download_multi_pdf` is `@frappe.whitelist()` and loads docs per item (`print_format.py:65-135`; permission path inside `_download_multi_pdf`, ASSUMPTION not read line by line).
- Print does not know about apps; ERPNext print formats are protected only by the doctype's `read`/`print` rights.

### 3.9 Static assets and nginx (reference deployment)

FACT from `frappe_docker/resources/core/nginx/nginx-template.conf`:

- `location /assets { try_files $uri =404; }` serves every app's built bundles (`/assets/erpnext/...`, `/assets/helpdesk/desk/...`) without any session (`:31-33`).
- `location /` first tries `sites/<site>/public/<uri>` (public files), then proxies to gunicorn (`:53-65`, `@webserver` `:67-78`).
- `/socket.io` proxies to the node realtime container (`:40-51`); compose runs `node .../apps/frappe/socketio.js` as `websocket` (`frappe_docker/compose.yaml:77-83`).
- This is the repo's reference config. The actual NXERP deployment is ASSUMPTION (the brief says Docker runs Frappe 15; the pinned source here is v16 - NOT VERIFIED which image the running site uses).

---

## 4. Realtime / websocket

### 4.1 Two implementations exist in v16.53

FACT:

- Node server: `frappe/realtime/index.js` (+ `middlewares/authenticate.js`, `handlers.js`, `utils.js`), started by `frappe/socketio.js` (`require("./realtime")`). The reference compose file runs this one (`frappe_docker/compose.yaml:77-83`).
- Python asyncio server: `frappe/frappe/realtime/` (`server.py`, `auth.py`, `handlers.py`, `dispatch.py`, `registry.py`, `bridge.py`, `socket.py`, `README.md`), started with `python -m frappe.realtime.server`; header comment "Port of realtime/middlewares/authenticate.js" (`realtime/auth.py:100`). Nothing in `frappe_docker` starts it (grep).
- Which one the NXERP site runs is NOT VERIFIED. This document covers both; where behaviours differ it says so.

### 4.2 Authentication of a socket

FACT (both servers):

- Namespace is the site name; origin host must equal Host (`node authenticate.js:13-24`, `python auth.py:122-137`). Credentials: `sid` cookie or `Authorization` header; at least one required.
- The server asks the web process who the user is: `GET /api/method/frappe.realtime.get_user_info` with the client's `sid`/`Authorization` plus `X-Frappe-Socket-Secret` (secret stored in redis `socketio_auth_secret`) and `X-Frappe-Site-Name` (`node authenticate.js:45-85`, `python auth.py:170-199,257-271`).
- `get_user_info` is `allow_guest=True` but returns `{}` unless the secret matches (`realtime/__init__.py:150-164`); it returns `{user, user_type, installed_apps}`. So the session identity used by the socket is exactly what the web process resolves (cookie session, API key, bearer, or `auth_hooks`) - see 5.
- Guests may connect (user `Guest`); the python dispatcher drops events from guests unless `allow_guest=True` on the handler (`dispatch.py:87-88`), and the core handlers are mostly `allow_guest=True` (`handlers.py:35-103`), relying on `has_permission` to refuse.

### 4.3 Rooms and publish semantics

FACT, `realtime/__init__.py:30-90,167-188`, `handlers.py:15-41`:

| Room | Name | Who is put in it |
|---|---|---|
| user | `user:<email>` | every socket, at connect |
| website | `website` | every socket at connect, Guests included |
| site | `all` | sockets with `user_type == "System User"` at connect |
| doctype | `doctype:<DT>` | on `doctype_subscribe` if `has_permission(doctype)` |
| doc | `doc:<DT>/<name>` | on `doc_subscribe` if `has_permission(doctype, name)` |
| open doc | `open_doc:<DT>/<name>` | on `doc_open` if `has_permission` |
| task | `task_progress:<id>` | on `task_subscribe` / `progress_subscribe` with NO permission check (`handlers.py:60-72`; node `handlers.js:43-56`) |

`publish_realtime(event, message, room=, user=, doctype=, docname=)` has no permission semantics: it sends to the room it computes (task -> user -> doc -> else `all`) (`:65-78`). The permission model is "the room membership was checked when the socket joined". A publish without `user`/`room`/`doctype+docname`/`task_id` goes to `all`, i.e. every System User of the site, regardless of app (`:77-78`; the docstring on `publish_to_all` says "System Users of THIS site", `:224`).

Join-time check: `socket.has_permission(doctype, name)` calls `GET /api/method/frappe.realtime.has_permission` as that user (`realtime/__init__.py:125-128`, `python auth.py:87-96`, `node handlers.js:12-27`). That function is overridable: Helpdesk overrides it via `override_whitelisted_methods` (`helpdesk-fork/helpdesk/hooks.py:134-136`) with `helpdesk.overrides.realtime.has_permission`, which refuses `HD Ticket` rooms to non-agents and otherwise delegates (`helpdesk-fork/helpdesk/overrides/realtime.py:7-17`). The same override mechanism is available for an app gate on rooms (FACT of mechanism; no such gate exists today).

Doctype rooms check doctype-level permission only (no doc, so no User Permissions or query conditions, `permissions.py:163-169`), yet core emits to them on every save: `Document.notify_update` publishes `list_update` with `{doctype, name, user}` (the modifying user) for non-single, non-child, non-read-only doctypes (`model/document.py:1760-1761`; `list_update` is routed to room `doctype:<DT>` by `realtime/__init__.py:59-61`) and `doc_update` with `{modified, doctype, name}` to the doc room (`document.py:1750-1756`). `Comment` and `Communication` publish `docinfo_update` carrying the whole comment/communication dict to `doc:<DT>/<name>` (`core/doctype/comment/comment.py:97-103`, `core/doctype/communication/communication.py:294-300`). So who sees document names and modifying users is decided by the doctype-level join check, and who sees comment/communication bodies by the doc-level join check; this is exactly why Helpdesk overrides the check for `HD Ticket` (`helpdesk-fork/helpdesk/overrides/realtime.py:8-13`).

### 4.4 Helpdesk realtime

FACT:

- App handlers on the node server load from `<app>/realtime/handlers.js` for each app in `socket.installed_apps` (`frappe/realtime/index.js:30-39,48-67`). Helpdesk ships `helpdesk-fork/realtime/handlers.js`.
- Helpdesk events `view_ticket`, `stop_view_ticket`, `ticket_get_viewers`, `notify_ticket_update`, `helpdesk_ticket_typing`, `helpdesk_ticket_typing_stopped` all use `open_doc:HD Ticket/<id>` rooms. `view_ticket` joins the room with no permission check; `notify_ticket_update` and typing events rebroadcast client-supplied `{ticket_id, user, field, value}` to the room (`helpdesk-fork/realtime/handlers.js:6-72`). Any authenticated socket (including a customer, a Helpdesk-less System User, or a Guest if the server accepts it) can join a ticket room by id and receive viewer lists and whatever other clients send (FACT of handler code; effect NOT VERIFIED). The stock `doc_open` path does check `has_permission`; Helpdesk's custom path does not.
- The Python realtime server finds app handlers at `<app>.realtime.handlers` (`realtime/README.md:11-16`); Helpdesk has no such module, so under the Python server these events are not handled at all (FACT: file absent).
- Server -> client events from Helpdesk: `publish_event(...)` defaults to the `website` room (everyone connected) with payload only `ticket_id` or nothing (`helpdesk-fork/helpdesk/utils.py:78-95`; `hd_ticket.py:66-70,182`; `api/comment.py:62-66`); `helpdesk:settings-updated` to `website` (`hd_settings.py:101-103`, `api/banners.py:32-35`); `notification` to a user room (`notifications.py:45,65`).
- Helpdesk's endpoint allow-list for non-system users includes `frappe.realtime.get_user_info`, `can_subscribe_doc`, `can_subscribe_doctype`, `has_permission` (`helpdesk-fork/helpdesk/auth.py:13-16`); `can_subscribe_*` do not exist in v16 (NOT FOUND) - stale entries from an older Frappe.

### 4.5 Limits for a central gate on realtime

- The socket server is a separate process. Its only link to Frappe authorisation is HTTP calls to the web process (`get_user_info`, `has_permission`). A gate implemented as a web-process hook (5.3, `auth_hooks`) would also cover socket connect, because the connect-time identity call is an ordinary request to `application()` carrying the user's `sid` or `Authorization` (loopback HTTP, or in-process WSGI when the python server is embedded: `python auth.py:180-181,189-196,218-248`, whose docstring says it "runs the real WSGI app, keeping session validation, permissions and the socket secret on the code path the HTTP transport uses"). A hook that raises there makes `get_user_info` fail, and both servers then refuse the connection (`python auth.py:265-266`, `node authenticate.js:86-88`). This is inference from the call flow (NOT VERIFIED).
- Room joins by event name that bypass `has_permission` (task rooms; Helpdesk `view_ticket`) cannot be reached by a web-process hook; they need a handler-level check.
- Install scoping exists in the python server: a handler runs only if its owning app is in the connecting site's `installed_apps` (`dispatch.py:85-86`), which is per site, not per user.

---

## 5. Request lifecycle hooks and where a central gate could run

### 5.1 Order inside `frappe.app.application` (FACT)

```
application(request)                                   app.py:108
  init_request(request)                                app.py:114 / 189
     frappe.init(site)  -> frappe.connect()             app.py:192,201
     maintenance mode check                             app.py:202-206
     make_form_dict(request)                            app.py:214 (body/query -> form_dict)
     frappe.local.http_request = HTTPRequest()          app.py:216-217
        -> LoginManager(): cookie sid -> Session        auth.py:33-51,124-144
           (or /api/method/login -> login(): before_login, authenticate,
            2FA, post_login: on_login, make_session -> on_session_creation)   auth.py:146-177,241
        -> CSRF check on unsafe verbs                   auth.py:81-97
     for hook in get_hooks("before_request"): call      app.py:219-220
  validate_auth()                                      app.py:116 / auth.py:625
     Authorization header: OAuth bearer, then API key/secret -> frappe.set_user   auth.py:629-636,691-743
     get_hooks("auth_hooks") each called                auth.py:636,746-748
     if header present and still Guest -> AuthenticationError   auth.py:640-641
     validate_ip_address if user changed                auth.py:647-648
  dispatch (cmd / /api/ / files / website)              app.py:118-154
except -> handle_exception -> response                  app.py:156-159
finally -> run_after_request_hooks (after_request)      app.py:164-173
process_response (headers, CORS, cookies)               app.py:176
ClosingIterator -> run_after_response_callbacks, frappe.destroy   app.py:90-105
```

Existing `before_request` hooks in Frappe: recorder, monitor, rate limiter, oauth CORS (`hooks.py:476-481`).

### 5.2 What each hook can see and do

| Hook | Runs | Sees resolved user? | Can block? | Notes |
|---|---|---|---|---|
| `before_request` | after cookie session + CSRF, before API-key/OAuth | Cookie user only. `init_request` (hooks at `app.py:219-220`) is called at `app.py:114`, `validate_auth` (API key / OAuth) at `app.py:116`, so for key/token requests `frappe.session.user` is still Guest when `before_request` runs (inferred from call order; NOT VERIFIED, see 9.9) | Yes - `init_request` is inside the `try`, so a raise becomes a normal error response (`app.py:113-114,156-159`) | Hooks also run for `OPTIONS`; `HTTPRequest` (session) is skipped for OPTIONS (`app.py:216-217`) so the user is not resolved there |
| `auth_hooks` | after cookie session, OAuth, API key | Yes: final user; may call `frappe.set_user` | Yes: raising -> error response | Called on every request that reaches `application()`, even with no `Authorization` header (`auth.py:636`); Helpdesk already uses it (`helpdesk-fork/helpdesk/hooks.py:169`) |
| `before_login` | start of `/api/method/login` or `cmd=login` | not yet authenticated | Yes (raise) | `auth.py:147` |
| `on_login` / `on_session_creation` | after successful auth / new session | yes | Yes (raise aborts login) | `auth.py:171,241`; ERPNext uses `on_session_creation` (`erpnext/erpnext/hooks.py:106`); only fires when a session is created, not on resume (`auth.py:240-241`) |
| `boot_session` / `extend_bootinfo` | when desk boot is built | yes | Only shapes the payload | `boot.py:99-100`, `sessions.py:173-174` |
| `after_request` | `finally`, after response built | yes | No (response exists; exceptions are swallowed `app.py:170-173`) | observation only |
| `before_job` / `after_job` | background workers | job user | n/a | `background_jobs.py:269,312` |
| `override_whitelisted_methods` | when a method name is resolved | n/a | Can replace a method by name | exact string match on dotted path (`__init__.py:1584`) |
| `override_doctype_class` | controller import | n/a | Can wrap a controller | must subclass original (`model/document.py:137-155`) |
| `page_renderer` | website path resolution | yes | Custom renderers are tried before static/web form/document/template/print/list renderers (`path_resolver.py:69-83,92-111`) | not consulted for `/desk` (hard-wired first, `:44-45`) |
| `website_route_rules`, `website_redirects`, `website_path_resolver` | website routing | no | redirect/rewrite | `path_resolver.py:51-59,140`, `website/path_resolver.py:233` |
| `has_permission` / `permission_query_conditions` (with `"*"`) | per doc check / per list query | yes | Deny only (has_permission) / narrow (query conditions) | section 1.7 |

### 5.3 Where a central "app-access gate" could run, and the limits (FACT of flow; viability NOT VERIFIED)

- Earliest point that sees every authentication mode: an `auth_hooks` callable (runs after cookie, OAuth and API key; `auth.py:625-648`). It can read `frappe.request.path`, `frappe.form_dict.cmd`, `frappe.session.user`, and raise `frappe.PermissionError`. Helpdesk's `helpdesk.auth.authenticate` is a working example of this exact position, including the `cmd` special case (`helpdesk-fork/helpdesk/auth.py:72-105`), but it only constrains non-System Users and only when `block_endpoints` is set in site config (`:73-74,82-83`).
- A `before_request` hook runs earlier but sees Guest for key/token calls (ASSUMPTION from line order; verify with 9.9).
- Request shapes a path-prefix gate must cover (FACT): `/api/method/<dotted>`, `/api/v1/method/...`, `/api/v2/method/<dotted>` and `/api/v2/method/<doctype>/<method>` (module path derived from the doctype, `api/v2.py:33-36`), `/api/resource/<dt>`, `/api/v2/document/<dt>`, `/api/v2/doctype/<dt>/...`, `/api/v2/mcp`, `/api/v2/discovery`, `?cmd=<dotted>` on any path (`app.py:121-130`), `POST /api/method/run_doc_method` (doctype in `dt` or inside the `docs` JSON, `handler.py:293-312`) and the doc-method routes (`/api/resource/<dt>/<name>?run_method=`, `/api/v2/document/<dt>/<name>/method/<m>`), `/private/files/...`, `/backups`, `/printview` and `www/*` pages, `/desk`, `/helpdesk`.
- Not reachable from Python: `/assets/*` and public `/files/*` in the reference nginx config (3.9); socket events that never call the web process (4.5). Both are by design public or separate-process.
- A gate keyed only on URL misses calls whose target app is inside the payload: `run_doc_method` (`dt` / `docs`), `frappe.client.*` (`doctype` argument), `frappe.desk.reportview.*`, `frappe.desk.search.search_link` (`doctype`), `frappe.desk.form.load.getdoc/getdoctype`, `frappe.desk.query_report.run` (`report_name`), `frappe.utils.print_format.download_pdf` (`doctype`), `frappe.desk.desk_page.getpage` (`name`), `frappe.desk.desktop.get_desktop_page` (`page` JSON). To gate these the owning app must be resolved from an argument (section 6).
- Handlers also call each other and reuse `frappe.get_all` internally; a gate at the HTTP edge does not affect server-side use, which is what one wants for system jobs (`before_job` is separate).

---

## 6. Mapping a request to its owning app

### 6.1 Lookups that exist

| From | Lookup | Cost / cache | Evidence |
|---|---|---|---|
| module name -> app | `frappe.local.module_app[scrub(module)]` (reverse map built from each installed app's `modules.txt`) | in-memory dict per request, built from `app_modules` cached in redis / client cache | `__init__.py:1041-1084`, `modules/utils.py:320-324` |
| doctype -> module | `frappe.modules.utils.get_doctype_module(doctype)`: redis-cached full map `doctype_modules`; throws `DoesNotExistError` for an unknown doctype | one redis get per call after first build; invalidated in `cache_manager.py:152` | `modules/utils.py:278-288` |
| doctype -> app | `frappe.get_doctype_app(doctype)`: `db.get_value("DocType", dt, "module")` then `module_app[scrub(module)]`; request-local cache; raises `KeyError` for a module not in any `modules.txt` | one DB read per doctype per request | `__init__.py:1470-1475` |
| doctype -> app (bulk) | `frappe.modules.utils.get_doctype_app_map()`: `DocType LEFT JOIN Module Def` -> `{doctype: Module Def.app_name}`; `@site_cache` (process memory, not shared across workers) | one query per process per site; app_name is `None` for modules without `app_name` | `modules/utils.py:327-337`, `utils/caching.py:78-143` |
| doctype -> app (production use) | `Notification Log.app` derived with `get_module_app(get_doctype_module(doctype))`, comment explains it avoids `get_doctype_app_map()` per insert; `None` for deleted/stale/custom doctypes | cached lookups | `desk/doctype/notification_log/notification_log.py:57-58,78-95` |
| doctype -> app (API telemetry) | `get_doctype_app_map().get(doctype)` in `api.handle` | same as above | `api/__init__.py:71-82` |
| whitelisted method -> app | first dotted segment of the path (`method.split(".", 1)[0]`); `frappe.get_attr` itself checks the segment is an installed app | string split, no I/O | `api/__init__.py:78-79`, `__init__.py:1134-1136` |
| page/report/workspace -> app | via `module` field: Page.module, Report.module (or `ref_doctype`'s module for reports without one, `query_report.py:212`), Workspace.module; app via `get_module_placement(module)` | one dict lookup, DB fallback `Module Def.app_name` with `cache=True` | `utils/modules.py:8-23`, `desk/desktop.py:504`, `desk/desk_views.py:156-160` |
| module -> app, including DB-only modules | `boot.get_boot_module_app()` folds `Module Def.app_name` for modules not in any `modules.txt`; docstring says server-side file resolution `get_module_app` deliberately stays modules.txt-based | one `get_all("Module Def")` per boot | `boot.py:171-186` |
| file -> doctype -> app | `File.attached_to_doctype` (+ `attached_to_name`) then doctype -> app as above; `File.has_permission` already resolves the attached doc (`file.py:1042-1057`) | per file | `file.py:1022-1059` |
| class path -> doc module | `frappe.modules.utils.get_doc_module(module, doctype, name)`: dotted path `{app}.{module}.{doctype}.{name}` | n/a | `modules/utils.py:46-54` |
| reverse (app -> modules) | `frappe.local.app_modules`, `get_modules_from_app(app)` (`Module Def.app_name`), `get_module_list(app)` (`modules.txt`) | redis_cache | `__init__.py:1083`, `utils/modules.py:147-149` |

Existing precedent worth noting (FACT): Frappe itself already stores the owning app next to some data (`Notification Log.app`, `notification_log.json:17,92`, backfill patch `patches/v16_0/backfill_notification_log_app.py`) and treats "app" as a placement concept for navigation (`utils/modules.py:11-15`: "Placement, never ownership").

### 6.2 Edge cases

FACT unless marked:

- Custom DocTypes: `import_controller` returns plain `Document` for `custom = 1` doctypes; their `module` is typically `Custom` or a user-made Module Def (`model/document.py:129-137`). `Custom` is a Frappe module (`frappe/frappe/modules.txt`), so by `module_app` they belong to `frappe`. A user-created Module Def may have empty `app_name` (`core/doctype/module_def/module_def.py:33-62`); then `get_doctype_app_map` yields `None` and `get_doctype_app` raises `KeyError` if the module is not in a `modules.txt`.
- Standard Frappe doctypes used by every app (`User`, `ToDo`, `Comment`, `File`, `Communication`, `Contact`, `Notification Log`, `DocShare`, `User Permission`, `Role`, `Assignment Rule`): app = `frappe`. `User` -> Core, `ToDo` -> Desk, `File`/`Comment`/`Communication` -> Core, `Contact` -> Contacts, `Notification Log` -> Desk (read from the JSON `module` field). A doctype-based app gate would classify these as "frappe", i.e. shared platform, not as any product app.
- ERPNext doctypes touched by Helpdesk: `Customer` -> module Selling -> erpnext; `Contact`/`Address` -> frappe. `Issue` (erpnext Support) coexists with `HD Ticket` -> Helpdesk module -> helpdesk (`helpdesk-fork/helpdesk/modules.txt` = `Helpdesk`).
- Helpdesk's HD-prefixed doctypes: all in module `Helpdesk` (JSON scan of `helpdesk/helpdesk/doctype/*/*.json` shows `"module": "Helpdesk"`); the module name `Helpdesk` maps to app `helpdesk` through `modules.txt`.
- ERPNext modules `Telephony` and `Communication` exist (`erpnext/erpnext/modules.txt`); the separate `telephony` app declares a module named `FTelephony` (`telephony/telephony/modules.txt` contains `FTelephony`, FACT from file content; likely a scaffold typo) so there is no module-name collision today. `get_hooks` warns on collisions and the later app wins (`__init__.py:1074-1081`).
- Child tables: permission delegates to the parent (`permissions.py:121-125,817-911`); app resolution would need `parenttype`.
- Virtual doctypes: bypass `get_list` DB path (`model/qb_query.py:124-153`: virtual doctypes get only a doctype-level check, then the controller's own `get_list`) and are served by their controller; module mapping is the same.
- Method paths can be overridden by `override_whitelisted_methods`, so the path in the URL may not be the executed method (`__init__.py:1582-1585`; Helpdesk overrides `frappe.realtime.has_permission`). The first segment of the final method decides the app only if resolved after the override.
- Server Script API methods (`_api`) are not Python modules at all and have no app (`handler.py:69-72`, `api/v2.py:40-43`).
- ERPNext "Setup" navigation sits in `code_only_modules` heirs; app placement of a module for navigation can differ from code ownership (`utils/modules.py:8-23,67-117`; `erpnext/erpnext/hooks.py:26-33` region).

---

## 7. How ERPNext relies on these mechanisms, and how Helpdesk layers its own checks

### 7.1 ERPNext

FACT:

- Authorisation model is almost entirely role DocPerm + User Permission link restrictions + per-controller code. `erpnext/erpnext/hooks.py` has NO `permission_query_conditions` and NO `has_permission` hook (grep of the whole `erpnext/erpnext` tree returns only `has_website_permission` implementations at `controllers/website_list_for_contact.py:293` and `support/doctype/issue/issue.py:317`). `has_website_permission` hooks cover Sales Order, Quotation, Sales Invoice, Supplier Quotation, Purchase Order/Invoice, Material Request, Delivery Note, Issue, Timesheet, Project (`hooks.py:335-347`).
- Row-level rules appear inside script reports and some doctype code through `build_match_conditions` and `get_user_permissions` (for example `accounts/report/general_ledger/general_ledger.py:333-335`, `accounts/party.py:8,390`, `accounts/doctype/payment_reconciliation/payment_reconciliation.py:9,81`). Link fields on ERPNext doctypes: 160 DocField definitions set `"ignore_user_permissions": 1` across 67 ERPNext doctype JSON files (grep count), which presupposes that the remaining Link fields are subject to User Permission scoping (Company, Territory, Warehouse, ...); this is the intended row-level mechanism (ASSUMPTION about intent; no ERPNext-specific user-permission creation found beyond Frappe core).
- Roles: business roles (`Sales User`, `Accounts Manager`, `Stock User`, ...) appear as DocPerm rows in doctype JSON and as Page/Report/Workspace roles. Pages are role-gated (2.1).
- API surface: 804 `@frappe.whitelist` functions in `erpnext/erpnext` (non-test, non-patch; AST count); 8 are `allow_guest` (`controllers/trends.py:340 get_period_date_ranges`, `templates/utils.py:12 send_message`, `templates/pages/search_help.py:26`, `www/banking.py:46`, `www/book_appointment/index.py:33,44,50,108`). A heuristic scan finds 338 whitelisted functions with no textual sign of a permission/only_for/get_list/get_doc call in their own body; that is a screening number only (many delegate to code that checks), not a defect count - ASSUMPTION that each needs review if an app gate is not added.
- App visibility: `add_to_apps_screen` with `has_permission = erpnext.check_app_permission` (`erpnext/erpnext/hooks.py:13-22`). `check_app_permission` returns True for Administrator and for every non-website user (`erpnext/erpnext/__init__.py:158-165`). A Helpdesk-only System User passes it. Framework's own app is hidden unless `System Manager` + System User (`frappe/permissions.py:962-966`).
- Portal: ERPNext adds `standard_portal_menu_items` and route rules (`/orders`, `/invoices`, ...; `hooks.py:148-257,259-333`) and `on_session_creation = erpnext.portal.utils.create_customer_or_supplier` which creates a Customer/Supplier + Contact for a Website User only if `Portal Settings.default_role` is `Customer`/`Supplier` and the user has that role (`erpnext/erpnext/portal/utils.py:22-59`). Helpdesk sets `default_role = "HD Customer"` (`helpdesk-fork/helpdesk/setup/install.py:232-246`), which makes this hook a no-op (inference from the two code paths).
- Boot: `boot_session = erpnext.startup.boot.boot_session`, `extend_bootinfo` add SLA doctypes and bootinfo (`hooks.py:100,706-709`).
- Shared data with Helpdesk: Custom Field `Customer.hd_customer` (hidden Data, created by Helpdesk `integrations/erpnext/utils.py:42-60`).

### 7.2 Helpdesk

FACT, `helpdesk-fork/helpdesk/`:

- Roles: `Agent`, `Agent Manager`, `HD Customer`, `HD Customer Manager`, plus `System Manager` and `Support Team` on DocPerm rows (JSON scan). HD doctypes give `System Manager` RWCD on essentially all of them.
- Helpers (`utils.py`): `is_agent(user)` - Administrator, else the `HD Agent.is_active` flag when a record exists, else role membership (`:46-61`); `agent_only` and `agent_manager_only` decorators throw `PermissionError` (`:181-195,209-223`); `check_permissions(doctype, parent, doc)` raises unless `select` or `read` (`:20-32`).
- Hooks (`hooks.py`): `permission_query_conditions` for `HD Ticket`, `HD Saved Reply`, `HD Customer` (`:119-123`); `has_permission` for `HD Agent`, `HD Ticket`, `HD Saved Reply`, `HD Customer`, and the shared `Comment` doctype (`:126-132`); `override_whitelisted_methods` for realtime (`:134-136`); `override_doctype_class` for `Email Account`, `Assignment Rule`, `User Invitation` (`:148-152`); `doc_events` on shared/ERPNext doctypes `Assignment Rule`, `Customer`, `User Permission`, `DocShare`, `Notification Log`, `Comment` (`:84-116`); `auth_hooks` (`:169`); `add_to_apps_screen` with `has_permission = helpdesk.api.permission.has_app_permission` (`:12-20`, `api/permission.py:3-17`: Administrator, or any of `Agent`, `Agent Manager`, `System Manager`, `HD Customer`, `HD Customer Manager`); `website_route_rules` `/helpdesk/<path>` -> `helpdesk` (`:57-62`).
- `HD Ticket`: `has_permission` allows Administrator, owner/raiser/contact, managers of the ticket's HD Customer, then agents (subject to team/assignment rules when `restrict_tickets_by_agent_group`) (`hd_ticket.py:1329-1375`); `permission_query` builds the matching SQL for lists; non-agents get their own tickets plus tickets of customers they manage (`:1378-1446`). These are the app's row-level rules; they run only after a role DocPerm already grants `read` (hooks cannot grant, `permissions.py:483-486`).
- `HD Customer`: member/manager rules (`hd_customer.py:462-483`); `HD Agent`: only self or manager may write/delete (`hd_agent.py:109-121`); `Comment`: for `reference_doctype == "HD Ticket"` hides comments from non-agents, otherwise returns True so other apps' comments are untouched (`extends/comment.py:57-79`).
- Customer visibility is contact-based: `get_customers(user)` joins `Contact(user)` -> `HD Customer Member` -> `HD Customer` (`utils.py:106-135`).
- Search: `helpdesk.api.search.search` uses a SQLite FTS index and post-filters results by ticket permission for non-agents (`search_sqlite.py:75-127`; `api/search.py:10-49`).
- Client-side only: the SPA router sends logged-out users to login and non-desk users to the customer view with `hasDeskAccess`/`isAgent` (`helpdesk-fork/desk/src/router/index.ts:229-256`). Nothing server-side depends on it.

### 7.3 Helpdesk-ERPNext integration (cross-app data bridge)

FACT, `helpdesk-fork/helpdesk/integrations/erpnext/`:

- When `ERPNext HD Settings.enabled` and ERPNext installed (`utils.py:19-22`), `HD Customer` and ERPNext `Customer` are linked (`Customer.hd_customer`, `HD Customer.erpnext_customer`), renamed/deleted together, and created in either direction with `ignore_permissions=True` (`api.py:59-126`, `customer.py:31,65`, `hd_customer.py:400,434,446`).
- `User Permission` rows with `allow` in (`HD Customer`, `Customer`) and `DocShare` rows with `share_doctype` in (`HD Customer`, `Customer`) are mirrored both ways through `doc_events` (`hooks.py:96-107`, `user_permission.py:12-44,47-104`, `doc_share.py:11-100`, `mirror_sync.py:27-136`). Consequence: granting a portal user membership/permission on an HD Customer can create a User Permission and DocShare on the ERPNext `Customer` record for that user. Whether that gives readable ERPNext data depends on role DocPerm (a DocShare grants read on the document even without a role row, `permissions.py:209-211`, `database/query.py:1653-1660`) - so this is a deliberate path by which a Helpdesk-side identity can see ERPNext `Customer` (FACT of mechanism; actual effect NOT VERIFIED).
- `frappe.whitelist` endpoints: `get_sync_info` (needs read on `HD Customer` and `Customer`) and `sync_hd_erpnext_customers` (write on both) (`api.py:9-56`).

### 7.4 Helpdesk endpoints that matter to the "no Helpdesk access" and "no ERPNext access" rules

108 `@frappe.whitelist` functions in `helpdesk-fork/helpdesk` (AST scan, non-test, non-patch). Full lists in Appendix A. Summary:

- `allow_guest=True`: `api/config.py:get_config`, `api/general.py:get_translations`, `api/knowledge_base.py:get_article`, `www/helpdesk/index.py:get_context_for_dev` (dev mode only).
- No `agent_only`, no explicit permission call (reachable by any logged-in user, including an ERPNext-only System User with no HD role, unless the body does something later): e.g. `api/knowledge_base.py` (`delete_articles`, `create_category`, `get_general_category`, `get_category_title`, `increment_views`; the doc operations they call still run DocPerm checks), `api/search.py:search`/`get_filter_options` (post-filtered), `helpdesk/doctype/hd_ticket/api.py:new`, `get_one` (checks), `hd_ticket.py:get_last_communication`, `mark_seen`, `api/onboarding.py:get_first_ticket`, `api/timeline.py:get_ticket_calls`.
- `ignore_permissions=True` in reachable code: `api/ticket.py:86 delete_ticket` (guarded by `is_admin()`), `api/comment.py:56` (reactions, preceded by permission checks), `api/contact.py:157`, `hd_ticket.py:733 reply_via_agent` (`agent_only`), `hd_ticket.py:805-834 create_communication_via_contact`, `api/tags.py:66`, analytics (`api/ticket_analytics.py:94,271,292,314`, `agent_only`). Full list in Appendix A. None of these were exploited or tested.

### 7.5 What Helpdesk's own block of non-system users does

`helpdesk-fork/helpdesk/auth.py` (`auth_hooks` entry): when site config `block_endpoints` is set, any `/api/` request by a user whose `user_type != "System User"` is refused unless the path is in `ALLOWED_PATHS` (exact string match), starts with `/api/method/helpdesk.` or `/api/method/telephony.`, matches `WILDCARD_PATHS`, is a Server Script API, or contains an entry from `allowed_custom_endpoints` (`:72-105`). Observations (FACT of code):

- It does nothing for System Users (`:82-83`), so it does not separate agents from ERPNext.
- `ALLOWED_PATHS` includes the generic `frappe.client.get_list/get/get_value/insert/set_value/delete/rename_doc`, `frappe.desk.search.search_link`, `frappe.desk.form.load.getdoctype`, `run_doc_method`, `frappe.desk.reportview.export_query` and `frappe.utils.print_format.download_pdf` (`:45-64`). A portal customer is therefore still able to call these on any doctype; DocPerm decides.
- Matching is on `frappe.request.path`, so `/api/v2/...` and `/api/v1/...` forms of the same methods are not in the list (`:78-80,103`); for non-system users they are refused unless `helpdesk.`-prefixed in the old `/api/method/` form (the check uses `startswith("/api/method/helpdesk.")`). ASSUMPTION: this is incidental.
- It is inert when `block_endpoints` is unset (`:73-74`). Runtime state NOT VERIFIED.

---

## 8. Coverage table (per enforcement surface)

Legend for "Stops Helpdesk-only user from ERPNext data": YES = the code path refuses by role/permission; PARTIAL = only if ERPNext DocPerm has no role the user holds (relies on role separation, not on app separation); NO = not checked. "Helpdesk-only user" = a user whose roles are only Helpdesk roles (Agent family, a System User per 1.2) or only `HD Customer*` (Website User). All "stops" statements are conditional on the ERPNext doctype rows not granting `All`/`Desk User`/the user's role (section 1.8).

| # | Surface | Who enforces today (file:line) | What it checks | Stops Helpdesk-only user using ERPNext data? | Gap |
|---|---|---|---|---|---|
| 1 | `/desk` and `/desk/<path>` (v16; `/app/*` and `/apps` redirect here) | `frappe/frappe/website/path_resolver.py:44-45`, `frappe/frappe/www/desk.py:50-62`, `hooks.py:68-72` | Login; user_type != Website User. No role/module/app check | NO. Any System User gets the full desk shell and boot (`boot.py:34-138`). Data still needs DocPerm | App-level access to the shell is not gated. Desk shows ERPNext tile to any non-website user (`erpnext/__init__.py:158-165`) |
| 2 | Desk metadata loaders (`getpage`, `get_desktop_page`, `get_workspaces`, boot `module_app`, `desk.get_installed_apps`) | `desk/desk_page.py:7-31`; `desk/desktop.py:365-390,429-523`; `desk/desktop.py:738-740` | Page roles; per-widget permission; Workspace roles + `block_modules` in the list builder only | PARTIAL. `getpage` honours Page roles; `get_desktop_page` does not call `is_permitted` (`desktop.py:365-390`); `/api/resource/Workspace` readable to Desk User | Workspace/Page/Report roles and `block_modules` are navigation filters. App/workspace names and structure of ERPNext are enumerable by any System User (runtime NOT VERIFIED) |
| 3 | `/helpdesk` SPA HTML (`www/helpdesk/index.py`) | `helpdesk-fork/helpdesk/www/helpdesk/index.py:13-54` | No login check at all. `get_context` builds `boot` with `apps: frappe.get_installed_apps()`, `session_user`, `agent` and hands it to the template (`index.py:13-20,30-54`). Whether the built HTML prints `boot` is NOT VERIFIED: the source template `desk/index.html` only uses `boot.lang`, `boot.dir`, `site_name`; the frappe-ui build plugin that rewrites it (`desk/vite.config.js:21-28`) is not in the tree (`helpdesk-fork/frappe-ui` is empty) | NO (nothing to stop; it is a shell). Server returns it to Guest | Installed-apps list is computed for Guest and may be rendered into the page (NOT VERIFIED); real gating relies on later API calls. SPA router guard is client-only (`desk/src/router/index.ts:229-256`) |
| 4 | `/assets/*` incl. `/assets/helpdesk/desk/*`, `/assets/erpnext/*` | nginx `location /assets` (`frappe_docker/.../nginx-template.conf:31-33`); dev server `app.py:554` | Nothing (static) | n/a (code is public). No data | By design public; no gate possible in Python in the reference deployment |
| 5 | `/api/method/<dotted>` and `?cmd=` | `handler.py:65-110`, `__init__.py:439-497`; `app.py:121-130`; per-method code | Method whitelisted; Guest needs `allow_guest`; HTTP verb. Then whatever the method does | PARTIAL. Frappe generic methods enforce DocPerm; ERPNext methods vary (804 whitelisted; 338 without an obvious check in their own body); Helpdesk methods use `agent_only` or DocPerm | No app/module gate. Any whitelisted ERPNext method is callable by any logged-in user, including Guest for the 8 `allow_guest` ones. The per-method check is the only barrier |
| 6 | `/api/resource/*` (v1) and `/api/v2/document/*`, `/api/v2/doctype/*` | `api/v1.py:12-153`, `api/v2.py:80-221`, `client.py`, `permissions.py:81-226`, `database/query.py:1590-1734` | DocPerm role rights, `if_owner`, User Permissions, `permission_query_conditions`, `has_permission` hooks, shares, permlevels | YES if the user has no ERPNext role rows. Not an app gate; works only because role names differ | `/api/v2/doctype/<dt>/meta` and `getdoctype` return meta to any logged-in user without a read check (`api/v2.py:219-221`, `desk/form/load.py:62-90`). Shared doctypes (`File`, `ToDo`, `Contact`, `Comment`, `Communication`) are readable per their own rules for every app |
| 7 | Reports (`query_report.run/get_script/export_query`, `reportview.*`) | `desk/query_report.py:29-63,209-343,441-475`; `desk/reportview.py:30-118,444-475` | Report roles (`Has Role`/`Custom Role`), `report` right on `ref_doctype`, filter-link permissions; list-style views use `get_list` | YES for roles/DocPerm; PARTIAL for script reports (their SQL decides row rules) | Script reports with unrestricted SQL are protected only by Report roles + `report` right; no app dimension. `can_export` always true for System Manager (`permissions.py:657-658`) |
| 8 | Print / PDF (`download_pdf`, `/printview`, `get_html_and_style`) | `utils/print_format.py:371-409`, `www/printview.py:536-556` | read or print on doc; website permission; share key | YES by DocPerm/doc permission | `download_pdf` is `allow_guest`; a leaked `key` share link works for anyone. No app dimension |
| 9 | File download: `/private/files/*`, `download_file` | `app.py:138-139`, `utils/response.py:294-306`, `core/doctype/file/file.py:1022-1059`, `core/doctype/file/utils.py:462-475`, `handler.py:258-274` | Guest refused for private; otherwise `File.has_permission` -> inherits attached document's read permission | YES for attachments of ERPNext documents (inherit doc permission). Unattached private files only to owner | Public `/files/*` served by nginx without session (`nginx-template.conf:53-65`) - capability URL. Files with no `attached_to_*` follow owner rule only |
| 10 | File upload `/api/method/upload_file` | `handler.py:128-255` | Doc write permission only if `doctype` passed; MIME limit for non-desk users | PARTIAL | Upload without `doctype` creates an unattached private/public File for any logged-in user (`:174-175`) |
| 11 | Websocket / realtime (node port 9000 via nginx `/socket.io`, or python server) | `frappe/realtime/index.js:30-39`, `frappe/realtime/middlewares/authenticate.js:13-85`, `frappe/realtime/handlers.js:4-106`; python `frappe/frappe/realtime/*.py`; `helpdesk-fork/realtime/handlers.js`; `helpdesk-fork/helpdesk/overrides/realtime.py:7-17` | Session via `get_user_info` + secret; room joins via `frappe.realtime.has_permission` (doctype / doc level). `task_*` rooms: none. Helpdesk `view_ticket`: none | PARTIAL. Doc/doctype subscriptions to ERPNext doctypes need DocPerm; `all` room gets every System User's broadcast; task rooms unauthenticated by id | Unscoped `publish_realtime` reaches all System Users (any app). Helpdesk `view_ticket` joins by id without a check (node). No app dimension on connect |
| 12 | Website/portal pages (`/me`, `/portal`, `/list?doctype=`, `/orders`, `/invoices`, `www/*`, web forms) | `www/me.py:11-17`, `www/portal.py:13-27`, `www/list.py:32-95,173-221`, ERPNext `has_website_permission` hooks (`erpnext/hooks.py:335-347`), `__init__.py:652-700` | Login for `/me`; `/portal` and `/list` use `frappe.get_list` (permissions on) unless `allow_guest_to_view`; per-doctype `has_website_permission` for single-doc portal pages | YES via DocPerm + website permission for a Website User with only `HD Customer*` roles; ERPNext portal list routes (`/orders`, `/invoices`, ...) are registered globally (`erpnext/hooks.py:148-257`) | `/portal` and `/list` take `doctype` from the URL: any doctype is attempted against DocPerm; no app filter. Portal menu is built from hooks regardless of whether the user "uses" the app (`website/utils.py:465-488`) |
| 13 | `/apps` launcher / `frappe.apps.get_apps` | `apps.py:36-73`, `boot.py:289-322`, hooks `add_to_apps_screen` (`erpnext/hooks.py:13-22`, `helpdesk-fork/helpdesk/hooks.py:12-20`, `frappe/hooks.py:579-589`); `/apps` is itself a redirect to `/desk` (`hooks.py:68-72`) | Per-app `has_permission` callable (`erpnext.check_app_permission`, `helpdesk.api.permission.has_app_permission`, `frappe.permissions.check_app_permission`) | NO for ERPNext: `check_app_permission` is True for any non-website user (`erpnext/__init__.py:158-165`) | Display only. Even a correct callable hides a tile; it does not stop a URL or API call. (Part 1 covers launcher flow.) |
| 14 | `/login`, `/logout`, `/api/method/login`, `logout` | `www/login.py:25-41`, `auth.py:124-177`, `handler.py:113-125`, hooks `before_login`, `on_login`, `on_session_creation` | Credentials, 2FA, IP, hours; login hooks may raise | n/a (authentication). Hooks (`on_login`, `on_session_creation`) can block or redirect but see no target app | `/login` already redirects logged-in users to `redirect-to` or `get_default_path()`/`/desk` (`www/login.py:32-41`) |
| 15 | `/api/v2/mcp`, `/api/v2/discovery/*` | `api/v2.py:278-293`, `api/discovery.py:29-110`, `mcp/transport.py:29-48` | `Desk User` role; MCP reuses doc permissions | PARTIAL: reads follow DocPerm; discovery lists all whitelisted methods (all apps) and method source to any System User (`hooks.py:576`) | Reveals ERPNext API surface to Helpdesk-only System Users |
| 16 | `/backups`, `/.well-known/*` | `app.py:135,141-148` | `download_backup` own checks (not read) | NOT VERIFIED | Not analysed |

Cross-cutting FACTs behind the table:

- Frappe does not check "does this user belong to this app" anywhere in handler, API, DB query or permission code (section 5.3 and the exhaustive `is_module_visible` consumer list in 2.5).
- Everything that separates Helpdesk from ERPNext today is: disjoint role names, `agent_only`-style decorators inside Helpdesk, and Helpdesk's `has_permission`/`permission_query_conditions` hooks on its own doctypes. None of those prevent an ERPNext-only user from calling Helpdesk's non-agent endpoints or reading Helpdesk doctypes where roles overlap through `System Manager`, `Desk User` or `All`.

---

## 9. Runtime verification list

Setup assumption: a site at `http://localhost:8100` with ERPNext and Helpdesk installed, and these seeded test users (names are placeholders):

- `t_admin` - System Manager (control).
- `t_agent` - roles: `Agent` only (system user via default `desk_access = 1`; confirm `user_type`).
- `t_cust` - roles: `HD Customer` only, `user_type = Website User`.
- `t_sales` - roles: `Sales User` (ERPNext) only.
- `t_blocked` - roles: `Sales User` + `Accounts User`, with `block_modules` listing `Selling` and `Accounts`.
- Seed at least one `Sales Invoice` (or any ERPNext doctype), a `Customer`, an `HD Ticket` owned by someone else, and a private `File` attached to the Sales Invoice.

Helper (login and cookie jar, replace passwords from the seed script, do not paste real secrets into notes):

```bash
BASE=http://localhost:8100
login() { curl -s -c /tmp/$1.jar -X POST $BASE/api/method/login -d "usr=$1" -d "pwd=$2" ; }
call()  { u=$1; shift; curl -s -b /tmp/$u.jar -H "Accept: application/json" "$@"; }
```

### 9.1 A Helpdesk-only user gets 403 on ERPNext resources (claims 6/1.9, row 6)

Claim: with no ERPNext role row, DocPerm blocks `/api/resource/Sales Invoice` and `/api/v2/document/Sales Invoice` for `t_agent` and `t_cust`.

```bash
call t_agent -o /dev/null -w "%{http_code}\n" "$BASE/api/resource/Sales%20Invoice?limit_page_length=1"
call t_agent -o /dev/null -w "%{http_code}\n" "$BASE/api/v2/document/Sales%20Invoice?limit=1"
call t_cust  -o /dev/null -w "%{http_code}\n" "$BASE/api/resource/Customer?limit_page_length=1"
call t_agent -o /dev/null -w "%{http_code}\n" "$BASE/api/method/frappe.client.get_count?doctype=Sales%20Invoice"
# control
call t_admin -o /dev/null -w "%{http_code}\n" "$BASE/api/resource/Sales%20Invoice?limit_page_length=1"
```

Expected (if the claim holds): 403 (or 200 with empty list only if the user has a role on the doctype). Refute: any 200 with rows for `t_agent`/`t_cust`. Also record whether `Customer` is readable via the DocShare/User Permission mirror (7.3): create an HD Customer membership for `t_cust` with the ERPNext integration enabled and re-run the `Customer` call.

### 9.2 `block_modules` does not block `/api/method` or `/api/resource` (2.5)

```bash
# as t_blocked (Selling/Accounts blocked, roles Sales User/Accounts User)
call t_blocked "$BASE/api/resource/Sales%20Invoice?limit_page_length=1"
call t_blocked "$BASE/api/method/frappe.desk.form.load.getdoctype?doctype=Sales%20Invoice" | head -c 200
call t_blocked "$BASE/api/method/frappe.desk.desktop.get_desktop_page" -G --data-urlencode 'page={"name":"Selling","title":"Selling","public":1}' | head -c 300
```

Expected: first two return data; the desktop call returns widgets only for permitted items, while `/desk` navigation hides Selling. Refute: first call 403 for the blocked user.

### 9.3 Metadata endpoints are reachable without read permission (3.4, 3.6)

```bash
call t_agent "$BASE/api/method/frappe.desk.form.load.getdoctype?doctype=Sales%20Invoice" | head -c 300
call t_agent -o /dev/null -w "%{http_code}\n" "$BASE/api/v2/doctype/Sales%20Invoice/meta"
call t_cust  -o /dev/null -w "%{http_code}\n" "$BASE/api/v2/doctype/Sales%20Invoice/meta"
call t_cust  -o /dev/null -w "%{http_code}\n" "$BASE/api/method/frappe.desk.form.load.getdoctype?doctype=Sales%20Invoice"
```

Expected per code: 200 for any logged-in user (schema plus `permissions` list). Refute: 403 for the non-ERPNext users. Note: if `block_endpoints` is configured, `t_cust` hits Helpdesk's allow-list instead (7.5): run once with and once without `bench set-config block_endpoints 1` and record both.

### 9.4 Desk access, launcher and discovery for a Helpdesk-only System User (1.2, 7.1, 3.4, coverage rows 1, 13, 15)

```bash
call t_agent -o /dev/null -w "%{http_code}\n" $BASE/desk
call t_agent "$BASE/api/method/frappe.apps.get_apps"
call t_agent "$BASE/api/method/frappe.desk.desktop.get_installed_apps"
call t_agent "$BASE/api/v2/discovery/search?q=sales" | head -c 400
call t_cust  -o /dev/null -w "%{http_code}\n" $BASE/desk
```

Expected per code: `/desk` 200 for `t_agent`, 403 for `t_cust`; `get_apps` lists `erpnext` for `t_agent` (and `helpdesk`); discovery returns ERPNext methods. Refute any of these. Also check `user_type` of `t_agent` in `bench console`:

```python
frappe.db.get_value("User", "t_agent", "user_type")
frappe.get_roles("t_agent")
frappe.db.get_value("Role", "Agent", "desk_access")
```

### 9.5 Workspace and Report enumeration by role (2.2, 2.4)

```bash
call t_agent "$BASE/api/resource/Workspace?fields=%5B%22name%22,%22module%22%5D&limit_page_length=200" | head -c 600
call t_agent "$BASE/api/resource/Report?fields=%5B%22name%22,%22ref_doctype%22%5D&limit_page_length=20" | head -c 400
call t_agent "$BASE/api/method/frappe.desk.desk_page.getpage?name=point-of-sale" | head -c 200
call "" -o /dev/null -w "%{http_code}\n" "$BASE/api/method/frappe.desk.desk_page.getpage?name=print"   # Guest, page with no roles
```

Expected per code: first two list ERPNext items (Desk User rows); `getpage` for `point-of-sale` is 403 for `t_agent` (Page roles enforced); Guest can load `print`. Refute otherwise.

### 9.6 Files and print for ERPNext documents (3.7, 3.8)

```bash
# private attachment of the Sales Invoice (get file_url as t_admin first)
call t_agent -o /dev/null -w "%{http_code}\n" "$BASE/private/files/<attached-file-name>"
call t_agent -o /dev/null -w "%{http_code}\n" "$BASE/api/method/frappe.utils.print_format.download_pdf?doctype=Sales%20Invoice&name=<name>"
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/private/files/<attached-file-name>"            # Guest
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/files/<a-public-file>"                          # public file, no cookie
```

Expected: 403/permission error for `t_agent` and Guest on the private file and PDF; 200 for the public file without any cookie (capability URL). Refute: 200 on the private file for `t_agent`.

### 9.7 Realtime (4.3, 4.4, coverage row 11)

Use the socket.io client in a scratch directory (not in the source tree). Connect as `t_cust` with their `sid` cookie to `ws://localhost:9000/<site-name>` (or through `/socket.io` on port 8100), then:

```js
socket.emit("doc_subscribe", "Sales Invoice", "<name>");   // expect no join
socket.emit("view_ticket", "<HD Ticket id not readable by t_cust>");  // node server: expect join
socket.emit("task_subscribe", "<any id>");                   // expect join without check
```

Then as `t_admin` trigger `frappe.publish_realtime("test", {"x":1})` from `bench console` (no user/room) and observe whether `t_agent` (System User) receives it on room `all`. Expected per code: `doc_subscribe` refused, `view_ticket` and `task_subscribe` accepted on the node server, global publish received by System Users only. Record which server runs (`docker compose ps`/process list) - 4.1.

### 9.8 Helpdesk endpoints reachable by non-agents (7.4, Appendix A)

```bash
call t_sales "$BASE/api/method/helpdesk.api.knowledge_base.get_categories"
call t_sales "$BASE/api/method/helpdesk.api.search.search?query=test"
call t_sales "$BASE/api/method/helpdesk.api.doc.get_list_data?doctype=HD%20Ticket"
call t_sales "$BASE/api/method/helpdesk.api.auth.get_user"
curl -s "$BASE/api/method/helpdesk.api.config.get_config"                       # Guest
curl -s "$BASE/helpdesk" | grep -o '"apps":[^]]*]'                              # installed apps in Guest boot
```

Expected per code: a user with no HD role gets DocPerm errors on HD doctypes but is not stopped by an app check; `get_config` and the `/helpdesk` boot answer Guest. Refute if the `apps` array is absent from the Guest response (whether the built template prints `boot` is not visible in the source tree).

### 9.9 Ordering of `before_request` vs token auth (5.2)

Not possible without instrumentation. In a scratch app (not in the tracked tree) add a `before_request` hook that logs `frappe.session.user` and an `auth_hooks` entry that logs the same, then:

```bash
curl -s -H "Authorization: token <key>:<secret>" "$BASE/api/method/frappe.auth.get_logged_user"
```

Expected per code: before_request logs `Guest`, auth_hooks logs the API user. Refute otherwise.

### 9.10 Realtime and helpdesk allow-list state (7.5)

```python
frappe.conf.get("block_endpoints"), frappe.conf.get("allowed_custom_endpoints")
frappe.get_hooks("auth_hooks")
frappe.get_hooks("before_request")
```

Record values; the Helpdesk gate is inert without `block_endpoints`.

---

## 10. Implications for NXERP

Format: fact -> implication. These are findings, not a design.

1. FACT: no code in `handler.py`, `api/*`, `permissions.py` or `database/query.py` reads app, module or `block_modules` (2.5, 5.3); the framework text says module visibility "must never" be a security boundary (`utils/modules.py:50-52`). -> "Hide ERPNext from Helpdesk-only users" cannot be achieved with Block Module / Module Profile / Workspace roles / `add_to_apps_screen.has_permission`; those are navigation. Any real separation either relies on role separation per doctype or on an added server-side check.
2. FACT: Frappe's authorisation is role-name based and additive across apps; `Desk User`, `All` and `System Manager` carry rights in many doctypes of every app (1.8, 7.2). -> Role separation protects ERPNext only while Helpdesk roles never appear on ERPNext doctypes and no user holds `System Manager`; any overlap is silent.
3. FACT: the existing precedent for a cross-cutting gate is `auth_hooks` (`auth.py:746-748`; Helpdesk `auth.py:72-105`); it sees the final user for cookie, OAuth and API-key requests, can raise, and covers realtime connect because the socket asks the web process for identity (4.2, 5.3). -> That is the only single point before dispatch that can be applied to all HTTP modes; its inputs are path, `cmd`, user, and the request body. `before_request` sees Guest for key/token requests (to be proven by 9.9).
4. FACT: the app of a request cannot be read from the URL for payload-carrying calls (`run_doc_method`, `frappe.client.*`, `reportview`, `search_link`, `getdoctype`, `download_pdf`, `getpage`, `get_desktop_page`, `query_report.run`) (5.3). -> A gate needs a resolver per argument kind; lookups already exist (doctype -> module -> app via redis-cached maps, section 6.1) and one is already called in the dispatch path for telemetry (`api/__init__.py:71-82`).
5. FACT: shared doctypes (`User`, `File`, `ToDo`, `Comment`, `Communication`, `Contact`, `Notification Log`, `DocShare`, `User Permission`) resolve to app `frappe` and are used by both products (6.2); Helpdesk already narrows `Comment` by `reference_doctype` inside the doctype's `has_permission` hook (`extends/comment.py:57-69`) and `File` inherits attached-doc permission (`file.py:1042-1057`). -> App-aware behaviour on shared doctypes has to key on the referenced document's doctype, not on the shared doctype's own app; there is working in-tree precedent for both.
6. FACT: `has_permission` hooks can only deny and are not called for doctype-level checks; `permission_query_conditions` applies only to permissioned list queries; both accept `"*"` (1.1, 1.7). -> A wildcard hook is a possible enforcement point for document and list access under the standard model but does not cover `frappe.db.*`, `get_all`, `get_doc` without `check_permission`, page/report/method paths, files served by nginx, or sockets.
7. FACT: `/assets/*` and public `/files/*` are served by nginx without Python, `/helpdesk` HTML is rendered without login and its server-side `boot` includes the installed-apps list (whether it is printed into the page is NOT VERIFIED) (3, 8 rows 3-4, 9). -> Product separation cannot be claimed for static bundles or the shell HTML; only data endpoints can be gated. Public files remain capability links.
8. FACT: ERPNext's `check_app_permission` returns True for any non-website user (`erpnext/erpnext/__init__.py:158-165`), `/desk` admits any System User, and `Desk User` can read `Workspace`, `Report`, `Module Def` and list all discoverable methods (1.8, 3.4). -> Today a Helpdesk agent sees ERPNext in the launcher and can enumerate ERPNext structure; the data itself is still protected by DocPerm.
9. FACT: Helpdesk bridges to ERPNext by design: Customer link, mirrored User Permissions and DocShares, `ignore_permissions` inserts (7.3). -> Any "Helpdesk users never see ERPNext" rule has an explicit exception path that must be decided (and tested, 9.1) rather than assumed away; this is where a Helpdesk-side identity can acquire read access to ERPNext `Customer`.
10. FACT: custom permission rows (`Custom DocPerm`) replace shipped DocPerm for a doctype and survive upgrades (1.3); Helpdesk already created them for `File`, `Contact`, `Email Account`, `Communication`, `HD Ticket`. -> Role-based separation is site state, not only code; it must be verified on the live site, not on the repo.
11. FACT: realtime has gaps independent of the permission system (task rooms without checks; Helpdesk node `view_ticket` joins without checks; global publish goes to all System Users) (4.3-4.4). -> A web-process gate does not cover those; they need their own review if sockets are in scope.
12. FACT: the Python realtime server lives in v16.53 but the reference deployment runs the node server; Helpdesk's realtime handlers exist only for node (4.1, 4.4). -> Which server runs is a prerequisite fact for any realtime decision (NOT VERIFIED).
13. FACT: v16 has new surfaces the brief did not list: `/api/v2/mcp`, `/api/v2/discovery/*`, field masking, `Desktop Icon`, `Dock`, `Sidebar` (2.6, 3.4). -> They need to be inside any coverage claim.
14. ASSUMPTION: ERPNext has about 800 whitelisted functions; roughly 40 percent have no permission-looking call in their own body (7.1). -> Treat "ERPNext methods enforce permissions" as unproven for those until reviewed or covered by a gate.
15. FACT: Helpdesk's own non-system-user filter is opt-in (`block_endpoints`) and exact-path based and exempts System Users (7.5). -> It is not a substitute for an app gate and should not be counted as one.

---

## Appendix A. Helpdesk endpoint lists (AST scan of `helpdesk-fork/helpdesk`, excluding tests and patches)

Generated by parsing every `@frappe.whitelist` function and its decorators. Paths are relative to `helpdesk-fork/helpdesk/`; "guards" is a textual hint of what is in the function body, not a proof.

### A.1 `allow_guest=True`

| File:line | Function | Notes |
|---|---|---|
| `api/config.py:5` | `get_config` | Returns brand fields and HD Settings flags (`restrict_tickets_by_agent_group`, `assign_within_team`, ...) to anyone |
| `api/general.py:6` | `get_translations` | Methods GET only |
| `api/knowledge_base.py:11` | `get_article` | Published articles only for non-agents (`:12-14`) |
| `www/helpdesk/index.py:24` | `get_context_for_dev` | Refuses unless `developer_mode` (`:25-26`) |

### A.2 Uses `ignore_permissions=True` (non-test, non-patch occurrences)

| File:line | Context |
|---|---|
| `api/comment.py:56` | Reaction insert, inside `toggle_reaction` |
| `api/contact.py:157` | `user_doc.save`, inside `edit_contact` |
| `api/tags.py:66` | Tag insert, `update_tags` (`agent_only`) |
| `api/ticket.py:86` | `delete_ticket`; function checks `is_admin()` first (`:80-85`) |
| `api/ticket_analytics.py:94,271,292,314` | Analytics reads, `agent_only` |
| `helpdesk/doctype/hd_ticket/api.py:263,385` | `merge_ticket`, `split_ticket` (`agent_only`) |
| `helpdesk/doctype/hd_ticket/hd_ticket.py:733,819,832,834,1124,1510` | `reply_via_agent` (`agent_only`), `create_communication_via_contact`, file and doc saves |
| `helpdesk/doctype/hd_customer/hd_customer.py:131,400,434,446` | ERPNext Customer insert/delete and ticket deletion on HD Customer deletion |
| `helpdesk/doctype/hd_agent/hd_agent.py:106`, `hd_agent_status.py:65`, `hd_team/hd_team.py:33,42,61,80`, `hd_settings/hd_settings.py:90,92`, `hd_email_feedback.py:49` | Internal saves |
| `integrations/erpnext/*` (`api.py:98,125`, `customer.py:31,65`, `doc_share.py:77,99`, `mirror_sync.py:60,96,121,136`, `user_permission.py:82,103`, `utils.py:134,144,154`) | Bidirectional sync with ERPNext `Customer`, `User Permission`, `DocShare` |
| `helpdesk/hooks/user_invitation.py:67,72`, `overrides/email_account.py:127`, `nxerp_branding.py:51`, `setup/*` | Setup/invitation paths |

### A.3 Whitelisted with no `agent_only`/`agent_manager_only` decorator

(Any logged-in user may call them; authorisation is only what the body does.)

`api/article.py:62 get_article_stats` (body calls `is_agent`), `:93 search`; `api/assignment_rule.py:5`; `api/auth.py:8 get_user`; `api/banners.py:14 get_banners`; `api/comment.py:11,72,104`; `api/contact.py:12,40,77,117,163`; `api/customer.py:8,61`; `api/doc.py:23 get_list_data` (generic doctype argument, `frappe.get_list`), `:248 get_filterable_fields`, `:391 sort_options`, `:420 get_quick_filters`; `api/knowledge_base.py:47,53,68,90,106,121,143,150,156`; `api/onboarding.py:32,52`; `api/search.py:11 search`, `:53 get_filter_options`; `api/settings/email.py:15`, `email_notifications.py:97-187` (`only_for`), `field_dependency.py:8,37`; `api/timeline.py:12,44`; `extends/data_import.py:7 bulk_insert`; `helpdesk/doctype/hd_agent/hd_agent.py:124 update_agent_role` (`only_for`); `hd_article.py:98`; `hd_customer.py:241 add_contacts`, `:338 get_pending_invites`; `hd_notification/utils.py:5`; `hd_service_holiday_list.py:23,107,112`; `hd_settings/helpers.py:97`; `hd_ticket/api.py:21 new`, `:31 get_one`, `:402`, `:488`, `:508`, `:563`, `:599`; `hd_ticket/hd_ticket.py:544,612,805,936`; `hd_ticket_template/api.py:13`; `integrations/erpnext/api.py:10,42`; `notifications.py:85`; `overrides/realtime.py:8`; `search.py:359 build_index`.

### A.4 Role helper semantics (for reading the above)

- `agent_only` throws `PermissionError` unless `is_agent()` (`utils.py:181-195`); `is_agent` returns True for Administrator, for a record with `HD Agent.is_active`, or for holders of `Agent` / `Agent Manager` (`utils.py:46-61`).
- Admin-only guard in `delete_ticket`: `is_admin()` means literally the `Administrator` user (`utils.py:35-43`), not `System Manager`.
