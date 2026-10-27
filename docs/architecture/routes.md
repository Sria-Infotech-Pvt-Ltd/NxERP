# NXERP routes and endpoints

Status: Phase 3. Every route the platform owns or depends on, who may open it, and what happens otherwise.
Companion to [ADR-004](../adr/ADR-004-route-map.md) (the decision) and
[`access-admin.md`](access-admin.md) (how grants are managed). Behaviour below was observed on the running
dev stack and is covered by `nxerp/tests/test_unified_experience.py`, `nxerp/tests/test_routing.py` and the
browser suites in `e2e/`.

**Reading the table.** *Guest* = not signed in. *Staff* = a System User. *Authorised* = holds the app's grant
(`docs/adr/ADR-003-amendment-1.md`). "Friendly page" = `/nxerp/no-access`. No response in this document
contains a stack trace, a list of the apps a user lacks, or the name of a grant role (checked by the tests).

## Pages

| URL | Owner | Authentication | Who may open it | Unauthorised | Invalid or unknown |
| --- | --- | --- | --- | --- | --- |
| `GET /login` | `nxerp` (`www/login.*`) | none | everyone | n/a. A **signed-in** visitor is redirected to `/nxerp/go` (carrying `redirect-to`, which the router re-validates) | `redirect-to` that is not a safe same-origin path is **dropped** (301 to a plain `/login`); a safe one is rewritten to travel through the router (`/login?redirect-to=/nxerp/go?redirect-to=<target>`) |
| `GET /login/<anything>` (e.g. the old `/login/helpdesk`) | `nxerp` (`website_redirects`) | none | everyone | n/a | 301 to `/login` |
| `GET /nxerp/go` | `nxerp` (`www/nxerp/go.*`) | session | everyone; **the post-login router** | Guest: 301 to `/login` | Always answers with a redirect to a same-origin path; a bad `redirect-to` is ignored and the user's landing is used |
| `GET /nxerp/apps` | `nxerp` (`www/nxerp/apps.*`) | session | users with **two or more** apps (the launcher) | Guest: 301 to `/login?redirect-to=/nxerp/go`. A user who does not need a launcher is redirected to where the router would send them (one app: that app; none: the friendly page; customer: the portal) | n/a |
| `GET /nxerp/no-access` | `nxerp` (`www/nxerp/no_access.*`) | none (it is the safe place to send people) | everyone | n/a | n/a. Shows a "Manage user access" link only to platform administrators; nothing else varies by user |
| `GET /nxerp/test-app` | `nxerp`, **test-only** | session | holders of a test-only registered app, and only when the site has `allow_tests` on | Guest: 301 to `/login`; no grant: 301 to the friendly page | **404 on any site without `allow_tests`** (production). Never shipped as an app |
| `/helpdesk`, `/helpdesk/*` | Helpdesk (SPA) behind the `nxerp` gate | session | staff holding the Helpdesk grant (or implied `Agent` / `Agent Manager`); customers (`HD Customer*`) on the portal routes | Guest: 302 to `/login?redirect-to=<path>`. Signed in without the grant: 302 to the friendly page | unknown SPA paths are the SPA's own 404 view |
| `/desk`, `/desk/*` (ERPNext) | Frappe/ERPNext behind the `nxerp` gate | session | staff holding the ERPNext grant; platform administrators keep the Desk shell (never ERPNext data) | Guest: 302 to `/login?redirect-to=<path>`. No grant: 302 to the friendly page. Customers: 403 | Frappe's own 404 |
| `/app`, `/app/*`, `/apps` | Frappe | as `/desk` | as `/desk` | as `/desk` | 301 to `/desk` (Frappe 16 behaviour, unchanged) |
| `GET /logout` | Frappe (not overridden) | session | everyone | n/a | ends the session, then `/login` |
| `/update-password?key=…` | Frappe (not overridden) | one-time key | holder of the emailed key | invalid or used key: Frappe's own message | n/a |
| `/v1/login` | nobody | n/a | n/a | n/a | 404. Frappe has no such route; `/login` is canonical |

## Landing rules (what `/nxerp/go` decides)

`nxerp.routing.route(user, redirect_to)`, in this order:

1. Guest or disabled user: `/login`.
2. `redirect-to` honoured **only if** it passes `routing.safe_target` **and** the user may use the app that owns
   the path (`routing.authorised_target`). Otherwise ignored.
3. Administrator while the setup wizard is unfinished: `/desk`, because only Desk's own router continues into the
   wizard (ADR-004 rule 5).
4. Otherwise `nxerp.access.resolve_landing`:

| User holds | Lands on |
| --- | --- |
| no app | `/nxerp/no-access` |
| exactly one app | that app's route (`/helpdesk/home`, `/desk`) |
| two or more apps | `/nxerp/apps` |
| only a customer or supplier portal role | the portal (`/helpdesk/my-tickets`) |

## Redirect safety

