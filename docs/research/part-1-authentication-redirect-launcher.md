# Part 1 - Authentication, User Types, Post-Login Routing and the App Launcher

Source-based research for the NXERP umbrella platform (Frappe + ERPNext + Helpdesk).
Scope: how the installed code authenticates users, classifies them, routes them after login and builds the app launcher. Part 2 (permissions / enforcement) is a sibling document and is not repeated here.

This document describes existing behaviour. It does not design NXERP.

## Conventions and pinned sources

All paths are relative to the research source directory (`.../scratchpad/src/`), for example `frappe/frappe/auth.py:123`.

| Key | Repo | Pin |
|---|---|---|
| `frappe/` | Frappe Framework | v16.53.0, commit e8d41dd0061a32ee781caefe5d0b0d2bb7c15362 |
| `erpnext/` | ERPNext | v16.52.1, commit ade850bbd6a7412e9994a9637d2c5c713771632a |
| `helpdesk-fork/` | Company-customised Helpdesk | commit 1c6981cc5 (develop-based) |
| `telephony/` | Helpdesk dependency | as checked out |

Claim labels used throughout:

- **FACT** - read directly in the pinned source; evidence is `path:line`.
- **ASSUMPTION** - inferred from the source but not directly stated in it.
- **NOT FOUND** - searched for and absent in the pinned source.
- **NOT VERIFIED** - depends on runtime state (database content, Redis cache, browser behaviour). Section 11 lists the commands to verify these once a site exists.

Note on the running environment: project memory records that the Docker site currently runs Frappe 15 + an older Helpdesk, not these pins. Nothing below was observed on a running site.

## Table of contents

