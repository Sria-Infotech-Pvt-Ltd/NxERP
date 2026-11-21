# NXDESK routes and endpoints (platform app `nxerp`)

Status: Phase 3. Every route the platform owns or depends on, who may open it, and what happens otherwise.
Companion to [ADR-004](../adr/ADR-004-route-map.md) (the decision) and
[`access-admin.md`](access-admin.md) (how grants are managed). Behaviour below was observed on the running
dev stack and is covered by `apps/nxerp_platform/nxerp/tests/test_unified_experience.py`, `apps/nxerp_platform/nxerp/tests/test_routing.py` and the
browser suites in `apps/nxerp_platform/browser-tests/`.

**Reading the table.** *Guest* = not signed in. *Staff* = a System User. *Authorised* = holds the app's grant
(`docs/adr/ADR-003-amendment-1.md`). "Friendly page" = `/nxerp/no-access`. No response in this document
contains a stack trace, a list of the apps a user lacks, or the name of a grant role (checked by the tests).

## Pages

| URL | Owner | Authentication | Who may open it | Unauthorised | Invalid or unknown |
| --- | --- | --- | --- | --- | --- |
| `GET /login` | `nxerp` (`www/login.*`) | none | everyone | n/a. A **signed-in** visitor is redirected to `/nxerp/go` (carrying `redirect-to`, which the router re-validates) | `redirect-to` that is not a safe same-origin path is **dropped** (301 to a plain `/login`); a safe one is rewritten to travel through the router (`/login?redirect-to=/nxerp/go?redirect-to=<target>`) |
| `GET /` | `nxerp` (`public_site.website_user_home_page`, hook `get_website_user_home_page`) | none | **a guest sees the public Home** (the page `www/nxerp/home.*`). Anyone signed in keeps Frappe's own answer for `/`, so the router still decides | n/a | site config `nxerp_keep_login_home` = 1 restores the old behaviour (a guest at `/` gets the login page). Cached per user outside developer mode: run `bench clear-cache` after changing it |
| `GET /nxerp/home` | `nxerp` (`www/nxerp/home.*`) | none | everyone; the same Home page, for a signed-in visitor too (header shows the avatar pill and "Open your apps") | n/a | n/a |
| `GET /products` | `nxerp` (`website_route_rules` -> `www/nxerp/products.*`) | none | everyone. Lists the **installed registry products** (never a test-only stand-in, never an uninstalled app), grouped by category; "Open application" instead of "Learn more" for a product the viewer holds | n/a | n/a |
| `GET /products/<key>` | `nxerp` (`website_route_rules` -> `www/nxerp/product.*`) | none | everyone, for an installed product key (`erpnext`, `helpdesk`) | n/a | **404**, the same page as any unknown URL, for an unknown, uninstalled, test-only or differently-cased key |
| `GET /get-started?product=<key>` | `nxerp` (`www/nxerp/get_started.*`, route rule) | none | a **guest** sees the page (product mark, "Create account", "I already have an account"). Signed in: redirected by `routing.get_started_target`: holds the app -> `/nxerp/go?redirect-to=<app route>`; otherwise `/welcome/<key>` (wizard, or the pending view when a request is open) | n/a | no `product` -> 301 `/products`; unknown, uninstalled or test-only key -> **404** |
| `GET /signup?app=<key>` | `nxerp` (`www/nxerp/signup.*`, route rule; split shell) | none | a guest. Shows the form to anyone; only when an administrator ticks Website Settings `disable_signup` does it show a calm "Signup is not available" state in the same layout (see `docs/features/signup-gate.md`). A signed-in visitor is redirected to `/get-started` | n/a | no `app` -> 301 `/products`; unknown key -> 404 |
| `GET /welcome/<key>` | `nxerp` (`www/nxerp/welcome.*`, route rule; split shell) | session | any signed-in user, for an installed product key: the first-run wizard, or the pending / invitation view. A user who already holds the app is redirected through the router. **Grants nothing** | Guest: 301 to `/login?redirect-to=/welcome/<key>` (the router honours `/welcome/<key>` for any signed-in user and refuses every other shape) | unknown key -> 404 |
| `GET /nxerp/no-access?app=<key>` | `nxerp` | none | as before, plus a primary "Request access" button to `/welcome/<key>` for a **signed-in** visitor when `<key>` is an installed product; no key, an unknown key, or a guest: unchanged page. Names no other application and no role | n/a | n/a |
| `GET /login/<anything>` (e.g. the old `/login/helpdesk`) | `nxerp` (`website_redirects`) | none | everyone | n/a | 301 to `/login` |
| `GET /nxerp/go` | `nxerp` (`www/nxerp/go.*`) | session | everyone; **the post-login router** | Guest: 301 to `/login` | Always answers with a redirect to a same-origin path; a bad `redirect-to` is ignored and the user's landing is used |
| `GET /nxerp/apps` | `nxerp` (`www/nxerp/apps.*`) | session | users with **two or more** apps (the launcher) | Guest: 301 to `/login?redirect-to=/nxerp/go`. A user who does not need a launcher is redirected to where the router would send them (one app: that app; none: the friendly page; customer: the portal) | n/a |
| `GET /nxerp/no-access` | `nxerp` (`www/nxerp/no_access.*`) | none (it is the safe place to send people) | everyone | n/a | n/a. Shows a "Manage user access" link only to platform administrators; nothing else varies by user |
| `GET /nxerp/test-app` | `nxerp`, **test-only** | session | holders of a test-only registered app, and only when the site has `allow_tests` on | Guest: 301 to `/login`; no grant: 301 to the friendly page | **404 on any site without `allow_tests`** (production). Never shipped as an app |
| `/helpdesk`, `/helpdesk/*` | Helpdesk (SPA) behind the `nxerp` gate | session | staff holding the Helpdesk grant (or implied `Agent` / `Agent Manager`); customers (`HD Customer*`) on the portal routes | Guest: 302 to `/login?redirect-to=<path>`. Signed in without the grant: 302 to the friendly page | unknown SPA paths are the SPA's own 404 view |
| `/desk/*` (ERPNext, e.g. `/desk/home`) | Frappe/ERPNext behind the `nxerp` gate | session | staff holding the ERPNext grant; platform administrators keep the Desk shell (never ERPNext data) | Guest: 302 to `/login?redirect-to=<path>`. No grant: 302 to the friendly page. Customers: 403 | Frappe's own 404 |
| bare `/desk` (and `/desk/`) | `nxerp` (`routing.desk_root_redirect`, called from the auth hook) | session | not a gateway: `/nxerp/apps` is the only one. After the gate allows it, a user with the ERPNext grant is redirected (302) to where the router would send them (`/desk/home` for ERPNext only, `/nxerp/apps` for several apps) | unchanged: the gate decides first (no grant: friendly page; guest: login) | **Not redirected:** a platform administrator without the ERPNext grant (keeps the Desk shell to grant access), an unfinished setup wizard (Administrator keeps the bare root until it is done), non-GET requests, and any site with `nxerp_keep_desk_root = 1` (kill-switch, takes effect within the 60 s config cache) |
| `/app`, `/app/*`, `/apps` | Frappe | as `/desk` | as `/desk` | as `/desk` | 301 to `/desk` (Frappe 16 behaviour, unchanged) |
| `GET /logout` | Frappe (not overridden) | session | everyone | n/a | ends the session, then `/login` |
| `/update-password?key=…` | Frappe (not overridden) | one-time key | holder of the emailed key | invalid or used key: Frappe's own message | n/a |
| `/v1/login` | nobody | n/a | n/a | n/a | 404. Frappe has no such route; `/login` is canonical |

