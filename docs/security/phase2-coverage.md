# Phase 2 enforcement coverage

Maps every surface of the Phase 1 coverage table (`docs/research/frappe-access-and-routing.md`) to what enforces it now
and the test that proves it. "Gate" = `nxerp.enforcement.auth_hook`; "doc" = wildcard `has_permission`; "list" = wildcard
`permission_query_conditions`; "after" = `after_request` sanitiser.

| # | Surface | Phase 2 enforcement | Evidence |
| --- | --- | --- | --- |
| 1 | `/desk`, `/desk/*`, `/app/*` | Gate (page): ERPNext staff or platform-admin shell; guests to login; others to no-access | matrix "desk URL"; `test_desk_pages`, `test_legacy_app_prefix_is_gated_like_desk` |
| 2 | Desk metadata loaders (`getpage`, `get_desktop_page`, Workspace/Report/Page lists) | Gate resolves `getpage`/`get_desktop_page` targets by module; list hides navigation of apps the user cannot reach; doc hook on Report/Page/Workspace | `test_navigation_lists_hide_other_apps_modules`, `test_module_scoped_records_follow_their_module`, `test_desk_loaders_are_gated_by_module` |
| 3 | `/helpdesk` SPA HTML | Gate (page): Helpdesk staff or portal role; guests to login (fixes the `/login/helpdesk` 404); others to no-access | matrix "SPA URL" |
| 4 | `/assets/*` static | **N/A**: public by design, served by nginx, no data | `shared-set.md` |
| 5 | `/api/method/*`, `?cmd=` | Gate: method root -> app; DocType/report args -> app | matrix "API method (ERPNext/Helpdesk)", `test_owned_method_roots`, `test_rpc_style_cmd_...` |
| 6 | `/api/resource/*`, `/api/v2/document\|doctype/*` | Gate (path) + list hook | matrix "API resource", `test_resource_paths` |
| 7 | Reports (`query_report.*`, `reportview.*`) | Gate: `report_name` -> module -> app, `doctype` arg; doc hook on Report | matrix "report", `test_reports_resolve_through_their_module` |
| 8 | Print / PDF (`download_pdf`, `/printview`) | Gate: `doctype` arg on any path; doc hook for `print` | `test_print_and_list_pages_use_the_doctype_gate` |
| 9 | Private file download | doc hook (File inherits the attached document's permission) | matrix "private file" |
| 10 | File upload | Gate: `doctype` argument of `upload_file`; shared otherwise | `test_print_and_list_pages_use_the_doctype_gate` |
| 11 | Realtime (document rooms) | doc hook through `frappe.realtime.has_permission` and the Gate on its `doctype` arg | matrix "realtime room join" |
| 11b | Realtime `task_*` and `all` rooms | **N/A / residual**: no per-app data in these rooms; unscoped publishes reach all System Users (documented in `shared-set.md`) | |
| 12 | Website/portal pages (`/me`, `/portal`, `/list?doctype=`) | list + doc hooks (portal roles preserved for ERPNext customers) | `test_print_and_list_pages_use_the_doctype_gate` |
| 13 | Launcher (`get_apps`) | **N/A in Phase 2**: display only; the resolver (`resolve_landing`, `get_user_apps`) is built, UI is Phase 3 | `test_access_resolver` |
| 14 | `/login`, `/logout` | Exempt from the gate; disabled accounts refused everywhere else | `test_a_disabled_account_reaches_nothing_even_shared_endpoints` |
| 15 | `/api/v2/mcp`, `/api/v2/discovery/*` | Gate: platform administrators only | `test_discovery_surfaces_are_platform_admin_only` |
| 16 | `/backups`, `/.well-known/*` | **N/A**: Frappe-owned, not app surfaces (backup download has its own System Manager check) | |

Beyond the table: customer data minimisation (document-info endpoints refused to portal-only users; `_assign` and
`_comments` stripped from their responses) is covered in `test_customer_leaks`.
