# The shared set

The app gate (`nxerp.enforcement`) applies only to things **owned by a registered NXERP app**. Everything else
is the *shared set* and stays governed only by Frappe's own permissions (DocType, field, record, User
Permission). The gate never reads, blocks or alters it.

## How ownership is decided

| Kind | Owned by an app when | Otherwise |
| --- | --- | --- |
| DocType | its **module's app** (`Module Def.app_name`) is in an entry's `owns` | shared |
| Whitelisted method | the first segment of its dotted path (the python package) is in an entry's `owns` | shared |
| URL | it starts with an entry's `path_prefixes` | shared |
| Report, Page, Workspace, Dashboard, Dashboard Chart, Number Card record | its `module` belongs to an owned app | shared |

## What is shared today (verified against the installed Frappe 16.53 / ERPNext 16.52 / Helpdesk)

DocTypes whose module belongs to the `frappe` app, for example: `User`, `Role`, `Has Role`, `File`, `Comment`,
`ToDo`, `Notification Log`, `Communication`, `Contact`, `Address`, `DocShare`, `User Permission`, `Version`,
`Email Account`, `Tag`, `Activity Log`; DocTypes of a **custom** module (no app); DocTypes of any app not in the
registry; methods under `frappe.*` (login, sessions, search, `frappe.client.*`, desk loaders, realtime...).
`frappe.client.*`, `reportview`, `search_link`, `getdoctype`, `download_pdf` and similar are shared **methods**, but
the DocType they are asked to act on is still resolved and gated if it is owned.

Test evidence: `test_registry.test_shared_core_doctypes_belong_to_no_app`,
`test_enforcement_unit.test_shared_doctypes_and_methods_are_never_gated_by_app` (five personas x eight DocTypes
and three methods), and the matrix row "shared DocType (get_count ToDo)".

## What this means

- A Helpdesk-only user can still use `User`, `File`, `ToDo`, `Comment`, notifications and search, as Helpdesk needs.
- Shared DocTypes can still *reference* app records (a `ToDo` assigned on a Customer, a `File` attached to a Sales
  Invoice). Access to the referenced record is decided by the referenced DocType's owner: the `File` check inherits
  the attached document's permission, which reaches the wildcard `has_permission` hook.
- A DocType in a custom module is not app-gated. Do not put app data in custom modules.
- ERPNext's website-user model (roles `Customer`, `Supplier`) is preserved: those roles are the ERPNext entry's
  `portal_roles`, so portal pages that read ERPNext records as the website user keep working.

## Residual, deliberately not covered

- Static `/assets/*` and public `/files/*` served by nginx: public by design.
- `allow_guest` methods (Frappe decides; guests are never gated by NXERP).
- Realtime rooms that are not document rooms (`task_*`, the `all` room): no per-app data; an unscoped
  `publish_realtime` reaches every System User regardless of app. Documented, not changed.
- `/backups`, `/.well-known/*`: Frappe-owned, not app surfaces.
