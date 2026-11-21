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


## Sharing data with another app: the contract steps (Phase 7)

An app never reads or writes another app's DocTypes. When an app needs data another app owns, or must change it, the owner publishes a contract and the
caller goes through the Read API and the command API. The steps, for an owner adding an entity or a command and for a new consumer:

| Step | What you do | Where |
| --- | --- | --- |
| 1 | Write or extend the ownership contract: owner app, source DocType, the allow-listed fields with their sensitivity class (S3 data is never shared), the events, which apps may read which fields (`consumers`) | `apps/nxerp_platform/nxerp/shared/contracts/<entity>.json` |
| 2 | For a change by another app, add a command: its writable fields (shared fields only, never the id), the role the acting user needs, and the `callers` (registered apps) | the same file, `commands` |
| 3 | Bump `contract_version` and run the lint | `python scripts/check_contracts.py` |
| 4 | Create the consuming app's Read API token (`deploy/scripts/shared.sh tokens create --app <app>`) and, for commands, a service user with the role `NXERP Command Caller`, mapped to the app in the owner's site config `nxerp_command_callers` | owner site |
| 5 | In the consuming app: read through a small client (timeouts, a short cache, a stale flag, never raise into a page) and change through a command client (one idempotency key per user action, reused by retries); both behind a site setting that is off by default | e.g. `apps/helpdesk/helpdesk/integrations/shared/` |
| 6 | Add the consumer-contract tests (they run from the contracts) and run the boundary check | `shared_service/tests/test_consumer_contracts.py`, `python scripts/check_architecture.py` |

`scripts/check_architecture.py` rule R5 fails if the new app's code touches a DocType another app owns; the only exemptions are exact file paths in `LEGACY_ALLOW`.

## Moving an existing app's data into its own stack (Phase 8)

A new app starts empty in its own stack (section 1). An app that already lives in the old single site moves with the cutover tools instead:

1. Create the stack (section 1) and its site; leave it stopped until the window.
2. Take a verified backup of the old site (`deploy/scripts/cutover.sh backup-source`), restore it into the new site (`cutover.sh clone-hd` does this for Helpdesk; copy it for another app and change the list of apps to uninstall).
3. Remove what does not belong: `bench uninstall-app` for the other apps, then `nxerp.cutover.prune_helpdesk_site` (the allow-list is read from Module Def, so it follows the app's modules).
4. Copy the identity data with `cutover.sh build-id`, prove equality with `cutover.sh reconcile`, rehearse the way back (`delta-export`, `delta-import`) twice before the window.
5. Re-point the shared layer's source for that app and rebuild it (`deploy/scripts/shared.sh repoint`, `rebuild-and-verify`).

Full steps, gates and the undo of each: [`../runbooks/isolation-cutover.md`](../runbooks/isolation-cutover.md).
