# How to add an app to NXERP

A checklist for whoever adds the next application (for example HRMS, Project Management or Budget Management).
None of those is installed or registered today and none is shown anywhere; this guide never assumes one exists.
`<app>` below is a placeholder for the Frappe app you are adding.

**Adding an app is one pin, one registry entry and role grants.** No platform code changes, no imports in either direction (ADR-005).
The short reference is [`../architecture/adding-an-app.md`](../architecture/adding-an-app.md); this guide is the full checklist, and
**its promises are checked by a test**: `apps/nxerp_platform/nxerp/tests/test_add_app_checklist.py` registers a clearly marked dummy app in process and asserts
each promise below against the real registry, resolver, gate, launcher and router code. If a promise stops being true, that test fails and this guide must change.

## 0. Before you start

- [ ] You are not importing `nxerp` from `<app>`, and `<app>` is not imported by `nxerp` or by another app. The platform resolves apps through the registry and Frappe's own channels (hooks, roles, HTTP/whitelisted APIs).
- [ ] If the app changes an architecture rule (a new kind of surface, a second login, a different landing), write or amend an ADR first ([`../adr/README.md`](../adr/README.md)).
- [ ] Ownership: a `CODEOWNERS` entry for the app's folder in this repo, if it gets any (normally it has none: it lives in its own repo).

## 1. Install it, pinned

- [ ] Add it to `deploy/apps.json` at an **exact 40-character commit** (`name`, `url`, `branch`, `commit`), after the apps it needs and **before `nxerp`**, which must stay last (its `/login` only wins as the last installed app).
- [ ] Update [ADR-002](../adr/ADR-002-version-matrix.md) (the version matrix) in the same pull request.
- [ ] `python3 -I deploy/check_pins.py` passes. Never vendor or copy the app into this repo.
- [ ] Rebuild the dev stack and install it on the site (`./deploy/dev/up.sh -d`; see [`../onboarding/day-1.md`](../onboarding/day-1.md)).

The registry entry is **active only while its Frappe app is installed** on the site (`AppEntry.app`). Declared but not installed means invisible everywhere.

## 2. Add one `AppEntry` to `apps/nxerp_platform/nxerp/registry.py`

Add it to the `APPS` tuple. Strings only; never import the app.

```python
AppEntry(
	key="<app_key>",                        # stable id used in grants, logs and URLs; no spaces
	title="<Title>",                        # what business users see
	logo="/assets/<app>/images/<logo>.svg", # served by the app, not copied here
	route="/<app-route>",                   # where staff land; must sit under one of path_prefixes
	order=30,                               # launcher order, ascending (ERPNext 10, Helpdesk 20)
	app="<app>",                            # the Frappe app that must be installed for the entry to be active
	owns=("<app>",),                        # python packages whose DocTypes, modules and whitelisted methods belong to it
	access_role="NXERP Access: <Title>",    # the role an administrator assigns
	path_prefixes=("/<app-route>",),        # URL prefixes only staff of this app may open
	# optional, see sections 4 and 5:
	implied_roles=(),
	portal_roles=(), portal_prefixes=(), portal_route=None,
)
```

| Field | What it controls | How to choose it |
| --- | --- | --- |
| `key` | Identity in grants (`set_app_access`), logs, the launcher tile and tests | Short, lowercase, stable. Never reused |
| `title`, `logo` | The tile and every "Apps" menu | The app's own name. The platform never renames an app |
| `route` | Where a user with **only** this app lands | The app's real home page. Must be under `path_prefixes`, or the gate would not cover the landing page |
| `order` | Position in the launcher | Next free number |
| `app` | "Installed" check | The Frappe app name exactly as `bench list-apps` prints it |
| `owns` | Which DocTypes and whitelisted methods are the app's: a method belongs to it when the first segment of its dotted path is in `owns`; a DocType when its **module's app** is in `owns` | The python package(s) the app ships. Put app data in the app's own modules, never in a custom module (custom and Frappe-core modules are the unprotected [shared set](../security/shared-set.md)) |
| `access_role` | The grant | `NXERP Access: <Title>`. Created for you (section 3). Unique |
| `path_prefixes` | Page URLs the gate protects (whole path segments only: `/<app-route>` covers `/<app-route>/x` but not `/<app-route>x`) | The app's route prefix(es). Must not overlap another app's |
| `admin_shell` | Lets platform administrators open the prefixes to administer | Leave `False`. Only ERPNext (the Desk shell) sets it |

