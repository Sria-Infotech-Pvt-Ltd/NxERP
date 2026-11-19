# Adding an app to NXERP

Adding an app is **one registry entry plus grants**. No platform code changes, no imports.

## 1. Give the app its own stack (the stack template)

Each app has its own site, database, database login, Redis pair, worker, scheduler, files volume and secrets; no existing app, database, cache or login is
touched (ADR-009; blueprint section 2.8). The one template is `deploy/docker/compose/isolated/stack.compose.yaml`; the steps are the same for every app:

| Step | What you do | Where |
| --- | --- | --- |
| 1 | Name the app and choose its database tier (standard, or restricted for tax, credit, payment or payroll data) | one new line in `deploy/env/isolated/stacks.list`: `<name> <host-prefix> <standard\|restricted>` |
| 2 | Pin the app in `deploy/apps.json` (exact commit, never vendored, ADR-001) before `nxerp`, and build the image | `deploy/apps.json`, `deploy/docker/build.sh` |
| 3 | Copy the generic env template, fill in the site name, `NXERP_STACK_APPS` (the apps to install on that site, in order), the database host and network, fresh passwords | `deploy/env/isolated/app.env.example` to `deploy/env/isolated/<name>.env` (mode 600) |
| 4 | Create the site once and start it | `deploy/scripts/stack.sh <name> create-site`, then `deploy/scripts/stack.sh <name> up` |
| 5 | Regenerate the edge proxy (no hand edits) and reload it | `deploy/scripts/stack.sh edge up` (runs `edge-gen.sh`) |
| 6 | Add the registry entry (section 2 below), register the app on the identity site (an NXERP Peer record) and create its OAuth client (`nxerp.federation.setup` or the Desk screens) | `registry.py`; `docs/architecture-isolation/phase-6-user-actions.md` steps 6.3 to 6.6 |
| 7 | Grant access on the identity site (section 3 below) | the identity site |
| 8 | Run the isolation checks: the new login appears as a new row and column in the matrix | `scripts/isolation_audit.sh cross-read reach published hostnames` |
| 9 | Add the app's backup schedule and monitoring | `deploy/scripts/stack.sh <name> backup` |

Nothing else changes: the three throwaway stand-ins `app3`, `app4`, `app5` in the Phase 5 rehearsal were added exactly this way.

## 2. Add one `AppEntry` to `apps/nxerp_platform/nxerp/registry.py`

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
	# public site (all optional; see docs/design/ui-contract.md for the copy limits):
	display_name="Royal HRMS",          # what the public pages call it (the launcher still shows `title`)
	tagline="...",                      # at most 60 characters
	summary="...",                      # at most 180 characters
	features=("...", "..."),            # at most 4, each at most 6 words
	category="Business apps",           # groups products on /products
	signup_policy="request_access",     # invite_only | request_access | open_portal
	# there is deliberately no colour field
)
```

`after_migrate` creates the `NXERP Access: HRMS` role (idempotent, `desk_access = 0`, so holding it never
turns a website user into a system user). Run `bench --site <site> migrate` once.

## 3. Grant access

Roles are the grants (ADR-003), made on the **identity site** and copied to the app site (ADR-003 amendment 2). In Desk on the identity site: open the
**User** (or a **Role Profile**), tick `NXERP Access: HRMS`. Or use the API: `nxerp.api.access.set_app_access(user, "hrms", 1)` (System Manager only;
on an identity site the answer also says `"provisioning": "queued"`). The app site's own administrator gives the person a business role there.
Revocation is queued at once and delivered within about a minute; the nightly reconcile repairs anything missed.

## 4. Verify

Run the matrix: `bench --site <site> run-tests --app nxerp`. Add the new app's surfaces (a URL, a method, a
resource, a file) as rows in `apps/nxerp_platform/nxerp/tests/test_access_matrix.py`; a user without the grant must be refused
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

- Do not import `nxerp` from your app and do not import other apps (ADR-005; `scripts/check_architecture.py`).
- A DocType belongs to your app through its **module**. Do not put app data in Frappe's own modules: they are the
  shared set (`docs/security/shared-set.md`) and are not app-gated.
- `implied_roles` is for roles your app already uses to mean "staff" (Helpdesk: `Agent`, `Agent Manager`) so the
  app's own invite flows keep working. Assigning an implied role is governed by the app's own rules, not by NXERP's
  grant guard. Leave it empty if in doubt: the explicit access role is always enough.
- `portal_roles` is for an app with a customer-facing surface. Portal users never see staff apps, never open Desk,
  and get extra data minimisation (`nxerp.enforcement`: no document-info endpoints, assignment metadata stripped).

## Placeholders (documented only, nothing is created)

- `apps/hrms/`: an own Frappe app in this repository (add a `path` entry to `deploy/apps.json`), **or** the official
  Frappe HRMS pinned by url and commit in `deploy/apps.json` (it requires ERPNext, so install it after ERPNext).
- `services/<name>/`: a non-Frappe external app (its own container, reached over HTTP), registered the same way.

For either: add one registry entry in `nxerp/registry.py`, add the access grants, reserve a `/<app>` route
(`docs/architecture/routes.md`), write an ADR, and add `CODEOWNERS` entries for its folder.