## Information pages and the announced product (public, read-only)

| URL | Owner | Notes |
| --- | --- | --- |
| `/platform`, `/security`, `/solutions`, `/roadmap`, `/company`, `/partners`, `/get-in-touch` | `nxerp` (`www/nxerp/page.*`, one route rule each with a `slug` default; content in `nxerp/public_catalog.py`) | static copy, guests and signed-in users alike; no data, no forms. `/contact` and `/about` are deliberately not used: Frappe ships pages with those names |
| `/products/aira-hrms` | `nxerp` (`product.*`, from `public_catalog.UPCOMING`) | an announced product that is **not installed**: "Coming soon", no account flow. `/signup`, `/get-started` and `/welcome/` answer 404 for it. Once an app with that key is installed and registered the registry entry replaces the announcement |

## Landing rules (what `/nxerp/go` decides)

`nxerp.routing.route(user, redirect_to)`, in this order:

1. Guest or disabled user: `/login`.
2. `redirect-to` honoured **only if** it passes `routing.safe_target` **and** the user may use the app that owns
   the path (`routing.authorised_target`). Otherwise ignored.
3. Administrator while the setup wizard is unfinished: bare `/desk` (the one place it is still a destination), because only Desk's own router continues into the
   wizard (ADR-004 rule 5).