0. [Mechanism existence check](#0-mechanism-existence-check)
1. [Login and sessions](#1-login-and-sessions)
2. [First-time setup](#2-first-time-setup)
3. [User types and Desk access](#3-user-types-and-desk-access)
4. [Roles, profiles and module blocking](#4-roles-profiles-and-module-blocking)
5. [Post-login redirect chain](#5-post-login-redirect-chain)
6. [App launcher (the "apps screen")](#6-app-launcher-the-apps-screen)
7. [Helpdesk layering over Frappe auth](#7-helpdesk-layering-over-frappe-auth)
8. [ERPNext, portal and website users](#8-erpnext-portal-and-website-users)
9. [Cross-cutting gotchas](#9-cross-cutting-gotchas)
10. [Implications for NXERP](#10-implications-for-nxerp)
11. [Runtime verification checklist](#11-runtime-verification-checklist)

---

## 0. Mechanism existence check

Candidate names come from general knowledge; each was searched in the pinned source.

| Candidate | Status | Where / what exists instead |
|---|---|---|
| `LoginManager`, `HTTPRequest`, `CookieManager` | EXISTS | `frappe/frappe/auth.py:33,121,380` |
| `on_login` hook | EXISTS | fired `frappe/frappe/auth.py:171`; core subscriber `frappe/frappe/hooks.py:102` |
| `on_session_creation` hook | EXISTS | fired `frappe/frappe/auth.py:241`; subscribers `frappe/frappe/hooks.py:97`, `erpnext/erpnext/hooks.py:106` |
| `before_login` hook | EXISTS | fired `frappe/frappe/auth.py:147`; no core subscriber |
| `on_logout` hook | EXISTS | fired `frappe/frappe/auth.py:366`; subscriber `frappe/frappe/hooks.py:103` |
| `after_login` hook | NOT FOUND | only the cache key `redirect_after_login` exists (`frappe/frappe/auth.py:211`) |
| `login_redirect` function | NOT FOUND | no function of this name; redirect logic is in `auth.py:190-218`, `www/login.py:25-41`, `login.js:322-346` |
| `get_logged_user` | EXISTS | `frappe/frappe/auth.py:446-448` (whitelisted, returns `frappe.session.user`) |
| `validate_auth` | EXISTS | `frappe/frappe/auth.py:625`, called `frappe/frappe/app.py:116` |
| `authenticate_with_api_key` | NOT FOUND | actual names: `validate_auth_via_api_keys` (`auth.py:691`), `validate_api_key_secret` (`auth.py:717`) |
| OAuth bearer-token auth | EXISTS | `frappe/frappe/auth.py:651` (`validate_oauth`) |
| `auth_hooks` hook | EXISTS | `frappe/frappe/auth.py:746-748`; used by Helpdesk fork `helpdesk-fork/helpdesk/hooks.py:169` |
| `is_safe_redirect` | NOT FOUND | actual: `sanitize_redirect` (`frappe/frappe/www/login.py:206`) and JS `frappe.utils.sanitise_redirect` (`frappe/frappe/public/js/frappe/utils/common.js:327`) |
| `frappe.utils.is_site_link` | EXISTS but unused for login redirects | `frappe/frappe/utils/data.py:2896` |
| `frappe.desk.desk_access` module | NOT FOUND | no such file under `frappe/frappe/desk/` |
| `has_desk_access` | EXISTS as a `User` method | `frappe/frappe/core/doctype/user/user.py:462`; also a different, unrelated key in the Helpdesk API (`helpdesk-fork/helpdesk/api/auth.py:33`) |
| `Role.desk_access` | EXISTS | `frappe/frappe/core/doctype/role/role.json:74`, `role.py:22` |
| `user_type` (User field) | EXISTS | `frappe/frappe/core/doctype/user/user.py:153`; standard values "System User", "Website User" (`frappe/frappe/utils/install.py:68-73`) |
| `Role Profile` | EXISTS (v16: many-per-user via `role_profiles` table) | `frappe/frappe/core/doctype/role_profile/role_profile.py`; `user.py:276-291` |
| `Module Profile`, `Block Module` | EXISTS | `frappe/frappe/core/doctype/module_profile/`, `.../block_module/` |
| `Home Settings` | EXISTS only as a legacy hidden `User.home_settings` code field | `frappe/frappe/core/doctype/user/user.json:469`; not a routing mechanism (no reader found in routing code) |
| `User.home_page` field | NOT FOUND | no such field in `user.json` |
| `Role.home_page` | EXISTS | `frappe/frappe/core/doctype/role/role.py:23`; read at `frappe/frappe/website/utils.py:108` |
| `User.default_workspace` | EXISTS | `frappe/frappe/core/doctype/user/user.json:759`; read at `website/utils.py:133` |
| `User.default_app`, `System Settings.default_app` | EXISTS | `user.json:785`, `system_settings.json:697`; read `frappe/frappe/apps.py:99-100` |
| `home_page`, `role_home_page`, `website_user_home_page`, `get_website_user_home_page` hooks | EXIST | `frappe/frappe/website/utils.py:146-171` |
| `Website Settings.home_page` | EXISTS | `website_settings.json:91`; read `website/utils.py:122` |
| `Portal Settings.default_portal_home` | EXISTS | `portal_settings.py:20`; read `website/utils.py:114` |
| `frappe/www/apps.*` page | NOT FOUND | `/apps` is a 301 redirect to `/desk`: `frappe/frappe/hooks.py:70` |
| `frappe.apps` module | EXISTS | `frappe/frappe/apps.py` (`get_apps`, `get_route`, `get_default_path`, `set_app_as_default`, `get_incomplete_setup_route`, `is_desk_apps`, `get_docked_apps`) |
| `add_to_apps_screen` hook | EXISTS (exact name) | `frappe/frappe/apps.py:51`, `boot.py:290`; declared `frappe/frappe/hooks.py:579`, `erpnext/erpnext/hooks.py:13`, `helpdesk-fork/helpdesk/hooks.py:12` |
| `/desk` "desktop" apps page | EXISTS | `frappe/frappe/desk/page/desktop/desktop.js:168-206`, `desktop.py` |
| `frappe.is_setup_complete()` | EXISTS | `frappe/frappe/__init__.py:1542` |
| `setup_complete` (System Settings field, boot key) | EXISTS | `system_settings.py:108`, `sessions.py:179`, `boot.py:50` |
| `Portal User` DocType | NOT FOUND | the concept exists only as `is_portal_user()` (`frappe/frappe/utils/user.py:464`) |
| `Portal Settings` | EXISTS | `frappe/frappe/website/doctype/portal_settings/` |
| `portal_menu_items`, `standard_portal_menu_items` hooks | EXIST | `website/utils.py:482`; `portal_settings.py:62`; `erpnext/erpnext/hooks.py:259` |
| `frappe.twofactor` | EXISTS | `frappe/frappe/twofactor.py` |
| `frappe.www.update-password` | EXISTS (file `update-password.html` + `update_password.py`) | `frappe/frappe/www/` |
| `reset_password`, `update_password`, `sign_up` | EXIST | `frappe/frappe/core/doctype/user/user.py:1247,1024,1193` |
| Social login keys | EXISTS | `frappe/frappe/integrations/doctype/social_login_key/`, `frappe/frappe/utils/oauth.py` |
| LDAP | EXISTS | `frappe/frappe/integrations/doctype/ldap_settings/ldap_settings.py:404` |
| SAML | NOT FOUND | case-insensitive search of `.py/.json/.js` under `frappe/frappe` returned no match |
| OIDC provider (Frappe as IdP) | EXISTS | `frappe/frappe/integrations/oauth2.py:208,224` |
| OIDC/OAuth client | EXISTS via Social Login Key providers | provider options in `social_login_key.json:57`; endpoints `integrations/oauth2_logins.py` |
| User Invitation | EXISTS (v16, per-app) | `frappe/frappe/core/doctype/user_invitation/`, `core/api/user_invitation.py` |
| `boot_session`, `extend_bootinfo` hooks | EXIST | `frappe/frappe/boot.py:99`, `sessions.py:173` |
| `website_route_rules`, `website_redirects`, `page_renderer`, `website_path_resolver` hooks | EXIST | `frappe/frappe/website/path_resolver.py:56,96,140`, `get_website_rules` |
| Helpdesk `on_session_creation` / `boot_session` hook | NOT FOUND | absent from `helpdesk-fork/helpdesk/hooks.py` |
| Helpdesk app-tile permission callable | EXISTS | `helpdesk-fork/helpdesk/api/permission.py:12` |
| `erpnext.check_app_permission` | EXISTS | `erpnext/erpnext/__init__.py:158` |
| `frappe.permissions.check_app_permission` | EXISTS | `frappe/frappe/permissions.py:962` |

---

## 1. Login and sessions

### 1.1 What it is and where

Authentication lives in `frappe/frappe/auth.py`. The class `LoginManager` is instantiated on **every** HTTP request (not only login requests); it either performs a login or resumes/creates a session. `HTTPRequest` wraps it.

### 1.2 Request pipeline (FACT)

`frappe/frappe/app.py`:

- `init_request()` -> `frappe.local.http_request = HTTPRequest()` (`app.py:217`), unless the method is OPTIONS.
- `HTTPRequest.__init__` runs, in order: request IP, cookies, `set_session()` (builds `LoginManager`), language, CSRF validation, cookie flush (`auth.py:34-51`).
- `before_request` hooks run after that (`app.py:219-220`).
- Only then `validate_auth()` runs (`app.py:116`) - this is the API key / bearer token / `auth_hooks` stage.
- Then dispatch: `/api/...` to `frappe.api.handle`, everything else to the website renderer (`app.py:118-146`).

Consequence: the password login (`/api/method/login`) completes inside `HTTPRequest`, before `validate_auth` and before any app `before_request` hook.

### 1.3 Password login (FACT)

Trigger condition, `auth.py:130`:

```python
if frappe.local.form_dict.get("cmd") == "login" or frappe.local.request.path == "/api/method/login":
    if self.login() is False:
```

`LoginManager.login()` (`auth.py:146-168`), in order:

1. `run_trigger("before_login")` (147).
2. `disable_user_pass_login` System Setting blocks password login entirely (149-150).
3. `get_cached_user_pass()` - used for the 2FA second step (152).
4. `authenticate()` (153): `User.find_by_credentials` (id by email; optionally mobile/username if the two System Settings are on, `user.py:921-928`), then per-IP and per-user failure trackers (`auth.py:270-288`); rejects disabled users except Administrator (281).
5. `frappe.clear_cache(user=self.user)` (154).
6. 2FA if `should_run_2fa(user)` (156-159).
7. Forced password reset if the policy applies (161-165).
8. `post_login()` (168).

`post_login()` (`auth.py:170-177`): `on_login` hooks, `validate_ip_address`, `validate_hour`, `get_user_info`, `make_session`, `setup_boot_cache`, `set_user_info`.

`/api/method/login` itself is not a whitelisted function; `handler.handle()` skips execution when `cmd == "login"` (`frappe/frappe/handler.py:52`) and v2 defines an empty `login()` (`frappe/frappe/api/v2.py:56-58`). The v1 route `/api/method/login` ends in `handler.handle()`, so it is a no-op after `LoginManager` has already logged in (`api/v1.py:35-40`).

### 1.4 Session creation and cookies (FACT)

- `Session.start()` (`sessions.py:255-`): sid = `frappe.generate_hash()` for non-Guest; writes a `Sessions` table row (`insert_session_record`, `sessions.py:~300-320`) and the Redis hash `session` (`sessions.py:320`); updates last login metadata and commits.
- The session data snapshot stores `user_type` at creation: `"user_type": self.user_type` (`sessions.py:284`). This is what later code reads as `frappe.session.data.user_type` (for example `www/desk.py:56`, `website/utils.py:128`).
- `sid` cookie: `httponly=True`, `max_age=get_expiry_in_seconds()` (`auth.py:390`); `samesite="Lax"` default and `secure` only when the request scheme is https (`auth.py:392-404`).
- Convenience cookies `full_name`, `user_id`, `user_image`, `user_lang`, `system_user` are set **not** httponly (`auth.py:196-218`). The Helpdesk SPA reads `user_id` from `document.cookie` (`helpdesk-fork/desk/src/stores/auth.ts:65-70`).
- Session expiry default `"240:00:00"` (`sessions.py:524`); `deny_multiple_sessions` (conf or System Setting) revokes other sessions at login (`auth.py:248-254`).
- A change of `User.user_type` invalidates all of that user's sessions (`user.py:368-369`: `clear_sessions(user=self.name, force=True)`).
- `bootinfo` (the Desk boot payload) is cached in Redis per user (`sessions.py:140,148`) and cleared via `frappe.clear_cache(user=...)` (`cache_manager.py:62-80`, key `bootinfo`, `roles`, `home_page`, `portal_menu_items`, `user_doc`...). `User.on_update` calls `frappe.clear_cache(user=self.name)` (`user.py:334`).

### 1.5 CSRF (FACT)

`HTTPRequest.validate_csrf_token` (`auth.py:81-97`): enforced for POST/PUT/DELETE/PATCH when the session has a saved token; accepts `X-Frappe-CSRF-Token` header or `csrf_token` form value, or an allowed Referer/Origin (`allowed_referrers` in site config, `auth.py:102-118`). Skipped when `frappe.conf.ignore_csrf` is set or the session has no token.

### 1.6 Rate limiting and lockout (FACT)

- Failed password logins are counted per user name and per client IP in Redis (`LoginAttemptTracker`, `auth.py:526-622`). Lock after `allow_consecutive_login_attempts` failures (default 10, `system_settings.json:330`) for `allow_login_after_fail` seconds (default 60, `system_settings.json:340`).
- `/api/method/login` has no `@rate_limit` decorator; the decorator is applied to `send_login_link`, `login_via_key` (`www/login.py:139,185`), `reset_password` (`user.py:1246`) and a few others.
- ASSUMPTION: the client IP used by the tracker comes from `X-Forwarded-For` when present (`auth.py:63-64`); behind a reverse proxy this header must be set by trusted infrastructure only. NOT VERIFIED on the target deployment.

### 1.7 Non-cookie authentication (`validate_auth`) (FACT)

`auth.py:625-648`: parses `Authorization` header (two tokens).

1. `validate_oauth` - `Bearer <token>`; verified through `oauthlib` against the OAuth Bearer Token table, then `frappe.set_user(...)` (`auth.py:651-688`).
2. `validate_auth_via_api_keys` - `Basic base64(key:secret)` or `token key:secret`; looks up `User.api_key` with `enabled=True`, compares to the decrypted `api_secret`, then `frappe.set_user(user)` (`auth.py:691-743`). The doctype can be redirected with the `Frappe-Authorization-Source` header (`auth.py:701,722`).
3. `validate_auth_via_hooks` - every function listed in the `auth_hooks` hook is called (`auth.py:746-748`).
4. If an Authorization header was supplied but the user is still Guest, raise `AuthenticationError` (`auth.py:640-641`).
5. IP allow-list is re-checked for any user set here (`auth.py:647-648`).

API keys are generated by `generate_keys` (System Manager only, `user.py:1534-1550`). API key / bearer-token requests do **not** go through 2FA or `on_login`/`on_session_creation`; they never create a `Sessions` row (they use `frappe.set_user`). NOT VERIFIED at runtime, but follows from the code path above.

### 1.8 Alternate login routes

| Route | Entry point | Runs 2FA? | Redirect target |
|---|---|---|---|
| Password | `/api/method/login` -> `LoginManager.login` | Yes (`auth.py:156`) | `home_page` in JSON response (section 5) |
| Social / OAuth client | `frappe.utils.oauth.login_oauth_user` -> `login_as(user)` (`utils/oauth.py:259`) | **No** - `login_as` goes straight to `post_login` (`auth.py:352-354`) | `redirect_post_login` (`oauth.py:365-373`) |
| LDAP | `ldap_settings.login` (`ldap_settings.py:404-422`) | Yes (413-416) | JSON response from `post_login` |
| Email link ("login with email link") | `login_via_key` (`www/login.py:184-196`) | **No** | `redirect_post_login` |
| Login token | `login_via_token` (`www/login.py:119-131`) | n/a (consumes existing sid) | `redirect_post_login` |
| Password reset link | `update_password` (`user.py:1024-1076`) | Returns "/login" if 2FA applies and key used (`user.py:1062-1063`) | server-computed URL |
| User Invitation accept | `_accept_invitation` (`core/api/user_invitation.py:148-173`) | **No** | `redirect_to_path` (see section 5.7) |
| Impersonation | `LoginManager.impersonate` (`auth.py:356-361`) | n/a | n/a |

Helpdesk fork UI: the fork's login page hides social login (`SHOW_SOCIAL_LOGIN = False`, `helpdesk-fork/helpdesk/www/login.py:16,52-54`) and forces `login_with_email_link = 0` (`login.py:51`). That is UI only: the backend endpoints stay reachable (and the fork's own `ALLOWED_PATHS` list names them, `helpdesk-fork/helpdesk/auth.py:20-31`).

### 1.9 Signup, forgot / reset password

- Signup `sign_up(email, full_name, redirect_to)` is `allow_guest=True` (`user.py:1192-1193`). It rejects when `is_signup_disabled()`, caps signups per hour (`max_signups_allowed_per_hour`, default 300, `user.py:1204`), creates a **Website User** (`"user_type": "Website User"`, `user.py:1224`), then adds `Portal Settings.default_role` (`user.py:1231-1233`). It stores the sanitised `redirect_to` in the Redis hash `redirect_after_login` (`user.py:1236-1237`), which `set_user_info` returns to the client on first login (`auth.py:211-213`).
- Forgot password `reset_password(user)`: guest-callable, POST only, rate-limited, always returns the same generic message (anti-enumeration, `user.py:1245-1270`). Administrator and disabled users silently skipped (`user.py:1254`).
- Reset page `www/update-password.html` posts to `update_password` (`update-password.html:164`); the server returns the post-reset URL and the page navigates to it (`update-password.html:181`). After a successful reset the code logs the user in (`login_as(user)`, `user.py:1071`) and returns `get_default_path() or "/desk"` for System Users, else `redirect_url or get_default_path() or get_home_page()` (`user.py:1073-1076`).
- NOT FOUND: any consumer of a `redirect_to` query parameter in `update-password.html` / `update_password.py`. `User Invitation` appends `&redirect_to=/...` to the reset URL (`core/api/user_invitation.py:168`), but no reader for it was found. NOT VERIFIED at runtime.

### 1.10 2FA (`frappe.twofactor`) (FACT)

- Enabled by System Settings `enable_two_factor_auth` (default 0, `system_settings.json:353-358`). Per-role flag `Role.two_factor_auth` decides who is challenged: the user's roles plus the implicit `All` role are checked (`twofactor.py:109-119`). If `All` has the flag, everyone is challenged.
- Optional bypass for users with a restricted IP list (`twofactor.py:44-62`).
- Methods: OTP App (TOTP), SMS, Email (`twofactor.py`, `get_verification_obj`). The first login call stashes user+password in Redis under a `tmp_id` for 180-300 s (`twofactor.py:94-106`); the second call posts `tmp_id`+`otp`.
- Gotcha: social login, email-link login, invitation accept and password-reset auto-login do not run this challenge (table in 1.8). Whether this matters is a policy decision for NXERP.

### 1.11 Federation: what exists in v16

- Social Login Key providers: Custom, Facebook, Frappe, GitHub, Google, Office 365, Salesforce, fairlogin, Keycloak (`social_login_key.json:57`). Provider login endpoints: `integrations/oauth2_logins.py`.
- Generic OIDC client: only via provider "Custom" / "Keycloak" configuration (ASSUMPTION; endpoint `oauth2_logins.custom`, `oauth2_logins.py:52-63`).
- LDAP: `LDAP Settings` + `ldap_settings.login` and group mapping (`integrations/doctype/ldap_settings`, `ldap_group_mapping`).
- Frappe as OIDC/OAuth2 provider: `oauth2.py` (`authorize`, `get_token`, `openid_profile`, `/.well-known/openid-configuration`, `oauth2.py:224,296`).
- SAML: NOT FOUND.
- New social-login users are created as `user_type: "Website User"` (`utils/oauth.py:304`), and a missing user is created only if the provider allows sign-ups (`provider_allows_signup`, `oauth.py:279-285`; the `Allow`/`Deny` option is on `social_login_key.json:176`).
- The login page lists providers only if client id, base url and keys resolve (`www/login.py:67-97`).

---

## 2. First-time setup

### 2.1 Administrator creation (FACT)

- `frappe.utils.install.before_install` creates the standard User Types and the two standard users **Administrator** (`is_admin=1`, role Administrator) and **Guest** (`frappe/frappe/utils/install.py:26-27,76-100`).
- `after_install` grants Administrator every Role that exists at that moment (`utils/install.py:41`: `add_roles(*frappe.get_all("Role", pluck="name"))`) and sets the password from site config `admin_password` or an interactive prompt (`utils/install.py:44,115`). ERPNext repeats the grant for its own roles (`erpnext/erpnext/setup/install.py:31`, `add_all_roles_to("Administrator")`).
- In addition `frappe.permissions.get_roles("Administrator")` is special-cased to return **all** Role names (`permissions.py:551-552`), so roles created later still count for Administrator.
- User type for the standard users is forced (Administrator -> System User, Guest -> Website User) only when a non-standard User Type is set (`user.py:436-441`); otherwise `user_type` is recomputed from roles with desk access (`user.py:445`).

### 2.2 Setup-state flags

| Flag | Where | Meaning |
|---|---|---|
| `Installed Application.is_setup_complete` + `has_setup_wizard` | `core/doctype/installed_applications/installed_applications.py:28-59` | Per-app wizard state. Only `frappe` and `erpnext` get `has_setup_wizard = 1`; every other app is forced to `has_setup_wizard = 0` (`installed_applications.py:45-47`). |
| `frappe.is_setup_complete()` | `frappe/frappe/__init__.py:1542-1556` | True when `is_setup_complete` is set on **both** `frappe` and `erpnext` rows (`app_name in ["frappe","erpnext"]`, `__init__.py:1549-1550`). |
| `System Settings.setup_complete` | `system_settings.py:108`; written `installed_applications.py:70`, `setup_wizard.py:414` | Cached copy of the above. Read by the Helpdesk boot (`helpdesk-fork/helpdesk/www/helpdesk/index.py:37`). |
| Default `desktop:home_page` | `utils/install.py:46-49`, `setup_wizard.py:410` | Set to `"setup-wizard"` on install unless site config `skip_setup_wizard` is set; changed to `"workspace"` when the wizard finishes. Read by `boot.add_home_page` (`boot.py:444`). |
| `HD Settings.setup_complete` | `helpdesk-fork/helpdesk/api/config.py:11`, `hd_settings.json:144` | Helpdesk's own flag, exposed to the SPA through `get_config` (guest-callable, `config.py:7`). Not read by Frappe. |

Edge cases (FACT):

- If no `frappe`/`erpnext` rows exist, `all([])` evaluates True and `is_setup_complete()` returns True (`__init__.py:1547-1552`). When ERPNext is **not** installed, only the `frappe` row decides.
- `update_versions` marks `frappe` complete if any non-admin System User exists, and `erpnext` complete if any Company exists (`installed_applications.py:38-43`, helpers `has_non_admin_user`/`has_company` at 78-90). It runs on install/migrate (`installer.py:402,416,474`; `migrate.py:206`).

### 2.3 Fresh Administrator login before setup completes (FACT + NOT VERIFIED)

Server side:

1. `POST /api/method/login` succeeds; the response `home_page` is `get_home_page() or "/desk"` (`auth.py:205`) - the setup state is **not** consulted by this code.
2. `GET /desk` renders `www/desk.py`: only Guest and Website User are rejected (`www/desk.py:51-58`). Nothing server-side checks `is_setup_complete()` on page load.
3. Boot: `bootinfo.sysdefaults["setup_complete"]` and `bootinfo["setup_complete"]` carry the flag (`boot.py:50`, `sessions.py:179`); when not complete, `setup_wizard_requires` is added (`boot.py:446-447`). `bootinfo.home_page` becomes the Page named by default `desktop:home_page` (`"setup-wizard"` pre-setup) (`boot.py:444-455`).

Client side (this is where the redirect to the wizard happens):

- `frappe.router.route()`: if `!frappe.boot.setup_complete` and the route is not already `setup-wizard`, call `frappe.set_route(["setup-wizard"])` (`public/js/frappe/router.js:180-185`).
- Conversely, once complete, the wizard page bounces away: `window.location.href = frappe.boot.apps_data.default_path || "/desk"` (`desk/page/setup_wizard/setup_wizard.js:36-38`).
- The `setup-wizard` Page is restricted to role System Manager (`desk/page/setup_wizard/setup_wizard.json`, `roles`).

So the wizard redirect is a Desk-SPA behaviour, not a server redirect. Anything that lands the Administrator somewhere other than `/desk` (for example `/helpdesk`) never reaches that redirect. NOT VERIFIED at runtime.

### 2.4 What the wizard does (FACT)

`frappe.desk.page.setup_wizard.setup_wizard.setup_complete` (`setup_wizard.py:58-77`): whitelisted for any logged-in user; no role check appears in the function. It short-circuits when `is_setup_complete()` (66-67) and is serialised by a file lock (65).

Stages: frappe's language/region stage, then every installed app's `setup_wizard_stages` hook, then every `setup_wizard_complete` hook, then post-completion (`setup_wizard.py:38`, `get_stages_hooks` 229-243, `get_setup_complete_hooks` 255-267). Per task, the app name is derived from the hook path or declared stage (`app_name = method.split(".")[0]`, 262), and `enable_setup_wizard_complete(app)` flags that app's `Installed Application` row (`setup_wizard.py:184-185`, called at 129 and 131).

Wizard user creation (`create_or_update_user`, `setup_wizard.py:316-354`): inserts a User with `_get_default_roles()` plus `System Manager` (347). `run_post_setup_complete` -> `disable_future_access()` flips `desktop:home_page` to `workspace` and sets `setup_complete` (`setup_wizard.py:205-210,409-414`). In non-developer mode, the first user is then logged in automatically (`login_as_first_user`, `setup_wizard.py:222-224`, called from `run_setup_success` at 214-219).

### 2.4a ERPNext wizard

- `erpnext/erpnext/hooks.py:89-90` registers `setup_wizard_requires` and `setup_wizard_stages`. ERPNext's tile advertises the wizard intro via `setup_wizard_text` (`erpnext/erpnext/hooks.py:19`).
- `erpnext.startup.boot.boot_session` shows a "no company" hint through `bootinfo.setup_complete` when no Customer exists (`erpnext/erpnext/startup/boot.py:43-54`).

### 2.5 Helpdesk setup (FACT)

`helpdesk-fork/helpdesk/hooks.py:31` `after_install = helpdesk.setup.install.after_install` (`setup/install.py:18-41`). It seeds statuses, SLAs, agent groups, templates, a welcome ticket, and:

- `setup_customer_role()` (install.py:29, 216-229): creates/updates roles **HD Customer** and **HD Customer Manager** with `home_page = "/helpdesk"` and `desk_access = 0`, then (fresh install) calls `set_portal_defaults(overwrite=True)`.
- `set_portal_defaults` (install.py:232-250) writes `Portal Settings.default_role = "HD Customer"` and `Portal Settings.default_portal_home = "/helpdesk"` straight into the Single.
- `setup_wizard_complete = helpdesk.setup.setup_wizard.setup_complete` (`hooks.py:162`) creates an `HD Agent` for the wizard user (`setup/setup_wizard.py:9-23`). If the wizard is bypassed (`skip_setup_wizard`, or completion by other means) that agent record is not created. NOT VERIFIED.
- Helpdesk declares no `setup_wizard_stages` (commented out, `hooks.py:160-161`) and is `has_setup_wizard = 0` in `Installed Application` (`installed_applications.py:45-47`), so Frappe never gates Helpdesk's tile behind a wizard (`apps.py:42-47`).

### 2.6 What breaks if the post-login redirect ignores setup state (derived, FACT-based)

| If the redirect... | Then (derived from the code above) |
|---|---|
| sends the first Administrator to `/helpdesk` or a custom launcher before `/desk` | The Desk SPA is never loaded, so `router.js:180-185` never routes to the wizard; Frappe/ERPNext remain `is_setup_complete = 0`. |
| marks the user "ready" while ERPNext wizard is pending | The ERPNext tile is hidden from every non-System-Manager (`apps.py:42-47`) and `get_default_path()` ignores it for them; ERPNext users who are not System Managers see no ERPNext tile until a Company exists. |
| lands a non-System-Manager before setup is done | They reach `/desk` with `boot.setup_complete = false` and are pushed to `setup-wizard` by the SPA, which the Page role restriction then denies (permission error) - a dead end. NOT VERIFIED. |
| relies on `frappe.is_setup_complete()` as the single truth | It reflects only `frappe` and `erpnext`; Helpdesk readiness (`HD Settings.setup_complete`, agent record) is separate. |

---

## 3. User types and Desk access

### 3.1 Definitions (FACT)

- Two standard User Types: "System User" and "Website User" (`utils/install.py:68-73`). Custom User Types exist (`core/doctype/user_type`); when a non-standard type is set, the roles/modules come from the User Type (`user.py:438-442`, `user_type.py`).
- `User.user_type` is recomputed on every validate: standard types become `"System User" if self.has_desk_access() else "Website User"` (`user.py:444-445`).
- `has_desk_access()` (`user.py:462-471`): returns true if **any** of the user's roles has `Role.desk_access = 1` (a count query against `tabRole`).
- Changing `Role.desk_access` re-evaluates every user holding that role (`role.py:68-84`).
- Roles auto-created because a DocType's permission table names them get `desk_access = 1` (`core/doctype/doctype/doctype.py:2024-2031`). Roles created explicitly keep whatever the creator sets (Helpdesk sets 0 for HD Customer roles, `install.py:225`; Agent and Agent Manager are not created explicitly in the fork - they come from DocType permission rows such as `hd_ticket.json:541,553` - so ASSUMPTION: they are `desk_access = 1`. NOT VERIFIED.)
- Invited users are created with `user_type = "System User"` (`user_invitation.py:151`) but validate recomputes it from roles (so roles with `desk_access = 0` yield a Website User). ASSUMPTION from `user.py:444-445`.

### 3.2 Where Frappe decides whether `/desk` (and legacy `/app`) may load

The only server-side gate is `frappe/frappe/www/desk.py:50-58`:

```python
if frappe.session.user == "Guest":
    ...
    frappe.redirect(f"/login?{urlencode({'redirect-to': frappe.request.path})}")
elif frappe.session.data.user_type == "Website User":
    frappe.throw(_("You are not permitted to access this page."), frappe.PermissionError)
```

- It reads the **session snapshot** `user_type` (section 1.4), not the live `User` row. Staleness is bounded because a `user_type` change clears the user's sessions (`user.py:368-369`).
- `/desk` and `/desk/*` are hard-wired ahead of all other routing: `path_resolver.py:44-45` returns `TemplatePage("desk")`.
- There is no check on `desk_access` roles, module access, app tiles or `block_modules` at this gate. Any System User (every user with at least one `desk_access` role) can load the Desk shell. `/app` and `/apps` are redirects to `/desk` (`hooks.py:69-71`).
- After the shell loads, `frappe.sessions.get()` / `get_bootinfo()` builds the boot payload filtered per user (permitted DocTypes, module sidebars, `app_data`, ...). That filtering is UI-level; data access is enforced by DocType permissions (part 2).
- `frappe.permissions.is_system_user` = `User.user_type == "System User"` (`permissions.py:914-915`); note the older `frappe.utils.user.is_system_user` also filters `enabled=1` and matches on `email` (`utils/user.py:416-427`).

### 3.3 Website User restrictions that are enforced by code

- `/desk` refused (above).
- `erpnext.check_app_permission` returns False for Website Users (`erpnext/erpnext/__init__.py:162-163`).
- Frappe's own tile requires System User **and** System Manager (`permissions.py:962-966`).
- File upload MIME restriction applies to Guests and users without desk access (`handler.py:215-218`).
- Login redirect uses a different branch ("No App", `auth.py:196-200`).
- The "system_user" cookie is set to "no" (`auth.py:197`); the website navbar shows "Switch To Desk" only for `system_user == yes` (`website/js/website.js:~650`).

### 3.4 Boot / `frappe.get_roles` automatic roles

`permissions.py:32-40`:

```python
GUEST_ROLE = "Guest"; ALL_USER_ROLE = "All"; SYSTEM_USER_ROLE = "Desk User"; ADMIN_ROLE = "Administrator"
AUTOMATIC_ROLES = (GUEST_ROLE, ALL_USER_ROLE, SYSTEM_USER_ROLE, ADMIN_ROLE)
```

`get_roles(user)` (`permissions.py:542-576`): Guest -> `["Guest"]`; Administrator -> all Role names; otherwise the user's `Has Role` rows (excluding automatic roles) plus `All`, `Guest`, and `Desk User` if the user is a System User. Result cached in the Redis hash `roles` (`permissions.py:568`).

---

## 4. Roles, profiles and module blocking

### 4.1 Role, Has Role, Role Profile (FACT)

- `Role` fields of interest: `home_page`, `desk_access`, `two_factor_auth`, `disabled`, `restrict_to_domain` (`role.json:12-18`). `STANDARD_ROLES` cannot be renamed/disabled (`role.py:10,31-33,45-49`). Disabling a role deletes its `Has Role` rows (`role.py:49,63-65`).
- `Role.validate_homepage` validates the path through the website path resolver and clears the routing cache on change (`role.py:51-56`).
- `User.roles` is the child table of `Has Role`. `Role Profile` (v16: a user can have many, `role_profiles` table) populates roles: on User validate, `populate_role_profile_roles` **replaces** manual roles with the union of profile roles (`self.roles = [r for r in self.roles if r.role in new_roles]`, `user.py:276-291`). Roles added manually are dropped whenever a user has at least one Role Profile. Profile edits re-save all users asynchronously (`role_profile.py:28-42`, queue "long").
- Standard users (Guest, Administrator) have role profiles cleared (`user.py:280-282`).

### 4.2 `frappe.get_roles` caching (FACT)

`frappe.cache.hget("roles", user, get)` (`permissions.py:568`). Invalidated by `frappe.clear_cache(user=...)` (cache key list `cache_manager.py:62-80` includes `roles`, `user_doc`, `bootinfo`, `home_page`, `portal_menu_items`). Creating a Role clears the Administrator entry (`role.py:35-36`). Any code that writes `Has Role` rows without `User.save()` and without clearing cache leaves stale roles. NOT VERIFIED for specific non-standard writers.

### 4.3 What Administrator bypasses (FACT, partial)

- `get_roles("Administrator")` returns every Role (`permissions.py:551-552`).
- `has_permission` short-circuits for Administrator (`permissions.py:108`, `306`) - detail belongs to part 2.
- Helpdesk and ERPNext tile callables explicitly return True for Administrator (`helpdesk-fork/helpdesk/api/permission.py:14-15`, `erpnext/erpnext/__init__.py:159-160`).
- `LoginManager.authenticate` lets Administrator log in even if `enabled` is false (`auth.py:281`).
- Standard users are excluded from forced password reset (`auth.py:295-296`) and from "reset_password" emails (`user.py:1254`).

### 4.4 Module Profile and Block Module (FACT)

- `User.block_modules` (child table `Block Module`) is filled from a `Module Profile` on User validate (`user.py:321-324`); the module list shown in the profile editor is all blockable modules (`utils/modules.py`, `get_blockable_module_names`).
- The authoritative statement of intent is in `frappe/frappe/utils/modules.py:26-58`:
  - `get_blocked_modules` returns only the user's own `block_modules`, with the explicit note "Don't reintroduce the Administrator union" (`modules.py:26-42`).
  - `is_module_visible` docstring: "This is navigation reach only. Never call it from `has_permission`. Document access is decided by DocPerm ... Hiding a module hides the way to a document, never the document itself." (`modules.py:45-58`).
- Where it is applied (FACT, grep of callers): module sidebars/dock (`desk/doctype/sidebar/sidebar.py:1762`, `dock.py:1048`), desktop icons (`desktop_icon.py:137`), workspace visibility `Workspace.is_permitted` (`workspace.py:1257`), `desk/desktop.py:84`, boot `get_visible_modules` (`boot.py:406`), module-scoped dashboard/chart/number-card pickers (`dashboard.py:11`, `dashboard_chart.py:24`, `number_card.py:17`).
- Where it is NOT applied: `frappe.has_permission`, REST (`/api/resource`), RPC (`/api/method`), `frappe.get_list`, direct `/desk/<doctype>` URLs, and any non-Desk SPA such as Helpdesk. A search of non-test Python for `get_blocked_modules`/`is_module_visible` shows only the navigation callers above.
- NOT FOUND: a v16 boot key `allowed_modules`; the equivalent per-user list is `User.allow_modules` / `permitted_modules` in `utils/user.py:62-63,141-156,278-296`, computed from DocType read permission (not from `block_modules`).
- Consequence: `block_modules` cannot be used as an access control for ERPNext vs Helpdesk. It also does not hide a non-Desk app because Helpdesk modules are not part of the Desk dock for the SPA.

### 4.5 Home Settings / default workspace

- `User.default_workspace` (Link to Workspace) overrides every other home-page source in `get_home_page` (`website/utils.py:133-136`; loaded by `UserPermissions.load_user`, `utils/user.py:~230-250`). NOT FOUND: a User-level `home_page` field.
- `User.home_settings` exists as a hidden legacy Code field (`user.json:469`); no routing code reads it.

---

## 5. Post-login redirect chain

There are several independent flows that each compute a landing URL, and they do **not** share one function. This section lists each flow and its exact ordering.

### 5.1 Flow A - password login from the login page (the common path)

Server (`auth.py:190-213`, `set_user_info`):

```python
if self.info.user_type == "Website User":
    frappe.local.response["message"] = "No App"
    if not resume:
        frappe.local.response["home_page"] = get_default_path() or "/" + get_home_page()
else:
    frappe.local.response["message"] = "Logged In"
    if not resume:
        frappe.local.response["home_page"] = get_home_page() or "/desk"
...
if not resume and (redirect_to := frappe.cache.hget("redirect_after_login", self.user)):
    frappe.local.response["redirect_to"] = redirect_to
    frappe.cache.hdel("redirect_after_login", self.user)
```

Key facts:

1. **System Users do not use `get_default_path()` on this path** (line 205); only Website Users do (line 200). `default_app` (user or system) and the apps-screen logic are therefore not applied to a System User's first redirect. They reach them only if `get_home_page()` ends at `/desk` and the Desk then shows the apps screen.
2. `set_user_info` runs **after** the `on_login` and `on_session_creation` hooks (`post_login` order, `auth.py:171-177`; `make_session` fires `on_session_creation` at 241). A hook cannot overwrite `frappe.local.response["home_page"]` because it is assigned afterwards. A hook **can** influence the result by setting `frappe.local.flags.home_page`, which `get_home_page` returns first (`website/utils.py:99-100`).
3. The `redirect_after_login` cache entry is set only by `sign_up` (`user.py:1237`).

Client (`frappe/frappe/templates/includes/login/login.js:322-346`):

```js
if (data.message == 'Logged In') {
    window.location.href = frappe.utils.sanitise_redirect(frappe.utils.get_url_arg("redirect-to")) || data.home_page;
} else if (data.message == "No App") {
    var last_visited = localStorage.getItem("last_visited") || sanitise_redirect(get_url_arg("redirect-to"));
    localStorage.removeItem("last_visited");
    if (data.redirect_to) { window.location.href = sanitise_redirect(data.redirect_to); }
    if (last_visited && last_visited != "/login") { window.location.href = last_visited; }
    else { window.location.href = data.home_page; }
}
```

Precedence for **System Users**: `?redirect-to=` (sanitised) > `data.home_page`. `data.redirect_to` is ignored for them.
Precedence for **Website Users**: the three assignments are not mutually exclusive (no `return`/`else`): effective winner is `last_visited` (localStorage, then `redirect-to`), else `data.home_page`; `data.redirect_to` is overwritten by the later assignment. NOT VERIFIED which navigation the browser honours; ASSUMPTION: the last assignment wins.

`localStorage["last_visited"]` is written by `ask_to_login()` in website JS (`website/js/website.js:611-618`) and is **not** passed through `sanitise_redirect` in this branch (`login.js:333-344`). It is same-origin storage, so exploitation requires prior script execution on the site.

### 5.2 `get_home_page()` - exact order (`frappe/frappe/website/utils.py:98-143`)

| # | Source | Lines | Notes |
|---|---|---|---|
| 0 | `frappe.local.flags.home_page` | 99-100 | Per-request override (not in tests). |
| 1 | `Role.home_page` of the first role in `frappe.get_roles()` order that has one | 105-110 | Non-Guest only. For Administrator, roles are *all* roles. Order within `get_roles` is query order - not guaranteed. |
| 2 | `Portal Settings.default_portal_home` | 112-114 | Applied to **every** non-Guest user lacking a role home page, including System Users. |
| 3 | Hooks via `get_home_page_via_hooks()` | 116-118, 146-171 | In sub-order: `get_website_user_home_page` (callable, **last** app, receives user) > `website_user_home_page` (last) > `role_home_page` (dict: role -> list; first matching role, last app) > `home_page` hook (last). |
| 4 | `Website Settings.home_page` | 120-122 | |
| 5 | `"login"` for Guest, otherwise `"me"` | 124-125 | |
| 6 | Normalisation | 127-131 | `.strip("/")`; `me` -> `desk` for System User; `me` -> `portal` for portal users (Website User + a role listed in the Portal menu, `utils/user.py:464-470`). |
| 7 | `User.default_workspace` | 133-136 | Overrides **all** of the above with `/desk/<slug>` or `/desk/private/<slug>`. |

Cache: the result is stored in the per-user Redis hash `home_page` (`website/utils.py:143`) unless `frappe._dev_server`. Cleared by `frappe.clear_cache(user=..)` and by website `clear_cache()` (`website/utils.py:~405-411`, `website/router.py:323`).

Important output-shape facts:

- Except for step 7, the returned value has no leading slash (`strip("/")`, 127). `auth.py:205` returns it unchanged for System Users, so the browser receives a relative URL such as `helpdesk` which resolves against `/login` to `/helpdesk`. For Website Users `"/" + get_home_page()` (`auth.py:200`); if step 7 applies it would produce `//desk/...` (a protocol-relative URL). Edge case; not expected for Website Users, who cannot use Desk. NOT VERIFIED.
- The role/hook sources return paths that `website/path_resolver` must accept; `Role.validate_homepage` checks this at save time (`role.py:51-53`).

### 5.3 Flow B - `GET /login` while already logged in (`www/login.py:25-41`)

```python
redirect_to = sanitize_redirect(frappe.local.request.args.get("redirect-to"))
if frappe.session.user != "Guest":
    if not redirect_to:
        if frappe.session.data.user_type == "Website User":
            redirect_to = get_default_path() or get_home_page()
        else:
            redirect_to = get_default_path() or "/desk"
    if redirect_to != "login":
        frappe.local.flags.redirect_location = redirect_to
        raise frappe.Redirect
```

This flow **does** use `get_default_path()` for System Users - unlike Flow A. Two logins to the same account (fresh POST vs. revisiting `/login`) may therefore land on different pages. NOT VERIFIED at runtime but follows directly from `auth.py:205` vs `www/login.py:37`.

### 5.4 `get_default_path()` - exact order (`frappe/frappe/apps.py:92-110`)

```python
apps = get_apps()
_apps = [app for app in apps if app.get("name") != "frappe"]
if len(_apps) == 0: return None
system_default_app = frappe.get_system_settings("default_app")
user_default_app = frappe.get_cached_value("User", frappe.session.user, "default_app")
if system_default_app and not user_default_app: return get_route(system_default_app)
elif user_default_app: return get_route(user_default_app)
if len(_apps) == 1: return _apps[0].get("route") or "/desk"
elif is_desk_apps(_apps): return "/desk"
return "/apps"
```

1. No accessible app (after `has_permission` and setup-wizard filtering, section 6.3) -> `None`.
2. Otherwise `User.default_app` beats `System Settings.default_app`.
3. **Neither default is re-checked against `has_permission`**: `get_route(app_name)` (`apps.py:76-81`) returns the declared route for any installed app whose `add_to_apps_screen` entry has `name == app_name`, else `"/apps"`. The only gate is that *some* app is accessible (step 1). A Helpdesk-only user with a system-level default app of ERPNext receives `/desk/home`. NOT VERIFIED at runtime.
4. One accessible app -> its route (that app only).
5. All accessible apps route inside `/desk` -> `/desk`.
6. Otherwise `/apps`, which is itself rewritten to `/desk` (5.6).

Users can set their own `default_app` to **any installed app**: `set_app_as_default` is whitelisted for any logged-in user and writes `User.default_app` with a plain `db.set_value`, checking only that the app is installed (`apps.py:113-122`). `User.validate` only blanks it if the app is not installed (`user.py:263-264`).

### 5.5 Where `get_default_path()` / `apps_data.default_path` is used

| Caller | Evidence |
|---|---|
| Website User login | `auth.py:200` |
| `GET /login` when logged in | `www/login.py:35,37` |
| Password reset success | `user.py:1074,1076` |
| Social / email-link / token login | `utils/oauth.py:369-370` (`redirect_post_login`) |
| Setup wizard completion | `desk/page/setup_wizard/setup_wizard.js:37,381` |
| Boot (`apps_data.default_path`) | `sessions.py:180-184`, `website/utils.py:182-186` |

### 5.6 `/apps`, `/app` and `/app/*`

`frappe/frappe/hooks.py:68-72`:

```python
website_redirects = [
    {"source": r"/app/(.*)", "target": r"/desk/\1", "forward_query_parameters": True},
    {"source": "/apps", "target": "/desk"},
    {"source": "/app", "target": "/desk"},
]
```

`resolve_redirect` runs before route resolution (`website/path_resolver.py:52`) and walks the merged hook list first, then `Website Settings.route_redirects` (`path_resolver.py:140-165`). `frappe` is always first in installed-app order (`installed_applications.py:131-132`), so its `/apps` rule is matched before any rule added by another app or by Website Settings. Hence a third app cannot repoint `/apps` through hooks. NOT VERIFIED at runtime (matches only by list order).

The website navbar still links to `/apps` when there is more than one non-desk app (`website/js/website.js:633-651`, `templates/includes/navbar/navbar_login.html:18`).

### 5.7 `redirect-to` handling and open-redirect analysis

Sources of `redirect-to`:

| Writer | Evidence |
|---|---|
| `/desk` for a Guest | `www/desk.py:54` (`urlencode({'redirect-to': frappe.request.path})` - path only) |
| Not-permitted page | `website/page_renderers/not_permitted_page.py:19` (`quote_plus(path)`), replaced by plain `/login` for `/desk*` |
| OAuth authorize | `integrations/oauth2.py:111`; Connected App `integrations/doctype/connected_app/connected_app.py:208` |
| Helpdesk SPA guard | `helpdesk-fork/desk/src/router/index.ts:239-244` |

Validation layers:

1. **Server, `sanitize_redirect`** (`www/login.py:206-226`): re-writes `netloc`/`scheme` to the request host/scheme; if the supplied netloc differs from the request host, the path is replaced with `/desk`. So `https://evil.example/x`, `//evil.example/x` and `https://evil.example@host` cannot leave the host. `javascript:...` is neutralised because the scheme/netloc are overwritten, leaving a harmless path. Used by: `GET /login` (`login.py:30`), the OAuth state creation (`login.py:93` -> `get_oauth2_authorize_url` -> `create_oauth_state`, `utils/oauth.py:98-136`), and `sign_up` (`user.py:1237`).
2. **Client, `frappe.utils.sanitise_redirect`** (`public/js/frappe/utils/common.js:327-346`): parses with `new URL(url, location.href)`; returns `""` if the origin differs; preserves absolute/relative shape.
3. **Not validated**: `localStorage["last_visited"]` (5.1); `User Invitation.redirect_to_path` - read with only a leading-`/` strip and passed to `frappe.utils.get_url`, which returns an absolute `http(s)://` input unchanged (`user_invitation.py:199-201`, `core/api/user_invitation.py:166`, `utils/data.py:1972-1973`). Nothing in the files read validates it. The invitation is created by a user with inviter roles, so the risk is a trusted-inviter-controlled redirect, not an anonymous open redirect. NOT VERIFIED at runtime.

Conclusion (FACT-based): the standard `?redirect-to=` login flow is same-origin-only on both the server and the client layers. There is no allow-list: any same-origin path is accepted, including `/desk/...` for a Website User (who is then rejected by `www/desk.py:56`).

### 5.8 Flow C - social login / email link / login token

`redirect_post_login(desk_user, redirect_to, provider)` (`utils/oauth.py:365-373`): redirect URL is the state-stored `redirect_to` if present, otherwise `get_url(desk_uri if desk_user else website_uri)` where `desk_uri = "/desk/workspace" if provider == "facebook" else get_default_path()` and `website_uri = get_default_path() or get_home_page() or "/me"`. `desk_user` is decided from `frappe.local.response["message"] == "Logged In"` (`oauth.py:270`) or `user_type == "System User"` (`www/login.py:130,195`). Note this flow uses `get_default_path()` for System Users - consistent with Flow B and different from Flow A. If `get_default_path()` returns `None`, `frappe.utils.get_url(None)` is called (`oauth.py:371`); resulting behaviour NOT VERIFIED.

### 5.9 Hook points that can change the destination

| Hook / flag | Effect | Evidence |
|---|---|---|
| `frappe.local.flags.home_page` | Wins in `get_home_page` for that request | `website/utils.py:99-100` |
| `get_website_user_home_page` (callable, per user) | Used if no Role/Portal home page matched | `website/utils.py:149-151` |
| `Role.home_page` | First hit in role order | `website/utils.py:107-110` |
| `Portal Settings.default_portal_home` | Applies to all non-Guest users without a role home page | `website/utils.py:112-114` |
| `User.default_workspace` | Overrides everything in `get_home_page` | `website/utils.py:133-136` |
| `User.default_app` / `System Settings.default_app` | `get_default_path` only (Flows B, C, Website-User A) | `apps.py:99-104` |
| `on_login` / `on_session_creation` / `before_login` | Can set flags/cache; cannot overwrite `response["home_page"]` (assigned later) | `auth.py:147,171,241,199-205` |
| `after_request` / `before_request` | Can mutate the response body of `/api/method/login` (not verified) | `app.py:185-186,219-220` |
| `website_redirects` | Page-level rewrite of any path before routing | `path_resolver.py:114-200` |
| `page_renderer` / `website_path_resolver` | Replace or precede the built-in renderers | `path_resolver.py:56-58,69,91-111` |
| Login template JS | Client-side override possible; the Helpdesk fork keeps stock JS (6.x) | `helpdesk-fork/helpdesk/www/login.html:4-9` |

### 5.10 How the Helpdesk login page overrides Frappe's `/login`

- The fork ships `helpdesk-fork/helpdesk/www/login.html` and `login.py` (section 7.5). Both Frappe and the fork contain a `www/login` page for the route `login`.
- Resolution: `TemplatePage.set_template_path` loops over `reversed(frappe.get_installed_apps())` and takes the first match (`website/page_renderers/template_page.py:51-60`), so the **last installed** app that has a `www/login*` wins. With the order frappe, erpnext, telephony, helpdesk (by install order; `frappe` is forced first, `installed_applications.py:131-132`), Helpdesk's page wins; if ERPNext were installed after Helpdesk, ERPNext has no `www/login`, so Helpdesk still wins - but any later app adding `www/login` would displace it. NOT VERIFIED which order the target site has: check `frappe.get_installed_apps()`.
- ERPNext ships no `www/login` (listing of `erpnext/erpnext/www/` shows none).
- The Helpdesk controller imports and calls Frappe's `get_context` (`from frappe.www.login import get_context as frappe_login_context`, `helpdesk-fork/helpdesk/www/login.py:7,26`), so the redirect logic in `www/login.py:25-41` stays in force; the template `{% extends "frappe/www/login.html" %}` (`login.html:9`) keeps Frappe's `login.js` (`frappe/www/login.html:218`). The fork adds branding only (`login.py:28-55`).
- API-level callables (`frappe.www.login.login_via_key`, ...) resolve by dotted path to Frappe's module, unaffected by the www override.
- `/login/helpdesk` risk: the SPA guard builds `LOGIN_PAGE + (redirectURL ? "?redirect-to=/helpdesk" + redirectURL : "/helpdesk")` (`desk/src/router/index.ts:239-244`). When `redirectURL` is empty the target is `/login/helpdesk`, not `/login?redirect-to=/helpdesk`. Whether `/login/helpdesk` resolves is NOT VERIFIED at runtime (ASSUMPTION: it falls to Frappe's 404).

---

## 6. App launcher (the "apps screen")

### 6.1 What exists in v16 (FACT)

- There is **no** `/apps` page: `/apps` is a 301 to `/desk` (5.6).
- The apps screen is the Desk "desktop" Page. `desktop.js:render_app_icons()` builds tiles from `frappe.boot.app_data` (`desktop.js:168-206`), filtering `on_apps_screen`, sorting by `sequence_id`, and computing each tile's link with `frappe.app.sidebar.app_landing_route(app)` (`public/js/frappe/ui/sidebar/sidebar.js:1043-1054`).
- A second, parallel payload `frappe.boot.apps_data` (`apps`, `is_desk_apps`, `default_path`) feeds the website navbar, the setup wizard and redirect logic (`sessions.py:180-184`, `website/utils.py:178-187`).
- `app.py` v16 desk page: `www/desk.py` serves `/desk`; `desk/page/desktop/desktop.py:7-27` redirects Guests to `/app` and renders the page context.
- The default landing page of the Desk root is the Page named by `desktop:home_page` (`workspace` after setup) and falls back to `"desktop"` when that Page is missing or not permitted (`boot.py:444-455`). The exact in-browser behaviour of a bare `/desk` (apps screen vs home shell vs default workspace) is NOT VERIFIED; it depends on `Desktop Settings.desktop_page`, `User.default_workspace` and the client router.

### 6.2 The hook, its keys and its name check (FACT)

Hook name: exactly `add_to_apps_screen`. A list of dicts in each app's `hooks.py`. Keys read by the code:

| Key | Consumers |
|---|---|
| `name` | `apps.get_route` matches `app.get("name") == app_name` (`apps.py:80-81`); must equal the app's module name or `get_route` returns `"/apps"` (`apps.py:81-82`) |
| `title` | `get_apps` (`apps.py:63`), boot `app_title` (`boot.py:~345`) |
| `logo` | `get_apps` (`apps.py:62`), boot `app_logo_url` |
| `route` | tile destination; `app_home` hook is the fallback in boot (`boot.py:~355-362`) |
| `has_permission` | dotted path to a no-arg callable returning truthy (`apps.py:56-57`, `boot.py:298-300`) |
| `sequence_id` | boot sort key; default 100 (`DEFAULT_APP_SEQUENCE_ID`, `boot.py:~208-215`); Framework is 1000 |
| `desk_route` | extra "open in desk" link under a non-desk app's tile (`boot.py:~363-370`, `desktop.js:196-206`) |
| `setup_wizard_text` | the wizard's intro slide (`apps.py:64-68`, `setup_wizard.js:57-61`) |

### 6.3 Two pipelines (FACT)

| Pipeline | Function | Installed apps considered | Setup gating | Frappe tile | Dock/entries | Used by |
|---|---|---|---|---|---|---|
| `apps_data` | `frappe.apps.get_apps` (`apps.py:36-73`, whitelisted + `request_cache`) | all installed apps except `frappe`, every dict in each app's hook list | Skips an app unless it is wizard-complete or wizard-not-required, **or** the user is a System Manager (`apps.py:42-47`) | Skipped (`apps.py:49-50`) | none | website navbar, `get_default_path`, setup wizard |
| `app_data` | `boot.get_app_data` (`boot.py:272-377`) | all installed apps, only `apps[0]` of each hook list (`boot.py:293-294`) | none | Included if permitted | per-app `dock` | the Desk apps screen and sidebar |

In `get_app_data`, a user denied by `has_permission` still gets a stub entry with `on_apps_screen=False`, `app_route=""`, `dock=[]` ("we don't expose its routes or its dock", `boot.py:298-318`). An app that mounts onto another app's dock (`Dock.mount_on`) is removed from the apps screen even if it declares the hook (`boot.py:332-336`, `apps.get_docked_apps`, `dock.mounted_apps` at `dock.py:625-665`). That affects only the mounting app's own tile.

`get_apps` catches errors from `has_permission` callables, logs them, and drops the tile (fail-closed; `apps.py:71-72`).

### 6.4 Where each tile comes from

| Tile label | Declared in | Title / route / logo | `has_permission` | Sequence | Evidence |
|---|---|---|---|---|---|
| **Framework** (Frappe) | `frappe/frappe/hooks.py:579-589` | title "Framework", route `app_home` = `/desk/build`, logo `/assets/frappe/images/frappe-framework-logo.svg` | `frappe.permissions.check_app_permission` = System User **and** System Manager (`permissions.py:962-966`) | 1000 | Appears only in `app_data` (Desk apps screen); never in `get_apps` (`apps.py:49-50`) |
| **ERPNext** | `erpnext/erpnext/hooks.py:13-23` | title = `app_title` "ERPNext", route `/desk/home`, logo `/assets/erpnext/images/erpnext-logo.svg`, `setup_wizard_text` | `erpnext.check_app_permission`: Administrator True; Website User False; **everyone else True** (`erpnext/erpnext/__init__.py:158-165`) - no role check | 1 | |
| **NXERP** (this is the Helpdesk fork's tile) | `helpdesk-fork/helpdesk/hooks.py:12-20` | title "NXERP", route `/helpdesk`, logo `/assets/helpdesk/nxerp_login/images/nxerp-mark.png` | `helpdesk.api.permission.has_app_permission`: Administrator True, or roles intersect {Agent, Agent Manager, System Manager, HD Customer, HD Customer Manager} (`helpdesk-fork/helpdesk/api/permission.py:3-17`) | none (100 default) | |
| Telephony | `telephony/telephony/hooks.py:19-27` | commented out | - | - | no tile |

There is no umbrella "NXERP" app/tile. The label "NXERP" currently names the Helpdesk app only.

Derived visibility (ASSUMPTION built on FACT; role-to-desk_access values NOT VERIFIED):

- A pure ERPNext user (System User, no Helpdesk role): ERPNext tile yes; NXERP (Helpdesk) tile no; Framework only if System Manager.
- A Helpdesk Agent (assumed System User): ERPNext tile **yes** (callable only excludes Website Users), NXERP tile yes.
- An HD Customer (Website User): ERPNext tile no; NXERP tile yes (HD Customer is in the allowed set), no Desk (blocked at `www/desk.py:56`).
- A System Manager: all three tiles.

### 6.5 Merge / override semantics of hooks (FACT)

- `frappe.get_hooks()` builds one dict by iterating installed apps in order and calling `append_hook(hooks, key, value)` for every non-underscore attribute of each app's `hooks.py` (`__init__.py:965-992`).
- `append_hook` (`__init__.py:1020-1038`): non-dict values are turned into lists and **extended**; dict values are merged key-by-key with the same rule applied recursively. No hook value can delete or replace another app's value; later apps append later.
- `frappe.get_hooks(hook, app_name=X)` loads only app X's `hooks.py` (`__init__.py:1007-1008`: `_request_cached_load_app_hooks(app_name)`). Both launcher pipelines use this form, so tile data is strictly per-app: **a third app cannot hide, rename or re-route another app's tile via `add_to_apps_screen`**.
- Installed-app order: `frappe` first, others by install order (`installed_applications.py:109-137`), changeable only through `update_installed_apps_order` (System Manager).
- Singular-value hooks that rely on "last one wins" do so explicitly via `[-1]` (home page hooks, `website/utils.py:149-171`; `signup_form_template`, `www/login.py:56-61`). The merge order therefore equals installed order.
- Practical hide/modify levers (ASSUMPTIONS that follow from the code): (a) the tile's own `has_permission` callable (owned by the tile's app); (b) mutate `bootinfo.app_data` from a `boot_session` hook, which runs after `load_desktop_data` (`boot.py:60` vs `boot.py:99-100`); (c) a `Dock` record that mounts a companion app onto a host (only removes the mounting app's tile, `dock.py:625-665`); (d) `apps_data` is assigned in `sessions.py:180-184` **after** `extend_bootinfo` hooks (`sessions.py:173-174`), so an `extend_bootinfo` hook cannot change it; (e) `override_whitelisted_methods` could redirect the whitelisted `frappe.apps.get_apps` API but boot and redirect code call the function directly, so it would not change the boot payload. None of (b), (d), (e) was exercised; NOT VERIFIED.

### 6.6 Is `/apps` (or the launcher) a permission boundary? (FACT)

No. `has_permission` on a tile is evaluated only to decide whether to **list** the tile (`apps.py:56-57`, `boot.py:298-300`, plus `convert_custom_sidebars.py:130`). Nothing reads it when the app's route is requested:

- `/desk`, `/desk/*`: gated only by `user_type` (`www/desk.py:50-58`).
- `/helpdesk`: `www/helpdesk/index.py` has no user check at all; it boots for Guests too (`get_context_for_dev` is guest-callable but developer-mode only, `index.py:23-27`).
- Both `route`s are plain URLs.

`get_default_path` can even emit a route for an app the user cannot access (5.4 item 3), and `set_app_as_default` lets a user choose any installed app (5.4).

### 6.7 Related launcher helpers

- `get_incomplete_setup_route(current_app, app_route)` returns the route of the first required app whose wizard is incomplete, or `"app"` for frappe (`apps.py:125-145`). `required_apps` comes from `hooks.py` (`helpdesk-fork/helpdesk/hooks.py:9` lists `telephony`).
- `get_docked_apps()` is request-cached (`apps.py:18-28`).
- `is_desk_apps(apps)` - True when every accessible app's route is under `/desk` (`apps.py:84-89`).

---

## 7. Helpdesk layering over Frappe auth

### 7.1 No Frappe-level auth override beyond one hook (FACT)

`helpdesk-fork/helpdesk/hooks.py` defines no `on_login`, `on_session_creation`, `boot_session` or `extend_bootinfo`. Auth-relevant entries:

- `add_to_apps_screen` (hooks.py:12-20).
- `website_route_rules`: `/helpdesk/<path:app_path>` -> `helpdesk` (hooks.py:57-62).
- `auth_hooks = ["helpdesk.auth.authenticate"]` (hooks.py:169).
- `after_install`, `setup_wizard_complete`, `user_invitation` (allowed inviter-to-role map, hooks.py:64-82), `doc_events` for Customer/User Permission/DocShare/Comment/Notification Log, `has_permission`/`permission_query_conditions` for HD DocTypes (part 2), `override_whitelisted_methods` for `frappe.realtime.has_permission`.

### 7.2 `helpdesk.auth.authenticate` (FACT)

`helpdesk-fork/helpdesk/auth.py:72-105`. It is an `auth_hooks` callable (runs in `validate_auth`, `auth.py:746-748`, for every request including website pages):

- Does nothing unless site config `block_endpoints` is truthy (73-74).
- Looks up `User.user_type` for the session user (80).
- System Users are unrestricted (82-83).
- For non-System Users it only restricts paths starting with `/api/`; non-API paths return immediately (85-86).
- Allows paths under `/helpdesk`, `/api/method/helpdesk.*`, `/telephony`, `/api/method/telephony.*`, server-script API endpoints, site-config `allowed_custom_endpoints`, a wildcard list, and a ~60-entry explicit list `ALLOWED_PATHS` (88-103).
- Otherwise `frappe.throw(... PermissionError)` (105).

Scope of the effect (derived): applies to Website Users and Guests alike and only when `block_endpoints` is configured; it is an endpoint deny-list approach on `/api/*`, not a role check. `frappe.client.*` (get, get_list, insert, set_value, delete, ...) appear in `ALLOWED_PATHS` (46-52), so those are not blocked here. Details of what these methods then enforce belong to part 2. Whether `block_endpoints` is set on the target site is NOT VERIFIED.

### 7.3 How Helpdesk decides agent vs customer vs admin (FACT)

`helpdesk-fork/helpdesk/utils.py:35-75` and `api/auth.py:7-78`:

- `is_admin(user)` = `user == "Administrator"` only (`utils.py:35-43`).
- `is_agent(user)`: Administrator -> True; if an `HD Agent` row exists, its `is_active` decides (including False for a deactivated agent who keeps roles); otherwise role `Agent` or `Agent Manager` (`utils.py:46-61`).
- `get_agent_name` = the user if an `HD Agent` record exists (`utils.py:64-75`).
- `helpdesk.api.auth.get_user` returns `has_desk_access = is_agent or is_admin`, where `is_admin` = System Manager or Administrator role (`api/auth.py:27-33`). This "has_desk_access" is the Helpdesk SPA's notion of agent-UI access, not Frappe's `Role.desk_access`.
- Customers are users who are not agents; Helpdesk-specific customer roles are `HD Customer` and `HD Customer Manager` (`install.py:217`).
- `@agent_only` decorators protect agent endpoints (`utils.py:181-195`).

### 7.4 `/helpdesk` page and SPA behaviour

- `/helpdesk` resolves via `website_route_rules` to the page `helpdesk` -> `helpdesk/www/helpdesk/index.html` (a **build artifact**, gitignored: `helpdesk-fork/.gitignore:43`; written by the Vite plugin, `desk/vite.config.js:28`) plus controller `helpdesk/www/helpdesk/index.py`.
- `index.py` makes no authentication decision: it returns a boot dict with `default_route = "/helpdesk"`, `session_user`, `setup_complete`, `agent` (HD Agent name or None) and the installed app list (`index.py:30-54`).
- The SPA router uses `createWebHistory("/helpdesk/")` (`router/index.ts:225`). The `beforeEach` guard (`router/index.ts:229-253`):
  1. `authStore.isLoggedIn` is derived from the `user_id` cookie (not httponly; "Guest" -> null) (`stores/auth.ts:64-73`).
  2. Not logged in: `window.location.href = "/login" + (redirectURL ? "?redirect-to=/helpdesk" + redirectURL : "/helpdesk")` (see 5.10 for the empty-path quirk).
  3. Logged in: fetches `helpdesk.api.auth.get_user`.
  4. Non-agent opening an agent ticket -> redirected to the customer ticket route.
  5. Route not `public` and user lacks agent/admin desk access -> `TicketsCustomer`.
- The route table: agent routes (`/home`, `/tickets`, `/contacts`, `/agents`, `/teams`, `/dashboard`, `/call-logs`...) and customer routes marked `meta.public` (`/my-tickets`, `/my-tickets/new`, `/kb-public/...`) (`router/index.ts:136-205`).
- `PortalRoot.vue` picks the shell from the session: agent shell if `hasDeskAccess && isAgent`, else the customer shell (`roots/PortalRoot.vue`).
- Consequence (FACT-based): the SPA does not require a Helpdesk role; any logged-in user, including an ERPNext-only System User, gets the SPA shell and falls into the **customer** view. The SPA guard is a UI convenience; the server's DocType permissions (part 2) are what protect data. The Helpdesk persona/onboarding interrupt applies only to `is_admin` desk users (`desk/src/persona.ts:41-50`).
- For Guests the same page HTML is served (there is no server redirect); the redirect to login happens in the browser after the bundle loads.

### 7.5 Fork's customised login (FACT)

- `www/login.html` extends `frappe/www/login.html` (`login.html:9`) and only changes layout/branding; the file header says "every form, field id, handler and script (login, forgot password, email link, 2FA, social login, redirect-to) is still the framework's code" (`login.html:3-8`).
- `www/login.py` calls Frappe's `get_context` first, then layers branding, forces `login_with_email_link = 0` and, unless `SHOW_SOCIAL_LOGIN`, empties `provider_logins` (`login.py:22-55`). It writes nothing to the database (docstring `login.py:23-25`).
- Therefore the fork changes neither redirect logic nor session handling. It also does not hide backend routes for email-link/social login (7.2).

### 7.6 Portal defaults that Helpdesk installs and what they do to non-Helpdesk users (FACT + derived)

On a fresh install (`install.py:29,216-250`):

- `Role "HD Customer"` and `"HD Customer Manager"`: `home_page = "/helpdesk"`, `desk_access = 0`.
- `Portal Settings.default_role = "HD Customer"`: **every self-signup** (`sign_up`, `user.py:1231-1233`) and every Social-Login auto-created user is not given this; the sign-up path is the one that applies `default_role`. So self-signup users become HD Customers (Website Users).
- `Portal Settings.default_portal_home = "/helpdesk"`: per `get_home_page` step 2 (5.2), this applies to **every** non-Guest user who lacks a `Role.home_page`, including ERPNext System Users and Administrator. Because `get_home_page()` is what Flow A uses for System Users (`auth.py:205`), an ERPNext-only System User with no role home page and no default workspace is sent to `/helpdesk` after login. Administrator's role list includes `HD Customer`, so step 1 may also pick `/helpdesk`. Which of the two fires first is not determined by the code. NOT VERIFIED at runtime; this is the highest-impact item to confirm (Section 11, item V2).
- The upgrade patches only fill empty values (`helpdesk/patches/set_default_portal_settings.py`).

---

## 8. ERPNext, portal and website users

### 8.1 ERPNext's own auth/session hooks (FACT)

`erpnext/erpnext/hooks.py`:

- `on_session_creation = "erpnext.portal.utils.create_customer_or_supplier"` (line 106; runs at `auth.py:241` for every non-resume session creation). For Website Users only, when `Portal Settings.default_role` is Customer or Supplier and the user holds that role, it auto-creates a Customer/Supplier party, and a Contact linked to it (`erpnext/erpnext/portal/utils.py:22-96`). With Helpdesk's `default_role = "HD Customer"` (7.6) this function returns early (`portal/utils.py:35-36`) - no ERPNext Customer is created on login.
- `boot_session = erpnext.startup.boot.boot_session` and `extend_bootinfo` (lines 100, 706-709) - Desk boot extras only (`startup/boot.py:13-76`).
- `doc_events["User"]`: `on_update = erpnext.portal.utils.set_default_role` (line 394) - adds the `Customer`/`Supplier` role to a User whose email matches a Contact linked to such a party (`portal/utils.py:4-19`).
- `doc_events["User"]["validate"] = erpnext.setup.doctype.employee.employee.validate_employee_role` (line 393).
- No `on_login`, no `auth_hooks`, no `website_user_home_page`/`role_home_page`/`home_page` hook (grep of `erpnext/erpnext/hooks.py`).
- Tile permission `erpnext.check_app_permission` (6.4).

### 8.2 Portal mechanics in Frappe (FACT)

- Roles `Customer` / `Supplier` are created by Portal Settings sync with `desk_access = 0` (`portal_settings.py:62-66`) from the `standard_portal_menu_items` hook (ERPNext defines the menu entries and their roles, `erpnext/erpnext/hooks.py:259-330`).
- A user is a "portal user" if `user_type == "Website User"` and holds a role listed in the Portal menu (`utils/user.py:464-479`).
- `get_home_page` converts `me` to `portal` for portal users (`website/utils.py:130-131`).
- Portal menu per user: `get_portal_sidebar_items` (`website/utils.py:464-491`) filters Portal Settings `menu` + `custom_menu` + `portal_menu_items` hook items by role and enabled flag, cached in the Redis hash `portal_menu_items` per user. `hide_standard_menu` hides the standard group.
- `/me` (`www/me.py`): any logged-in user; the footer shows `/portal` for portal users, `/desk` for others (`www/me.html:78-90`).
- `/portal` (`www/portal.py`): list page for a doctype passed in the form; Guests are rejected unless the meta has `allow_guest_to_view` (`portal.py:36-37`); the list itself uses website list permissions (`get_list_context`, part 2).
- `/update-password`, `/update-profile`, `/third_party_apps`, `/request-for-account-deletion` are linked from `/me` (`www/me.html:33-65`).
- NOT FOUND: `/tickets` as a Frappe or ERPNext www route. Helpdesk's customer tickets live in the SPA at `/helpdesk/my-tickets` (7.4). ERPNext's `Issue` has a website permission hook (`erpnext/erpnext/hooks.py:344`), and `erpnext/www/support` exists, but neither was traced.
- ERPNext website portal routes (`/orders`, `/invoices`, `/quotations`, `/purchase-orders`, `/rfq`, `/project`, ... ) are declared through `website_route_rules` (`erpnext/erpnext/hooks.py:148-250`) and gated by `has_website_permission` per doctype (`hooks.py:335-346`, implemented in `erpnext/controllers/website_list_for_contact.py`).

### 8.3 What a Website User (customer) can reach (FACT-based inventory)

| Surface | Reachable? | Evidence |
|---|---|---|
| `/desk`, `/desk/*` | No (PermissionError) | `www/desk.py:56-58` |
| `/apps`, `/app` | Redirect to `/desk`, then denied | `hooks.py:69-71` |
| `/me`, `/update-password`, `/portal`, `/login`, `/logout` | Yes | `www/me.py`, `www/portal.py` |
| ERPNext portal list/detail pages | Subject to `has_website_permission` / portal roles | `erpnext/erpnext/hooks.py:335-346` |
| `/helpdesk` SPA | Yes (page is public); customer routes meta `public` | `index.py`, `router/index.ts:136-205` |
| `/api/method/*` whitelisted functions | Subject to `@frappe.whitelist` and per-function checks; Helpdesk may restrict when `block_endpoints` is set | `handler.py:83-84`, `helpdesk-fork/helpdesk/auth.py:72-105` |
| `/api/resource/*` | Subject to DocType permissions (part 2); NOT blocked by the apps screen or `block_modules` | 4.4, 6.6 |
| Launcher tiles | NXERP (Helpdesk) tile only | 6.4 |

---

## 9. Cross-cutting gotchas

1. **Two redirect engines.** Fresh login (Flow A) uses `get_home_page()` for System Users; every other post-login flow uses `get_default_path()` (5.1, 5.3, 5.8).
2. **`default_portal_home` is global.** Helpdesk's install writes `Portal Settings.default_portal_home = "/helpdesk"`, and `get_home_page` applies it to every non-Guest user lacking a role home page (5.2, 7.6).
3. **Launcher is UI only.** Tile `has_permission` hides tiles; it neither blocks the route nor feeds the default path (6.6, 5.4).
4. **Default app is not permission-checked** and is user-settable to any installed app (5.4).
5. **`ERPNext` tile visibility is "any System User".** There is no ERPNext-role check in `erpnext.check_app_permission` (6.4).
6. **`frappe.is_setup_complete()` ignores Helpdesk** and every app other than frappe/erpnext (2.2); only wizard-complete apps are visible to non-System-Managers (`apps.py:42-47`).
7. **Setup redirect is client-side.** A server-side redirect that bypasses `/desk` bypasses the wizard redirect (2.3).
8. **`get_home_page` cache.** Per-user Redis hash `home_page`; role/portal/home-page configuration changes require cache clearing for existing users (5.2).
9. **`user_type` snapshot in session** (1.4) - bounded by session clearing on user-type change (`user.py:368-369`).
10. **Role Profiles overwrite manual roles** (4.1) and propagate asynchronously (`role_profile.py:30-35`).
11. **`block_modules` is navigation only** by explicit design (4.4).
12. **`desk_access` default for implicitly created roles is 1** (3.1); a role created only through DocType permission rows turns its holders into System Users.
13. **2FA is bypassed by non-password login routes** (1.8, 1.10).
14. **Relative redirect values.** `get_home_page()` returns paths without a leading slash (5.2); consumers resolve them relative to `/login`.
15. **Hooks merge, never override** (6.5); "last wins" exists only where code indexes `[-1]`.
16. **/login override depends on installed-app order** (5.10).
17. **SPA login redirect quirk** `/login/helpdesk` (5.10).
18. **`Home Settings`** is a legacy hidden field, not a routing mechanism (0).

---

## 10. Implications for NXERP

Facts on the left; implication for the NXERP requirements (one login, authorised-only launcher, direct landing on `/helpdesk/home` for Helpdesk-only users, restricted customer portal, server-side enforcement). These are consequences, not design.

| # | Fact (evidence) | Implication |
|---|---|---|
| I1 | `/apps` is only a redirect to `/desk`; the launcher is the Desk "desktop" Page fed by `boot.app_data` (`hooks.py:70`, `desktop.js:168-206`). | A launcher that is reachable by Helpdesk-only users must live outside `/desk`, or the post-login logic must avoid sending them there; `/desk` is closed to Website Users and open to every System User. |
| I2 | Fresh login for System Users uses `get_home_page()`, not `get_default_path()` (`auth.py:205`); all other flows use `get_default_path()` (`www/login.py:37`, `oauth.py:369`). | Landing rules must be implemented in (or compatible with) both engines, or logins from different entry points will disagree. |
| I3 | `get_home_page()` order: flag > role home page > Portal default home > hooks > Website Settings > `me`; `default_workspace` overrides all (`website/utils.py:98-137`); result cached per user. | A deterministic per-user landing needs a single owner of this chain, plus cache invalidation when grants change. The flag `frappe.local.flags.home_page` is the only per-request override that survives `set_user_info`. |
| I4 | Helpdesk install sets `Portal Settings.default_portal_home = "/helpdesk"` and `default_role = "HD Customer"` (`install.py:240`). | Without intervention, ERPNext-only System Users may be routed to `/helpdesk` and every self-signup becomes an HD Customer. These two settings must be consciously owned in an umbrella deployment. |
| I5 | `erpnext.check_app_permission` = any non-Website user (`erpnext/__init__.py:158-165`); Frappe tile = System Manager; Helpdesk tile = role set (`permission.py:3-17`). | "Only apps the user is authorised for" is not true of the ERPNext tile out of the box; changing it requires editing the callable (upstream code), wrapping it, or post-filtering `boot.app_data` in a `boot_session` hook. |
| I6 | Tile data is read per app with `get_hooks(..., app_name=app)`; hooks only append (`__init__.py:1007-1038`). | A third "NXERP" app cannot hide, rename or re-route other apps' tiles through hooks; it can only add its own tile or post-process boot payloads. |
| I7 | Tile `has_permission` is evaluated only to list tiles; routes `/desk`, `/helpdesk` are not gated by it (`www/desk.py:50-58`, `helpdesk/www/helpdesk/index.py`). | The launcher cannot be the authorisation layer. Enforcement must be at DocType/API level (part 2) and, for whole-app access, in code paths the apps themselves control. |
| I8 | `default_app` (user and system) is not permission-checked in `get_route`; users may set any installed app (`apps.py:76-82,113-122`). | If default-app is used, add a permission check or restrict who may set it. |
| I9 | `block_modules` is explicitly navigation-only (`utils/modules.py:45-58`). | Module Profiles cannot be the mechanism that separates ERPNext data from Helpdesk users. |
| I10 | `www/desk.py` allows any non-Website user; `desk_access` is evaluated only at User save and Role change (`user.py:444-445`, `role.py:74-84`). | A Helpdesk Agent with `desk_access = 1` roles is a System User who can open `/desk` and sees the ERPNext tile. To keep Helpdesk-only staff out of Desk, their roles must have `desk_access = 0` (note implicitly created roles default to 1, `doctype.py:2030`). Whether Agent roles are 0 or 1 is NOT VERIFIED. |
| I11 | `frappe.is_setup_complete()` looks at frappe and erpnext only; the wizard redirect is performed by the Desk SPA (`__init__.py:1549`, `router.js:180-185`). | Direct landing on `/helpdesk/home` skips the wizard redirect; first-run Administrator handling must be explicit (for example always send an incomplete-setup Administrator to `/desk`). ERPNext and Helpdesk readiness are tracked separately (`HD Settings.setup_complete`). |
| I12 | The Helpdesk SPA admits any logged-in user and drops non-agents into the customer view (`router/index.ts:229-253`, `stores/auth.ts`). | "Helpdesk-only users land on /helpdesk/home" is a SPA/route decision; the SPA will also happily host an ERPNext-only user as a customer, so server-side checks on Helpdesk data remain essential. |
| I13 | `/login` is overridden by the last installed app that ships `www/login` (`template_page.py:51`); the fork's login reuses Frappe's `get_context` and JS (`login.py:26`, `login.html:9`). | The single `/login` is already satisfied; redirect logic is Frappe's. Any later app adding `www/login` would silently replace it; installed-app order should be fixed and checked. |
| I14 | `?redirect-to=` is same-origin-only on server and client (`www/login.py:206-226`, `common.js:327-346`) but takes precedence over `home_page` for System Users (`login.js:327`). | Launcher/landing logic cannot rely on server `home_page` alone when the user arrives with `redirect-to` (for example from the Helpdesk SPA). Inputs outside this layer (`last_visited`, invitation `redirect_to_path`) are unvalidated. |
| I15 | 2FA runs only in the password and LDAP flows (`auth.py:156`, `ldap_settings.py:413`); social, email-link, invitation and reset flows call `login_as` directly. | If 2FA is a requirement, disable or gate the other routes (the fork hides the social UI but the endpoints remain, `login.py:52-54`, `auth.py:20-31`). |
| I16 | API key / bearer auth does not create sessions or run login hooks (`auth.py:625-648`); `auth_hooks` runs for every request (`auth.py:746-748`); Helpdesk's hook is a no-op unless `block_endpoints` is configured (`helpdesk/auth.py:73-74`). | Machine access follows different rules from UI login; any "one login" policy has to state how API users are handled. |
| I17 | Social-login and sign-up create Website Users; sign-up assigns `Portal Settings.default_role` (`oauth.py:304`, `user.py:1224-1233`). | Customer self-registration will produce portal users without an ERPNext party. ERPNext's `create_customer_or_supplier` only acts if `default_role` is Customer/Supplier (`portal/utils.py:35`). |
| I18 | Role Profiles overwrite manual roles and apply asynchronously (`user.py:276-291`, `role_profile.py:30-35`). | Grants should be expressed through one mechanism; mixing manual roles and profiles loses manual grants. |
| I19 | `frappe.get_roles(Administrator)` returns every role, and Administrator is special-cased in app callables (`permissions.py:551`, `permission.py:14`, `__init__.py:159`). | Administrator sees every tile and passes every callable: it is not a valid test account for "only authorised apps". |

---

## 11. Runtime verification checklist

Assumes a site `<site>` in a bench and the stack reachable at `http://localhost:8100` (adjust). Use a throwaway test site. Do not paste real credentials into shared logs.

**V1 - installed app order and versions (affects 5.10, 6.5)**

```
bench --site <site> console
>>> frappe.get_installed_apps()
>>> frappe.utils.get_installed_apps_info()
```

**V2 - default landing for each user class (affects 5.2, 7.6; highest impact)**

Create test users: `erp_only` (System User, roles: ERPNext roles only), `hd_agent` (Agent), `hd_cust` (HD Customer, Website User), `sysmgr` (System Manager). In console:

```
>>> frappe.set_user("erp_only"); from frappe.website.utils import get_home_page; get_home_page()
>>> from frappe.apps import get_apps, get_default_path; get_apps(); get_default_path()
```

Repeat per user. Also check config: `frappe.db.get_single_value("Portal Settings","default_portal_home")`, `frappe.db.get_value("Role","HD Customer","home_page")`, `frappe.db.get_value("Role","HD Customer","desk_access")`, and the same two fields for `Agent` and `Agent Manager`.

**V3 - actual login response**

```
curl -i -c jar.txt -X POST http://localhost:8100/api/method/login -d "usr=<user>" -d "pwd=<password>"
```

Inspect JSON `message` and `home_page`; check `Set-Cookie` flags (`sid` HttpOnly, SameSite). Repeat for each class in V2 to confirm Flow A uses `get_home_page` (System User) vs `get_default_path` (Website User).

**V4 - already-logged-in `/login` (Flow B)**

```
curl -i -b jar.txt http://localhost:8100/login
```

Expect a 3xx with `Location`; compare with V3 `home_page` for the same user.

**V5 - `/apps`, `/app`, `/desk`**

```
curl -i http://localhost:8100/apps
curl -i http://localhost:8100/app
curl -i http://localhost:8100/desk
curl -i -b jar_website_user.txt http://localhost:8100/desk
```

Expect 301 to `/desk`; Guest `/desk` -> redirect/403 to `/login?redirect-to=%2Fdesk`; Website User `/desk` -> permission error.

**V6 - `redirect-to` validation**

```
curl -i -b jar.txt "http://localhost:8100/login?redirect-to=https://evil.example/x"
curl -i -b jar.txt "http://localhost:8100/login?redirect-to=//evil.example/x"
curl -i -b jar.txt "http://localhost:8100/login?redirect-to=/helpdesk/home"
```

Expect the first two to resolve to `/desk` on the same host.

**V7 - launcher tiles per user**

```
>>> frappe.set_user("<user>")
>>> from frappe.boot import get_app_data; [(a["app_name"],a["on_apps_screen"]) for a in get_app_data()]
>>> from frappe.apps import get_apps; [a["name"] for a in get_apps()]
```

Browser check of `/desk` for the apps screen layout and tile routes (`frappe.boot.app_data` in devtools).

**V8 - setup state (affects Section 2)**

```
>>> frappe.is_setup_complete()
>>> frappe.get_all("Installed Application", fields=["app_name","has_setup_wizard","is_setup_complete"])
>>> frappe.db.get_default("desktop:home_page")
>>> frappe.db.get_single_value("HD Settings","setup_complete")
```

Then, on a freshly created site before the wizard: log in as Administrator, GET `/desk` and `/helpdesk`; observe whether the browser reaches `setup-wizard`.

**V9 - default app misroute (5.4 item 3)**

```
>>> frappe.db.set_single_value("System Settings","default_app","erpnext")
>>> frappe.set_user("hd_cust"); from frappe.apps import get_default_path; get_default_path()
```

Expect `/desk/home` if the analysis holds; restore the setting afterward.

**V10 - 2FA bypass routes (1.8, 1.10)**

Enable 2FA for a role, then attempt login by social provider, email link and invitation accept for a user holding that role; observe whether a second factor is requested.

**V11 - desk_access of Helpdesk roles (3.1, I10)**

```
>>> frappe.get_all("Role", filters={"name":["in",["Agent","Agent Manager","HD Customer","HD Customer Manager"]]}, fields=["name","desk_access","home_page"])
```

**V12 - hook merge / tile override (6.5)**

```
>>> frappe.get_hooks("add_to_apps_screen")
>>> frappe.get_hooks("add_to_apps_screen", app_name="helpdesk")
>>> frappe.get_hooks("website_redirects")
```

**V13 - /login override and SPA redirect quirk (5.10)**

```
curl -s http://localhost:8100/login | grep -i "nx-shell"
curl -i http://localhost:8100/login/helpdesk
curl -i http://localhost:8100/helpdesk
```

First: confirms the Helpdesk template is served. Second: the empty-path URL built by the SPA guard. Third: shows that `/helpdesk` is served to Guests (redirect to login happens client-side).

**V14 - Website User login finishing (5.1)**

Browser test with a Website User that arrives with `?redirect-to=/helpdesk/home` and with a stored `last_visited`; record which URL the browser ends on.

**V15 - `block_endpoints` (7.2)**

```
>>> frappe.conf.get("block_endpoints")
>>> frappe.conf.get("allowed_custom_endpoints")
```

Then as a Website User: `curl -b jar_website_user.txt http://localhost:8100/api/method/frappe.desk.form.load.getdoc?...` and note which endpoints are denied.

---

## Appendix - key files by topic

| Topic | Files |
|---|---|
| Login, sessions, API auth | `frappe/frappe/auth.py`, `frappe/frappe/sessions.py`, `frappe/frappe/app.py`, `frappe/frappe/handler.py` |
| Login page | `frappe/frappe/www/login.py`, `frappe/frappe/www/login.html`, `frappe/frappe/templates/includes/login/login.js`, `helpdesk-fork/helpdesk/www/login.py`, `helpdesk-fork/helpdesk/www/login.html` |
| Social/LDAP/OAuth | `frappe/frappe/utils/oauth.py`, `frappe/frappe/integrations/oauth2.py`, `.../oauth2_logins.py`, `.../doctype/ldap_settings/ldap_settings.py` |
| 2FA | `frappe/frappe/twofactor.py` |
| User model | `frappe/frappe/core/doctype/user/user.py`, `.../role/role.py`, `.../role_profile/`, `.../module_profile/`, `.../user_type/`, `.../user_invitation/` |
| Home page | `frappe/frappe/website/utils.py`, `frappe/frappe/website/path_resolver.py`, `.../page_renderers/template_page.py` |
| Launcher | `frappe/frappe/apps.py`, `frappe/frappe/boot.py`, `frappe/frappe/desk/page/desktop/`, `frappe/frappe/public/js/frappe/ui/sidebar/sidebar.js`, `frappe/frappe/hooks.py`, `erpnext/erpnext/hooks.py`, `helpdesk-fork/helpdesk/hooks.py` |
| Setup | `frappe/frappe/desk/page/setup_wizard/`, `frappe/frappe/utils/install.py`, `frappe/frappe/core/doctype/installed_applications/installed_applications.py`, `helpdesk-fork/helpdesk/setup/` |
| Helpdesk SPA | `helpdesk-fork/desk/src/router/index.ts`, `.../stores/auth.ts`, `.../roots/PortalRoot.vue`, `helpdesk-fork/helpdesk/www/helpdesk/index.py`, `helpdesk-fork/helpdesk/api/auth.py`, `.../api/permission.py`, `.../auth.py`, `.../utils.py` |
| Portal | `frappe/frappe/website/doctype/portal_settings/`, `frappe/frappe/www/me.py`, `frappe/frappe/www/portal.py`, `erpnext/erpnext/portal/utils.py` |
