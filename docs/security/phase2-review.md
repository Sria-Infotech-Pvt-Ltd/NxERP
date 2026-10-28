# Phase 2 security review

Scope: the access layer in `nxerp` (registry, resolver, gate, document and list hooks, response sanitiser, grant
API and guard). Method: threat-by-threat review, each item either **mitigated with a test** or **accepted with a
reason**. Evidence is the test suite (`bench --site <site> run-tests --app nxerp`: 115 tests) and a static scan.

## Static scan

| Tool | Command | Result |
| --- | --- | --- |
| bandit 1.9.4 (application code) | `bandit -r nxerp -x apps/nxerp_platform/nxerp/tests` | 0 high, 0 medium. 1 low (B110, `try/except/pass` in the denial logger) **accepted**: a logging failure must never turn a denial into an error; marked `# nosec B110` with the reason |
| bandit (tests) | `bandit -r apps/nxerp_platform/nxerp/tests -s B101,B105,B106,B311` | clean; skipped IDs are asserts, generated fake passwords and `secrets`-based fixtures |
| ruff check / format | `ruff check .`, `ruff format --check .` | clean |
| architecture rules | `tools/check_architecture.py` | nxerp imports no other app, declares no `required_apps` |

## Checklist

### Privilege escalation

| Threat | Mitigation | Test |
| --- | --- | --- |
| A user grants themselves an app by editing their own User record | `nxerp.guard.validate_user`: changing an `NXERP Access:` role needs a platform administrator, whatever Frappe's form permissions allow | `test_self_grant_through_a_user_record_is_blocked` |
| A non-admin grants or revokes for someone else (API or record) | same guard; the API also checks | `test_a_normal_user_cannot_grant_through_the_api`, `test_a_non_admin_cannot_revoke_a_grant_either` |
| A customer (Website User) becomes staff through a stray grant | `get_user_apps` returns nothing for non-System Users; access roles have `desk_access = 0` so they never change user type | `test_a_website_user_never_holds_staff_access_even_if_granted`, `test_granting_an_access_role_never_changes_user_type` |
| Removing the last administrator | guard blocks role removal, disabling and deletion of the last named System Manager; Administrator cannot be disabled | `test_the_last_named_system_manager_*`, `test_administrator_cannot_be_disabled` |
| **Accepted:** assigning an *implied* role (`Agent`, `Agent Manager`) grants Helpdesk | ADR-003 amendment A2. Those roles are governed by Helpdesk's own rules (an Agent Manager may invite agents by design). The explicit access role is the guarded path | documented |
| **Accepted:** a System Manager can grant themselves any app | System Manager is the platform administrator by definition; every change is in the Version log | `test_grants_and_revocations_are_in_frappes_version_log` |

### IDOR and mass assignment on the grant model

- `set_app_access(user, app_key, grant)` and `get_user_access(user)` take an arbitrary user name but are System
  Manager only, so the object reference is authorised by role, not by ownership. `get_my_access` returns only the caller's
  own data and takes no user argument.
- The API accepts exactly three parameters. Extra parameters (`roles`, `user_type`) raise; Frappe type-checks the
  rest (`test_the_api_accepts_nothing_but_user_app_and_grant`, `test_bad_arguments_are_rejected_cleanly`: unknown
  user, `Administrator`, `Guest`, unknown app, `None`, lists).
- There is no new DocType, so there is no grant document to mass-assign. Grants are role rows on `User`, protected by the guard.

### Cache poisoning and stale grants

- The resolver keeps no cache (`test_the_resolver_has_no_cache_of_its_own`). It derives answers from `frappe.get_roles`,
  which Frappe clears on every User save, and `frappe.get_cached_value("User"|"DocType"|"Report", ...)`, which Frappe
  invalidates on save. Nothing the gate caches can be written by a request.
- Revocation applies on the next request to a live session (`test_revocation_applies_to_a_live_session_without_relogin`,
  `test_a_system_manager_can_grant_and_revoke`, ERPNext smoke test). **Residual:** if roles are changed by raw SQL the
  delay is Frappe's role-cache lifetime until `frappe.clear_cache(user=...)`; use the API or Desk.

### Missing enforcement paths (found and closed during this phase)