`apps/nxerp_platform/nxerp/tests/test_add_app_checklist.py` holds these shape rules as code (`checklist_problems`): a key without spaces, a role named `NXERP Access: ...`, a route under a prefix,
non-empty `owns`, no clash with another app's key, role, packages or prefixes, portal fields complete. Run it on your entry.

## 3. Roles: created by migrate, not by hand

- [ ] Run `bench --site <site> migrate` once. `nxerp.install.after_migrate` calls `ensure_access_roles()`, which creates `NXERP Access: <Title>` for every **installed** entry: idempotent, `desk_access = 0` (holding it never turns a website user into a system user), `is_custom = 1`. The patch `nxerp.patches.create_access_roles` does the same.
- [ ] An entry whose app is not installed gets **no** role.
- [ ] The platform creates only the access role. Roles the app itself defines (`implied_roles`, `portal_roles`) are the app's business and must already exist.

## 4. Grants and implied roles

- [ ] Grants are Frappe roles (ADR-003). In Desk: open the **User** (or a **Role Profile**), tick `NXERP Access: <Title>`, Save. Or call `nxerp.api.access.set_app_access(user, "<app_key>", 1)` (System Manager only; `0` revokes). Revocation applies on the next request, no re-login.
- [ ] Only a System Manager may change an `NXERP Access:` role; the last named System Manager cannot be removed or disabled ([`../architecture/access-admin.md`](../architecture/access-admin.md)).
- [ ] `Administrator` holds every **installed** app and never an uninstalled one.
- [ ] A website user (customer) never holds staff access, whatever roles they carry.
- [ ] `implied_roles`: only for roles the app already uses to mean "staff" so its own invite flows keep working (Helpdesk: `Agent`, `Agent Manager`). A user with an implied role has staff access; revoking through the API removes the implied roles too. Assigning an implied role is governed by the app's own rules, not by the NXERP grant guard. **Leave it empty if in doubt**: the explicit access role is always enough, and a role such as `Sales User` must never imply an app.

## 5. Portal (customer-facing) surface, only if the app has one

- [ ] `portal_roles` (the customer roles), `portal_prefixes` (which URLs they may open, under `path_prefixes`) and `portal_route` (where a portal-only user lands). All three together.
- [ ] Portal use is **not** staff access: it never appears in the launcher, never opens Desk, and portal-only users get extra data minimisation (no document-info endpoints on owned DocTypes; `_assign` and `_comments` removed from API responses).
- [ ] Frappe's DocType and record permissions still decide what a portal user can read; the registry only decides whether they may reach the app at all.

## 6. What you get automatically

| Surface | Result for a user without the grant |
| --- | --- |
| A page under `path_prefixes` | Guest: 302 to `/login?redirect-to=...`. Signed in: 302 to `/nxerp/no-access` |
| A whitelisted method whose root is in `owns` | 403 JSON "You do not have access to this application" |
| `/api/resource/<DocType>` and friends for DocTypes of the app's modules, and `doctype` / `report_name` arguments of generic methods | same |
| Files, print, realtime document rooms, `doc.check_permission()`, `get_list`, reports | refused by the wildcard document and list hooks |
| The launcher, `frappe.apps.get_apps`, Desk's app switcher | the app is not listed |
| Landing | see below |

Nothing is granted by this layer: Frappe's DocType, field and record permissions still apply on top.

Landing rules (`routing.route` and `access.resolve_landing`), unchanged by adding an app:

| User holds | Lands on |
| --- | --- |
| no app | `/nxerp/no-access` |
| exactly the new app | its `route` |
| two or more apps | `/nxerp/apps` (the launcher lists them in `order`) |
| only a portal role of the app | its `portal_route` |

A `redirect-to` into the app is honoured after sign-in only for someone who may use it; anyone else gets their own landing.

## 7. Hooks

- [ ] **Do not edit `apps/nxerp_platform/nxerp/hooks.py`** to add an app. The set of platform hooks is pinned by `test_scaffold.py`, and the registry is the one extension point.
- [ ] The app keeps its own `hooks.py` (title, `add_to_apps_screen`, its own `required_apps` if it needs ERPNext). Frappe builds a tile from it, and the platform then corrects every "Apps" menu from the registry: the registry's title and logo win and unregistered apps are hidden. **`nxerp` itself still declares no `required_apps`.**
- [ ] A new top-level URL the app serves must be covered by `path_prefixes`; a new whitelisted API by `owns`.

## 8. Tests

