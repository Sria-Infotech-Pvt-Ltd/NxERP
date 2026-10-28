# Architecture rules

Enforced by `scripts/check_architecture.py` (CI job "Architecture rules", pre-commit, and the unit tests in
`apps/nxerp_platform/nxerp/tests/test_architecture.py`). The checker finds every other app under `apps/` itself, so a
new app is checked as soon as its folder exists.

1. **Apps never import from each other.** Only `nxerp_platform` knows about the apps, through its registry
   (`nxerp/registry.py`). Facts cross apps by hooks, roles and permissions, and HTTP APIs, never by Python imports.
2. **Platform code lives only in `apps/nxerp_platform/`. App code lives only in its own app.** Login, launcher, access
   rules and platform branding are platform code; the checker fails if another app carries a copy of them.
3. **Helpdesk customisations stay minimal and isolated** and are listed in `docs/upstream.md`.
4. **Platform package layout.** Today the platform is flat modules (`access`, `enforcement`, `guard`, `routing`,
   `launcher`, `registry`, `audit`, `install`, `migration`) plus `api/`, `patches/`, `www/`, `public/`, `tests/`.
   Splitting them into `access/ login/ launcher/ branding/` packages changes dotted paths in `hooks.py` and is a
   follow-up that must be proven by tests (see `docs/PROGRESS.md`). `api/` holds thin whitelisted endpoints only.
5. **Import-boundary test in CI.** `scripts/check_architecture.py` fails (exit 1) on any violation: R1 platform imports
   another app, R2 `required_apps` or app dependencies, R3 another app imports `nxerp`, R4 platform code outside the
   platform app. Negative tests prove each rule catches its violation.
6. **Names.** Python packages and Frappe app names are snake_case; other folders and docs are lowercase-with-hyphens.
   Never rename the Python packages `nxerp` and `helpdesk`, `hooks.py`, `modules.txt`, `patches.txt`, `www/`, `public/`,
   `.github/`, tool configs or the `frappe-ui` submodule.
7. **Fixed names inside Helpdesk:** `realtime/` must keep its name (Frappe loads `<app>/realtime/handlers.js` by path);
   the build output `helpdesk/public/desk` and the `/assets/helpdesk/desk/...` URLs stay.