| Finding | Fix | Test |
| --- | --- | --- |
| DocType schema (`getdoctype`, `/api/v2/doctype/.../meta`) answered any logged-in user | gated by the owning app | matrix "metadata" |
| Helpdesk agents and customers could open `/desk` | page gate | matrix "desk URL" |
| `/helpdesk` was served to guests and to ERP-only users | page gate (guests to login, others to no-access) | matrix "SPA URL" |
| A disabled account's old session still answered shared endpoints (Frappe checks `enabled` only at session start) | gate refuses every non-exempt request from a disabled account | `test_a_disabled_account_reaches_nothing_even_shared_endpoints`, matrix `disabled` column |
| Customers received the assigned agent's email from Helpdesk's *own* ticket list (`_assign`) and via `getdoc` | document-info endpoints refused to portal-only users; `_assign` and `_comments` stripped from their JSON responses (fails closed) | `test_the_portals_own_ticket_list_does_not_carry_the_assignee`, `test_document_info_endpoints_are_refused_to_portal_users`, `test_after_request_*` |
| `on_trash` ordering made the last-administrator guard blind (Frappe sets `enabled = 0` in memory first) | guard reads persisted state | `test_the_last_named_system_manager_cannot_be_disabled_or_deleted` |
| Desk loaders taking a Page/Workspace name, `/printview`, `/list?doctype=`, `upload_file` | resolved through module or `doctype` argument | `test_desk_loaders_are_gated_by_module`, `test_print_and_list_pages_use_the_doctype_gate`, matrix website test |

Every surface of the Phase 1 coverage table is covered or documented N/A in `docs/security/phase2-coverage.md`.

### Open redirect and information disclosure

- The gate only ever redirects to fixed internal paths (`/nxerp/no-access?app=<key>`, `/login`) and to
  `/login?redirect-to=<the user's own requested path, percent-encoded>`; a request can never choose a redirect target.
- Denials are generic (`You do not have access to this application`). The no-access page names no application and shows no data
  (`test_denial_page_is_plain_and_reachable`). The `app=` query key reveals which app key was refused: accepted, it is not a secret.
- Log lines contain a salted hash (`user_ref`), the app key, the surface and the DocType only; never an email, record name, query
  string or body (`test_denial_is_logged_without_personal_data`).

### Fail-closed and availability

- A resolver or classifier error denies a non-Administrator with a clean response and logs; `Administrator` is never evaluated
  (`test_resolver_error_*`). The document and list hooks also fail closed. The sanitiser fails closed for portal users.
- **Operational note:** a persistent resolver bug therefore denies every non-Administrator until fixed; the runbook is
  to log in as Administrator, read `logs/<site>/nxerp.access.log`, roll back the pin. By design.

### Upgrade fragility (what to re-test when Frappe, ERPNext or Helpdesk change)

The layer uses only documented extension points, and modifies **no upstream file**
(`git -C helpdesk status` is clean; this phase changed only `nxerp-platform`). It does depend on these behaviours; the
persona x surface matrix fails loudly if any changes:

| Dependency | Where used | Check on upgrade |
| --- | --- | --- |
| `auth_hooks` runs after session resolution and before dispatch; an `HTTPException` carrying a response is returned as-is | `auth_hook` | matrix |
| wildcard `has_permission` and `permission_query_conditions` honoured | document and list hooks | `test_a_document_check_goes_through_the_hook`, `test_a_real_list_query_honours_the_condition` |
| `after_request` receives a mutable response | sanitiser | `test_after_request_*`, customer-leak test |
| DocType -> `module` -> `Module Def.app_name` | `registry.entry_for_doctype` | `test_lookup_by_doctype_module_package_and_path` |
| method names `frappe.desk.form.load.getdoc/get_docinfo`, `frappe.desk.desk_page.getpage`, `frappe.desk.desktop.get_desktop_page` | `PORTAL_DENIED_METHODS`, `NAV_METHODS` | matrix, unit tests (a renamed method silently stops being gated: review the changelog) |
| Helpdesk customer endpoints (`get_list_data`) | customer-leak tests | `test_the_portals_own_ticket_list_does_not_carry_the_assignee` |
| `User.save(ignore_version=False)`; `User.on_trash` ordering | grant API, guard | audit and guard tests |

### Accepted residual risks

1. `allow_guest` methods (ERPNext has 8, Helpdesk `get_config`) remain public: Frappe's decision, not NXERP's.
2. Public `/files/*` and `/assets/*` are served by nginx without Python.
3. Unscoped `publish_realtime` reaches every System User regardless of app.
4. A customer still sees the sender of replies sent to them (inherent to a support conversation); NXERP removes assignment and comment metadata, not message authorship.
5. A Helpdesk-only agent can no longer read ERPNext `Customer` records through Helpdesk's optional ERPNext integration
   (mirrored User Permissions and DocShares are overridden by the app gate). This is the intended Case 2 behaviour; the
   integration policy is a product decision (see PROGRESS).
6. Tests commit fake users and records to the dev database and lift `throttle_user_limit` in-process; use a disposable site.
