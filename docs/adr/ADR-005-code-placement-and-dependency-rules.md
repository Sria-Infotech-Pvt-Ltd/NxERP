# ADR-005: Where branding, login and launcher code lives; app dependency rules

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

- **FACT** Today the login page, NXERP assets and branding live inside the Helpdesk fork: `helpdesk/www/login.{html,py}`, `helpdesk/public/nxerp_login/*`, `helpdesk/nxerp_branding.py`, and the Helpdesk `app_title` is "NXERP" (`helpdesk/hooks.py:2`). At runtime Frappe lists the Helpdesk app as title "NXERP" and the platform app as "NXERP" too (`frappe.utils.change_log.get_versions`). That contradicts "Helpdesk is never NXERP" and would show two tiles with the same name.
- **FACT** A separate local `NXERP/nxerp` app (never committed) contains another login override (`nxerp/www/login.*`, `branding.py`). Two apps overriding `/login` resolve by install order (last wins), which is fragile.
- **FACT** Hooks only append, and tile data is read per app (`get_hooks(..., app_name=X)`): a third app cannot hide or re-route another app's tile through hooks (research part 1, I6).
- **FACT** The fork's login diff against upstream is 64 files / +831 -64 (audit), and cherry-picks cleanly onto `v1.31.0` (ADR-002).

## Decision

1. **Platform app (`nxerp`) owns everything shared:** `/login`, the post-login router, the launcher, the no-access page, platform branding (NXERP logo, palette tokens for shared pages), and the access resolver (ADR-003). In Phase 2 the login moves from the Helpdesk fork into `nxerp/www/login.*`; the Helpdesk fork then keeps only Helpdesk-specific branding.
2. **Per-app code stays in the app:** Helpdesk SPA theming and Helpdesk screens belong to Helpdesk; ERPNext is never customised from `nxerp` except through supported hooks.
3. **Naming:** the Helpdesk app title becomes "Helpdesk"; "NXERP" is reserved for the platform. This is a Phase 2 change to the fork (`app_title`, `add_to_apps_screen`, and `nxerp_branding.apply_branding()`, which rewrites site-wide settings and must not run implicitly).
4. **Dependency rules (architecture rules):**
   - `nxerp` never imports `erpnext`, `helpdesk`, `hrms` or any future app, and declares no `required_apps`.
   - Apps never import `nxerp` or each other.
   - Cross-app facts flow through Frappe's own channels: hooks (`add_to_apps_screen`, a future declared registry hook), roles and permissions in the database, and public HTTP/whitelisted APIs, never Python imports.
   - A new app is added by a pin in `deploy/apps.json` plus a registration, not by editing platform code.
5. **Enforcement of the rules:** `tools/check_architecture.py` (run in CI and pre-commit) fails if `nxerp/` imports another app or declares `required_apps`. `nxerp` must be the last entry in `deploy/apps.json` so that its `www/login` wins and its hooks run after the apps it resolves.

## Alternatives considered

- Keep login in Helpdesk: rejected (couples platform identity to one app; breaks if Helpdesk is absent or reordered).
- Put the launcher in `/desk`: rejected (ADR-004: Desk is closed to Website Users and open to every System User).
- Patch upstream ERPNext tiles: rejected (vendoring/forking ERPNext contradicts ADR-001); filter in the platform instead.

## Consequences

- The Helpdesk fork's diff shrinks over time toward Helpdesk-only branding.
- The ERPNext tile out of the box is visible to any System User (`erpnext/__init__.py:158-165`); filtering it is the platform's job in Phase 2.