4. Otherwise `nxerp.access.resolve_landing`:

| User holds | Lands on |
| --- | --- |
| no app | `/nxerp/no-access` |
| exactly one app | that app's route (`/helpdesk/home`, `/desk/home`) |
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

Hooks that shape these routes (`apps/nxerp_platform/nxerp/hooks.py`; the exact set is asserted by `test_scaffold.py`):
`on_session_creation` (points a fresh login at the router), `extend_bootinfo` (Desk's own app switcher shows
only the user's apps, Framework hidden), `override_whitelisted_methods` (above), `website_redirects`
(`/login/<x>` to `/login`) and `standard_navbar_items` (the "All applications" row in Desk's user menu, shown
only when the server set `boot.nxerp.launcher`, i.e. to multi-app users).

## Switch-app links

Helpdesk's Apps menu (`hd-frontend/src/composables/useApps.ts`, Helpdesk fork) and Desk's user menu list the user's
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
| Social / LDAP / SSO | Frappe | not configured here; the NXERP page hides the buttons unless `SHOW_SOCIAL_LOGIN` is switched on (`apps/nxerp_platform/nxerp/www/login.py`) |
| Kill-switch | `nxerp` | site config `nxerp_stock_login = 1` serves Frappe's stock login (`docs/runbooks/login-recovery.md`) |

Site config is cached by every web worker for up to 60 seconds (`frappe/config.py`), so the kill-switch and any
other `bench set-config` change takes effect within a minute without a restart.

## Accessibility and branding

The login, launcher and no-access pages: one `h1`, a `main` landmark, labelled fields, `lang` set, a skip link on
the launcher and the no-access page, visible focus, text contrast checked in light and dark at 1440 and 390 px
wide, no horizontal scroll (`apps/nxerp_platform/browser-tests/pages.test.mjs`). These are automated basics, not a screen-reader audit.
NXERP branding appears on the login, launcher and no-access pages; ERPNext and Helpdesk keep their own names
and tiles. Palette tokens come from `apps/nxerp_platform/nxerp/public/css/nxerp-theme.css` only.

## Onboarding methods (Phase 2)

| Method | Verb | Guest | Session | Platform admin | Notes |
| --- | --- | --- | --- | --- | --- |
| `nxerp.api.account.sign_up(email, full_name, app)` | POST | **yes** (`allow_guest`) | yes | yes | 403 while signup is off; rate limited to 10 per hour per IP (`frappe.rate_limiter`); wraps Frappe's `sign_up`; the same neutral answer whether or not the email is registered; `app` must be an installed, non-test product; the post-login destination is `/welcome/<key>` built from the registry, never from input; drops Portal Settings' default role from the new account when it is a product portal role |
| `nxerp.api.onboarding.get_state(app)` | GET | refused | **own state only** | own state only | the user is `frappe.session.user`, never a parameter |
| `nxerp.api.onboarding.save_step(app, step, data)` | POST | refused | own state only | own state only | allow-listed fields and values; limited to 60 per hour; Frappe's CSRF check applies to the session |
| `nxerp.api.onboarding.submit(app)` | POST | refused | own state only | own state only | limited to 10 per hour; idempotent; policy `invite_only` creates no request, `request_access` creates one Pending request and emails the platform administrators, `open_portal` grants the product's portal role only |
| `nxerp.api.access_request.decide(name, decision, note)` | POST | refused | **refused (PermissionError)** | **yes** | `decision` is Approve or Reject; Approve runs `nxerp.api.access.set_app_access` (one grant path, last-administrator guard, Version log) and gives the Desk User role to a Website User; deciding twice returns the first decision |

Data: Desk list `/desk/nxerp-access-request` is the administrator queue (System Manager read and write; nobody else). `NXERP Onboarding` is System Manager read only.

## Cross-origin routes (identity site, Phase 6)

Off unless the site config key `nxerp_site_role` is `identity` or `app`; with it unset (or any other value) nothing here applies and no absolute URL is ever honoured.

* `nxerp_site_role = identity`: the apps are not installed on this site. Every registry entry that has an **enabled NXERP Peer** is active (`registry.active_entries()`), carrying the peer's `origin`. Tiles, the launcher, `/nxerp/apps` and the router (`/nxerp/go`) point at `origin + route`, and a user sees only the apps whose `NXERP Access: <app>` role they hold.
* `nxerp_site_role = app`: the app's own installed entries, as today. `/login` shows ONE button, "Sign in with NXERP" (the Social Login Key `frappe`), next to the password form. Local password login is never disabled from code.
* `routing.safe_target` still refuses every scheme, host, `//`, backslash and control character, **except** an absolute URL whose origin is *exactly* the origin of an enabled NXERP Peer (`registry.allowed_origins()`). https only (http only when `developer_mode`). Refused even for a registered peer: user-info (`https://evil.test@id.example.test`), a host that only starts or ends like a peer (`id.example.test.evil.test`), a trailing dot, another port, percent-encoding or non-ASCII characters in the authority, `javascript:`/`data:` and scheme-relative forms. Scheme and host are lower-cased and the result is returned normalised.
* `routing.authorised_target` honours an absolute target only when the user holds the app's access role AND the path is under that app's prefixes. The hostile-payload tests (`tests/test_routing.py`, 35 payloads) and the cross-origin cases (`tests/test_identity_site.py`) both pass with peers registered.
* The NXERP Peer DocType (System Manager only) holds the app's origin, internal URL, site name and the service credentials (Password fields, read only with `get_decrypted_password`).

## Provisioning endpoints (app sites, Phase 6)

Whitelisted in `nxerp/federation/api.py`. Not `allow_guest`. Active only when `nxerp_site_role` is `app` (otherwise `PermissionError`). The caller must hold the role **NXERP Provisioner** (a service user with that one role; `Authorization: token <key>:<secret>`). Every denial is logged through `nxerp/audit.py` with a hashed user reference. They are reachable on the app-to-app network only: the edge refuses `/api/method/nxerp.federation.*` (and `nxerp.shared.*`).

| Method | HTTP | Arguments | Answer |
| --- | --- | --- | --- |
| `nxerp.federation.api.provision_user` | POST | `email`, `full_name`, `enabled`=1, `user_type` (System User or Website User), `app_key`, `grant`=1, `idempotency_key` | `{"user", "created", "enabled", "app_access"}` |
| `nxerp.federation.api.deprovision_user` | POST | `email`, `idempotency_key` | `{"user", "enabled": false}` |
| `nxerp.federation.api.list_provisioned` | GET | `after` (email cursor), `limit` (max 200) | `{"users": [{"email", "enabled", "user_type", "apps"}], "next"}` |

Rules: a user is created without a password and without a welcome email; only the access role of the app this site owns is added or removed (never System Manager; business roles are untouched); Administrator and Guest are refused; users are disabled, never deleted; the same `idempotency_key` returns the stored answer for 7 days and the operations set a desired state, so a repeat changes nothing. Frappe turns a user with no desk-access role into a Website User, so a provisioned person needs a business role from the app's own administrator before they count as staff there.

`nxerp.api.access.set_app_access` on an identity site also queues provisioning and answers `"provisioning": "queued"` (unchanged elsewhere). On an identity site, `User` saves that change a grant queue a row in **NXERP Provisioning Outbox** (same transaction); the scheduler (`all`) delivers rows with exponential backoff (30 s doubling to 1 h, 8 attempts) and `nxerp.federation.reconcile.run` (`daily`) repairs drift toward the identity site.
