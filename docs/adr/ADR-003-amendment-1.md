# ADR-003 amendment 1: refinements found while implementing Phase 2

- **Status:** Accepted
- **Date:** 2026-10-27
- **Amends:** ADR-003 (access model). The decision (option D, roles as the source of truth, a thin resolver and a
  server-side gate) is unchanged and implemented as written. Nothing here contradicts it; these are details the
  implementation had to settle. Stated here so the ADR stays the source of truth.

## A1. The registry lives in `nxerp`, not in each app's hooks

ADR-003 point 3 / ADR-005 described apps declaring themselves through hooks. Phase 2 uses a declarative registry
(`nxerp/registry.py`) holding strings only. Reasons: the brief asks for one registry in `nxerp`; hooks only append, so
an app could not be hidden or corrected centrally; and a single list is what the tests and the launcher read.
Dependency direction is unchanged: the registry never imports an app, and apps never import `nxerp`.
A hook-based extension point can be added later without changing the resolver.

## A2. Implied roles (`AppEntry.implied_roles`)

An app may declare existing roles that also confer staff access. Helpdesk: `Agent`, `Agent Manager`. Reason: Helpdesk's
own "Invite agents" flow lets an Agent Manager (not a System Manager) create agents; without implied roles every
invited agent would be locked out until a System Manager also granted `NXERP Access: Helpdesk`. ERPNext declares none:
its dozens of business roles do not mean "uses ERPNext" and are never treated as a grant (test
`test_erpnext_business_roles_alone_do_not_grant_the_app`). Consequence: revoking Helpdesk through the API also removes
the implied roles; assigning an implied role is governed by the app's own rules, not by the NXERP grant guard
(accepted, documented in docs/security/phase2-review.md).

## A3. Portal roles are not staff access

Customer-facing surfaces (`AppEntry.portal_roles`) let website users reach the app's API and records (Helpdesk:
`HD Customer*`; ERPNext keeps `Customer`/`Supplier`, preserving its website-user model) but never appear in the
launcher, never open Desk, and are held to extra data minimisation. A Website User never holds staff access, even if an
access role is assigned by mistake (`test_a_website_user_never_holds_staff_access_even_if_granted`).

## A4. System Managers keep the Desk shell, not the data

ADR-003 said System Managers are not auto-granted apps. The brief also says platform administrators must never be
locked out. Resolution: a platform administrator (Administrator, or an enabled System User with `System Manager`) may
open the `/desk` shell to administer users and grants without holding ERPNext (`AppEntry.admin_shell`), and always
passes the shared set. Owned records (Customers, Sales Invoices, ...) still require the ERPNext grant: a System Manager
without it is refused on `/api/resource/Customer`, files, reports and realtime (matrix row `sysmgr`).

## A5. No cache of our own

ADR-003 left caching open. The resolver keeps none: every answer derives from `frappe.get_roles`, which Frappe caches
and clears on every User save. Revocation is therefore effective on the next request, including on a live session
(`test_revocation_applies_to_a_live_session_without_relogin`). If roles are changed by raw SQL the delay is Frappe's
own role-cache lifetime until `frappe.clear_cache(user=...)`.

## A6. Findings that tightened the model (all with tests)

1. **Disabled accounts.** Frappe checks `enabled` only when a session starts and force-logs-out only inside a
   login-manager request, so a session outliving a scripted disable still answered shared endpoints. The gate now
   refuses every non-exempt request from a disabled account.
2. **Customer data minimisation.** Helpdesk's own customer ticket list returns `_assign` (the assigned agent's email),
   and `getdoc`/`get_docinfo` bundle assignments and user details. For portal-only users the gate refuses those
   document-info endpoints on owned DocTypes and an `after_request` hook strips `_assign` and `_comments` from every
   JSON API response (fails closed).
3. **`on_trash` ordering.** Frappe's `User.on_trash` sets `enabled = 0` in memory before document-event hooks run, so
   the last-administrator guard reads persisted state.