`routing.safe_target` accepts a site-relative **path** and nothing else. It percent-decodes up to three rounds
before judging (so `%252f%252f` cannot hide a `//`), rejects backslashes, control characters, a leading `//`,
any scheme or host, over-long values and non-strings, and normalises `..`. A path is then honoured only if an
installed app owns it and the user may use that app; unknown internal paths (`/me`, `/files/...`) are not
honoured. The query string is carried exactly as received.

ADR-004 rule 1 said to reuse Frappe's `sanitize_redirect`. It was **not** reused as the decision: it accepts
absolute same-host URLs and rewrites foreign hosts to `/desk`, which may itself be a place the user may not go.
`routing.safe_target` is the stricter, path-only validator; Frappe's own client-side sanitiser still runs on the
login page as a second layer. About 35 hostile payloads are tested in `test_routing.py`, and the same set is sent
through the real router in `test_unified_experience.py` and the browser suite.

`localStorage["last_visited"]` is not trusted: for website users the login page clears it and points the
browser at the router (rule 3). **Not covered:** a User Invitation's `redirect_to_path` is Frappe's own flow and
is unchanged (open question, see PROGRESS.md).

## Whitelisted endpoints added or overridden in Phase 3

| Endpoint | Where | Guests | Behaviour | Permission check |
| --- | --- | --- | --- | --- |
| `frappe.apps.get_apps` (override of Frappe's own) | `nxerp.launcher.get_apps` | refused by Frappe (not `allow_guest`): 403 | returns `[{name, title, logo, route, setup_wizard_text}]` for the apps **the caller** may use, with the registry's names (ERPNext, Helpdesk) | the list is built from `nxerp.access.get_user_apps(caller)`; there is no parameter that selects another user |

No other whitelisted method was added. The Phase 2 methods in `nxerp.api.access` are documented in
`access-admin.md`.

Hooks that shape these routes (`nxerp/hooks.py`; the exact set is asserted by `test_scaffold.py`):
`on_session_creation` (points a fresh login at the router), `extend_bootinfo` (Desk's own app switcher shows
only the user's apps, Framework hidden), `override_whitelisted_methods` (above), `website_redirects`
(`/login/<x>` to `/login`) and `standard_navbar_items` (the "All applications" row in Desk's user menu, shown
only when the server set `boot.nxerp.launcher`, i.e. to multi-app users).

## Switch-app links

Helpdesk's Apps menu (`desk/src/composables/useApps.ts`, Helpdesk fork) and Desk's user menu list the user's
other apps plus "All applications" (`/nxerp/apps`) **only when the user holds more than one app**. A single-app
user sees no app switcher at all. This is display only; the gate is the control.

## Login and its special flows

`/login` is Frappe's own login page logic with the NXERP layout on top (`frappe.www.login.get_context` runs
unchanged). The flows below are Frappe's; the platform changes only where the browser goes afterwards.
Status and evidence are in `docs/PROGRESS.md` (Phase 3 test results).

| Flow | Provided by | Notes |
| --- | --- | --- |
| Password sign-in, wrong password, disabled user | Frappe | generic message; a disabled account says "disabled" only after the correct password was given (Frappe behaviour) |
| Forgot / reset password | Frappe | emailed `/update-password?key=...` link, single use |
| Two-factor (OTP by email, app or SMS) | Frappe | OTP step is rendered by Frappe's script inside the NXERP page |
| Lockout and rate limits | Frappe (`allow_login_attempts`, rate-limited endpoints) | unchanged |
| Session expiry and logout | Frappe | after expiry any protected path goes to `/login?redirect-to=<path>`, and sign-in returns there if the user is still authorised |
| Sign-up | Frappe (`disable_signup`) | disabled on the dev and test sites; the API refuses |
| Login with an emailed link | Frappe (System Settings) | not offered on the NXERP page; endpoints stay as Frappe ships them |
| Social / LDAP / SSO | Frappe | not configured here; the NXERP page hides the buttons unless `SHOW_SOCIAL_LOGIN` is switched on (`nxerp/www/login.py`) |
| Kill-switch | `nxerp` | site config `nxerp_stock_login = 1` serves Frappe's stock login (`docs/runbooks/login-recovery.md`) |

Site config is cached by every web worker for up to 60 seconds (`frappe/config.py`), so the kill-switch and any
other `bench set-config` change takes effect within a minute without a restart.

## Accessibility and branding

The login, launcher and no-access pages: one `h1`, a `main` landmark, labelled fields, `lang` set, a skip link on
the launcher and the no-access page, visible focus, text contrast checked in light and dark at 1440 and 390 px
wide, no horizontal scroll (`e2e/pages.test.mjs`). These are automated basics, not a screen-reader audit.
NXERP branding appears on the login, launcher and no-access pages; ERPNext and Helpdesk keep their own names
and tiles. Palette tokens come from `nxerp/public/css/nxerp-theme.css` only.