- [ ] `bench --site nxerp.localhost run-tests --app nxerp --module nxerp.tests.test_add_app_checklist` stays green (it uses a dummy entry, so it does not depend on your app).
- [ ] Add the app's real surfaces as rows to `apps/nxerp_platform/nxerp/tests/test_access_matrix.py` (a URL, a method, a resource, a file): a user without the grant must be refused on each, by URL and by API, and the guest case too.
- [ ] Extend `apps/nxerp_platform/nxerp/tests/test_registry.py` for ownership (`entry_for_doctype` of one of the app's DocTypes returns your entry; Frappe core DocTypes still return none).
- [ ] `python3 -I tools/check_architecture.py --app-path <app>=<path-to-the-app-checkout>` passes: no import of `nxerp` from the app, no platform code inside it.
- [ ] Add a persona (a user holding only the new app) to the HTTP and, if the app has a UI, browser tests ([`testing.md`](testing.md)).

What the exercised test proves, and where each is asserted in `test_add_app_checklist.py`:

| Promise | Test |
| --- | --- |
| The entry is well formed and clashes with no existing app; the shape rules catch the usual mistakes | `test_the_dummy_entry_follows_the_shape_rules...`, `test_the_shape_rules_reject_the_mistakes...` |
| Lookups find the app by package and by path (whole segments only) | `test_the_registry_lookups_find_the_new_app`, `test_installed_entries_keep_launcher_order...` |
| Migrate creates the role once, with `desk_access = 0`; a newly declared app gets its role | `test_ensure_access_roles_creates_the_role_once...`, `test_a_newly_declared_app_gets_its_role_on_the_next_sync` |
| An app that is not installed has no role, no visibility, no claimed paths | `test_an_app_that_is_not_installed_gets_no_role_and_no_visibility`, `test_an_uninstalled_app_is_never_listed...` |
| Holders, implied-role holders and Administrator get the app; everyone else, website users, disabled accounts and guests do not | `test_the_resolver_grants...`, `test_an_implied_role_counts...`, `test_a_website_user_never_holds...` |
| Portal roles are not staff access | `test_a_portal_role_is_not_staff_access` |
| Grant and revoke through the API; revoking strips implied roles; only a platform administrator may; an uninstalled app is refused; revocation needs no re-login | `test_granting_through_the_api...`, `test_only_a_platform_administrator...`, `test_the_grant_api_refuses...`, `test_revocation_is_effective...` |
| The gate admits holders to pages and methods of the app and refuses others; portal prefix only for portal roles; shared methods stay shared | `test_the_gate_*`, `test_the_portal_prefix...`, `test_methods_outside_owns_stay_shared` |
| `get_apps`, boot info list the app only for holders, with the registry identity | `test_get_apps_lists...`, `test_the_tile_carries...`, `test_the_boot_info...` |
| Landing: one app goes straight in, two get the launcher in order, none get no-access, portal gets the portal route; a `redirect-to` is honoured only for those who may use it | `test_a_user_with_only_the_new_app...`, `test_a_user_with_two_apps...`, `test_a_user_with_no_app...`, `test_a_portal_user...`, `test_the_router_honours...` |
| People who do not hold the new app are unaffected, and the dummy exists only while the test runs | `test_a_real_app_user_is_unaffected...`, `test_the_dummy_is_only_registered_while_this_class_runs` |

**Not proven by that test** (it is in process and uses a dummy): DocType ownership through a real app's module (`Module Def.app_name`), HTTP behaviour through the real web server (site config is cached by workers for up to 60 s, see [`testing.md`](testing.md)), the app's own data permissions, and any browser behaviour. Those need the app's own rows in the matrix and the browser suites.

## 9. Documentation

- [ ] [`../architecture/access-admin.md`](../architecture/access-admin.md): add the app to the grant table.
- [ ] [`../architecture/routes.md`](../architecture/routes.md): add its pages to the table; [`../architecture/overview.md`](../architecture/overview.md): add it to the diagram and the version matrix.
- [ ] [`../security/shared-set.md`](../security/shared-set.md) if it brings new shared-looking DocTypes; the access matrix if it adds surfaces.
- [ ] [`../PROGRESS.md`](../PROGRESS.md) and, if a rule changed, an ADR row in [`../adr/README.md`](../adr/README.md).
- [ ] Remove "not installed" statements about the app from `README.md` and `CLAUDE.md` only when it really is installed and tested.

## 10. Definition of done

The app is installed from a pinned commit; its entry is in the registry; migrate created its role; a user holding only it lands in it; a user with two apps sees the launcher; a user without the grant is refused on its URLs, its API, its DocTypes, files and lists; guests go to `/login`; the architecture check passes in both directions; the matrix and persona tests pass; docs and ADR are updated; and you have listed what you did **not** verify.
