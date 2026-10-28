# ADR-004 amendment 1: what Phase 3 learned, and every upstream file it touched

- **Status:** Accepted (Phase 3)
- **Date:** 2026-10-27
- **Amends:** ADR-004 (route map), ADR-005 (upstream files stay untouched unless justified here)

## Decisions that differ from the text of ADR-004

1. **`routing.safe_target` is the redirect validator, not Frappe's `sanitize_redirect` (rule 1).**
   Frappe's function accepts absolute same-host URLs, returns an absolute URL, and rewrites a foreign host to
   `/desk`, which can itself be a place the user may not go. The router needs a path-only answer. The validator is
   stricter (multi-round percent-decoding, no backslashes, control characters, `//`, schemes, over-long input) and
   is tested with about 35 hostile payloads in process and again through the real router and a real browser.
   Frappe's client-side sanitiser still runs on the login page as a second layer.
2. **The login page points *every* sign-in at the router, in the page, not only in the server hook.**
   `on_session_creation` sets `home_page` for system users, but Frappe answers a Website User (a customer) from a
   different engine (`get_default_path()`, which calls its own, un-overridden `get_apps`). A small script on the
   NXERP login page re-points that answer at `/nxerp/go` and clears the browser's stale `last_visited`
   (ADR-004 rule 3). The server gate remains the control; the script only keeps the landing consistent.
3. **The "All applications" row in Desk's user menu is a standard navbar item with a condition, not a boot hook.**
   Frappe assigns `boot.navbar_settings` *after* the `extend_bootinfo` hooks run, so a hook cannot add a row per
   user. A standard item (`standard_navbar_items`, synced on migrate) carries the condition
   `frappe.boot.nxerp && frappe.boot.nxerp.launcher`, which Desk evaluates in the browser each time the menu
   opens; `boot.nxerp.launcher` is set only for multi-app users.
4. **A kill-switch exists (`nxerp_stock_login`)** that serves Frappe's stock login. It changes only the page;
   authentication, the router and the gate are unchanged. Runbook: `docs/runbooks/login-recovery.md`.
5. **A test-only third app.** No third app ships, so Case 3 is exercised through site config `nxerp_test_apps`,
   honoured only when the site has `allow_tests` on, every entry flagged `test_only`, with a stand-in page at
   `/nxerp/test-app` that answers 404 on any other site.
6. **Site config is cached per web worker for up to 60 seconds** (`frappe/config.py`, `ttl=60`). The kill-switch and
   test-only entries therefore take effect within a minute without a restart. Documented in the runbook; tests
   poll for it instead of sleeping.

## Defects this phase found in Phase 2 code, now fixed

- `no-access.py` (Phase 2) was **never executed**: Frappe resolves the controller of a hyphenated page as
  `no_access.py`. The page rendered from its template only (a guest saw "Back to my applications"). Renamed. Same
  rule applied to the test-only page (`test_app.py`), whose guard had never run either; it was publicly reachable
  as a static page until the rename. Rule for the codebase: **a page named `a-b` needs a controller `a_b.py`**.

## Upstream files touched (ADR-005 justification)

All in the Helpdesk fork, branch `feature/nxerp-platform-login`. Nothing in Frappe or ERPNext was edited.

| File | Change | Why it cannot live in `nxerp` |
| --- | --- | --- |
| `helpdesk/www/login.html`, `login.py`, and the login-only assets | **deleted** (moved to `apps/nxerp_platform/nxerp/www/login.*` and `apps/nxerp_platform/nxerp/public/nxerp_login/`) | Frappe's template resolver picks the *last installed* app's `/login`; two apps cannot both own it. Helpdesk must stop owning it |
| `helpdesk/hooks.py` | app title and apps-screen tile title are "Helpdesk" (were "NXERP"); logo, favicon and splash hooks removed | The title is Helpdesk's own identity; the platform hooks now come from `nxerp`, so Helpdesk pages no longer reference platform assets |
| `desk/src/composables/useApps.ts`, `Sidebar.vue`, `MobileSidebar.vue` | the Apps menu reads Frappe's app list (which `nxerp` overrides), lists other apps plus "All applications", and appears only for multi-app users | This is the Helpdesk SPA's own menu; it cannot be changed from outside the SPA |
| `desk/src/theme/build/sync.mjs`, `check-tracked.mjs`, README, `tokens/audit-allow.json` | the login stylesheet targets removed | They referenced files that no longer exist there |

Kept in Helpdesk on purpose: the NXERP mark and wordmark images used by the SPA's own logo and by
`helpdesk/nxerp_branding.py`. They are the SPA's assets, not the login's.

## Still open

- A User Invitation's `redirect_to_path` is Frappe's own flow and is not validated by the platform.
- Frappe computes `boot.apps_data` (used for its own default path) from the un-overridden app list after the
  hooks run. It lists only apps the user may use by Frappe's rules, so nothing leaks, but names and logos there
  are Frappe's; the visible switcher and menus use the corrected data.
- "Keep me signed in" on the login page is a stored preference only; it does not lengthen the session.
