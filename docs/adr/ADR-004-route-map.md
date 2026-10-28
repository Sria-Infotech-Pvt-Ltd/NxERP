# ADR-004: Route map, ownership and redirect safety

- **Status:** Accepted
- **Date:** 2026-10-27
- **Evidence:** `docs/research/frappe-access-and-routing.md` (static, pinned source) and runtime probes on the Phase 1 dev site (`docs/audit/bootstrap-evidence.md`).

## Context

The brief names `/login`, a launcher, a post-login router, `/helpdesk/home`, ERPNext at `/app...`, a no-access page and logout. Facts that shape the map:

- **FACT (runtime)** `GET /login` returns 200 and serves the NXERP login (the fork's `www/login.*`, which wins because Frappe's template resolver iterates installed apps in reverse: `frappe/website/page_renderers/template_page.py:50-66`). `GET /v1/login` and `/api/v1/login` return **404**: the brief's "v1/login" does not exist in Frappe 16. `/login` is canonical (open question 1).
- **FACT (runtime)** In Frappe 16, `/app` and `/apps` are 301-redirects to `/desk` (`/app/home` to `/desk/home`, `/app/sales-invoice` to `/desk/sales-invoice`). The ERPNext Desk is therefore canonically `/desk`, not `/app`; `/app/...` keeps working as a redirect. There is no `/apps` page: the launcher in v16 is the Desk "desktop" screen fed by `boot.app_data` (`frappe/hooks.py:70`).
- **FACT (runtime)** `/desk` returns 200 for any System User (agent, manager, ERP user) and 403 for a Website User (customer). `/helpdesk/home` returns 200 for **every** logged-in user and the Helpdesk SPA shell is served to guests (`/helpdesk` 200): the SPA decides what to show after load.
- **FACT (runtime)** Every login, including an ERP-only user, receives `home_page: "helpdesk"` today, because Helpdesk's install sets `Portal Settings.default_portal_home = "/helpdesk"` (research part 1, section 5.2/7.6). Frappe has two redirect engines (fresh `/api/method/login` uses `get_home_page()`; every other flow uses `get_default_path()`), so one account can land differently depending on how it signed in.
- **FACT (runtime)** A guest who lands on a Helpdesk path with an empty redirect is sent to `/login/helpdesk`, which is a **404** (SPA router bug, `helpdesk/desk/src/router/index.ts:239-244`).

## Decision

| Purpose | Canonical URL | Owner | Notes |
| --- | --- | --- | --- |
| Login (the only one) | `/login` | `nxerp` (`www/login.*`, moved from Helpdesk in Phase 2) | Frappe authentication underneath; `nxerp` must be the **last** installed app so its page wins, enforced by `deploy/check_pins.py` and a test |
| Post-login router | `/nxerp/go` | `nxerp` | Single server-side decision: launcher, direct app, no-access. Every Frappe redirect engine is pointed at it so both converge |
| Launcher | `/nxerp/apps` | `nxerp` | Outside `/desk`, so Helpdesk-only users and Website Users can be served without Desk access |
| No access | `/nxerp/no-access` | `nxerp` | Plain explanation, no app data |
| Helpdesk | `/helpdesk/home` (SPA under `/helpdesk/*`) | Helpdesk | Helpdesk-only users land here directly |
| ERPNext | `/desk` (`/app/*` kept as redirect) | Frappe/ERPNext | Never moved or renamed |
| Logout | `/logout` page and `POST /api/method/logout`, then `/login` | Frappe | Not overridden |
| Customer portal | The Helpdesk customer view and website portal pages | Helpdesk / Frappe | Customers never get `/desk` (already 403 for Website Users) |

The `/nxerp/*` prefix is reserved for the platform app (ADR-005).

**Redirect-safety rules** (apply to every redirect the platform issues):

1. Targets are **site-relative paths only**; never a scheme, host or `//`. Reuse Frappe's `sanitize_redirect` (`frappe/www/login.py:206-226`); do not write a second validator.
2. `redirect-to` is honoured only if the target is under a mounted app route **and** the user is authorised for that app (the router re-checks); otherwise the router's own decision wins.
3. Never trust `localStorage["last_visited"]` or a User Invitation `redirect_to_path`: both are unvalidated in Frappe today (research part 1, finding 8).
4. A cached landing path is invalidated when roles or grants change (Frappe caches `home_page` per user).
5. Incomplete first-time setup: Administrator is routed to `/desk` (wizard redirect is client-side in the Desk router only, so a direct landing on `/helpdesk/home` would skip it).

## What this does not do

- Landing/launcher decisions are routing and visibility, **not security**. `/desk` and `/helpdesk` remain reachable by direct URL; enforcement is ADR-003's server-side layer.
- The Phase 2 mechanism for converging both redirect engines (flag `frappe.local.flags.home_page` set in `on_session_creation`, versus configuring `Portal Settings`/role home pages) is a **design to be proven in Phase 2** with tests; this ADR fixes the URLs and the rules, not the hook.
- `/login/helpdesk` 404 is an upstream-fork bug to fix in Phase 2 (or removed with the Helpdesk login).

## Consequences

Open question for the owner: confirm `/login` as canonical (the brief also wrote "v1/login").
