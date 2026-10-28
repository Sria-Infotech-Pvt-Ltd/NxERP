# Adding an app to NXERP

Adding an app is **one registry entry plus grants**. No platform code changes, no imports.

## 1. Install the app

Add it to `deploy/apps.json`, pinned to an exact commit (never vendored, ADR-001), after the apps it
depends on and before `nxerp`. Rebuild with `./deploy/dev/up.sh`.

## 2. Add one `AppEntry` to `nxerp/registry.py`

```python
AppEntry(
	key="hrms",                         # stable id used in grants, logs and URLs
	title="HRMS",
	logo="/assets/hrms/images/logo.svg",
	route="/hrms",                      # where staff land
	order=30,                           # launcher order
	app="hrms",                         # entry is active only while this Frappe app is installed
	owns=("hrms",),                     # python packages whose DocTypes, modules and methods belong to it
	access_role="NXERP Access: HRMS",   # the role an administrator assigns
	path_prefixes=("/hrms",),           # URL prefixes only staff of this app may open
	# optional:
	implied_roles=(),                   # existing app roles that also count as staff access (see below)
	portal_roles=(),                    # roles allowed to use the app's customer-facing surface
	portal_prefixes=(), portal_route=None,
)
```

`after_migrate` creates the `NXERP Access: HRMS` role (idempotent, `desk_access = 0`, so holding it never
turns a website user into a system user). Run `bench --site <site> migrate` once.

## 3. Grant access

Roles are the grants (ADR-003). In Desk: open the **User** (or a **Role Profile**), tick
`NXERP Access: HRMS`. Or use the API: `nxerp.api.access.set_app_access(user, "hrms", 1)` (System Manager only).
Revocation is immediate on the next request.

## 4. Verify

Run the matrix: `bench --site <site> run-tests --app nxerp`. Add the new app's surfaces (a URL, a method, a
resource, a file) as rows in `nxerp/tests/test_access_matrix.py`; a user without the grant must be refused
on each.

## What the registry gives you automatically

| Surface | Enforced by |
| --- | --- |
| URLs under `path_prefixes` | `auth_hook`: no grant is redirected to `/nxerp/no-access`; guests to `/login` |
| Whitelisted methods whose first segment is in `owns` | `auth_hook` |
| `/api/resource/<DocType>`, `/api/v2/document|doctype/...` for DocTypes of an owned module | `auth_hook` |
| `doctype`, `dt`, `doc`, `docs`, `report_name` arguments of generic methods (`frappe.client.*`, `reportview`, `search_link`, `getdoctype`, `query_report.*`, `download_pdf`...) | `auth_hook` |
| Files, print, realtime room joins, `doc.check_permission()` on owned documents | wildcard `has_permission` hook |
| `get_list`, report views, website list pages for owned DocTypes; Workspace/Report/Page/Dashboard records of owned modules | wildcard `permission_query_conditions` hook |

Nothing is granted by this layer: Frappe's DocType, field and record permissions still apply on top.

## Rules for an app author

- Do not import `nxerp` from your app and do not import other apps (ADR-005; `tools/check_architecture.py`).
- A DocType belongs to your app through its **module**. Do not put app data in Frappe's own modules: they are the
  shared set (`docs/security/shared-set.md`) and are not app-gated.
- `implied_roles` is for roles your app already uses to mean "staff" (Helpdesk: `Agent`, `Agent Manager`) so the
  app's own invite flows keep working. Assigning an implied role is governed by the app's own rules, not by NXERP's
  grant guard. Leave it empty if in doubt: the explicit access role is always enough.
- `portal_roles` is for an app with a customer-facing surface. Portal users never see staff apps, never open Desk,
  and get extra data minimisation (`nxerp.enforcement`: no document-info endpoints, assignment metadata stripped).
