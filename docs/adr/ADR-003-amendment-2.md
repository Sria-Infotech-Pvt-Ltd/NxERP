# ADR-003 amendment 2: grants move to the identity site (Phase 6)

- **Status:** Proposed (accepted with ADR-009 when the owner sets it)
- **Date:** 2026-11-19
- **Amends:** ADR-003 (access model) and its amendment 1. The model stays "grants are Frappe roles, one resolver, a server-side gate". What changes
  is *where the grant is made* when the apps live on separate sites (ADR-009, ADR-004 amendment 2: one sign-in page per app).

## Decisions

1. **Grants are roles on the identity site, copied to the app sites.** On the identity site an administrator grants `NXERP Access: <app>` exactly as
   today (the User form or `nxerp.api.access.set_app_access`). A change queues a row in the provisioning outbox in the same transaction; the
   scheduler delivers it to the app site, whose own `nxerp.federation.api` creates or disables the local user and adds or removes that app's access
   role. A nightly reconcile repairs drift toward the identity site. The identity site holds the access role of every app (the apps are not
   installed there); an app site holds only its own.
2. **Business roles stay per app.** Provisioning adds or removes only the access role of the app the receiving site owns. `Agent`, `Sales User`
   and the like are assigned by that app's own administrator. Consequence found in testing: Frappe makes a user with no desk-access role a Website
   User, so a newly provisioned person is staff on the app site only after the app's administrator gives them a business role (the access role has
   `desk_access = 0` on purpose).
3. **No password ever leaves the identity site.** A user is created on an app site without a password and without a welcome email. People
   sign in through the identity site (Frappe's OAuth authorization-code flow, userinfo only: spike item (g)). Sign ups on the app site's Social Login
   Key stay **Deny**: allowing them would create a Website User with Portal Settings' default role (spike item (b)).
4. **The identity site is also a gate.** Each OAuth Client lists `allowed_roles` = the app's access role. A person without it is refused at the
   identity site (`400 Invalid client_id`), before reaching the app (spike item (a2)). This is enforcement on the server, not a hidden button.
5. **Local password login on an app site is disabled only after single sign-on is proved** on that site and a break-glass Administrator exists
   and is recorded (`docs/runbooks/login-recovery.md`, per-app section). Code never sets `disable_user_pass_login`; a person does, at a gate. Frappe
   itself refuses to switch it on with no Social Login Key, LDAP or email-link login available.
6. **Customers' logins live on the identity site (assumption A4).** A customer is an identity-site Website User; the portal role and the
   customer's records stay in the app that owns them. A customer reaches an app site through the same single sign-on and gets the restricted portal
   only, never Desk. UNRESOLVED until the owner confirms A4: how a customer is provisioned (the same outbox with `user_type` Website User is
   ready; the portal role would be an app-side business role).

## Consequences

- One identity per person, one credential, per-app sign-in pages. The grant list is one screen (the identity site); each app keeps its own business roles.
- The identity site becomes critical for sign-in and for grant changes; the app sites keep serving sessions that are already open if it is down, and
  break-glass administrators keep local access.
- The OAuth Client secret is a clear-text `Data` field of 10 hex characters when Frappe generates it (spike item (a1)): setup supplies its own 32+
  character secret (`nxerp.federation.setup`, from an environment variable), and the identity database is treated as holding application credentials.
- Off by default: nothing in this amendment has any effect on a site that has not set `nxerp_site_role`.
