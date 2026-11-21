# Signup gate: a feature kept for later (currently NOT in use)

**Status: excluded on purpose (2026-11-21).** Self-signup is open to anyone on every site. Nothing asks an operator for permission, and no site config key is needed. This page records what the gate was, why it existed, and exactly how to bring it back when it is needed. It is a decision record plus a ready implementation plan, not a request.

## 1. What happens today

- `/signup?app=<product>` shows the create-account form to any visitor. A signed-in visitor is sent on to `/get-started`.
- The only thing that can close signup is Frappe's own Website Settings flag **Disable Customer Signup** (`disable_signup`). An administrator may tick it in Desk. Then the page shows the calm "Signup is not available" state and the endpoint answers 403.
- `install.open_signup()` sets that flag to 0 **once** on a fresh install and **once** on an existing site (patch `nxerp.patches.open_signup_for_everyone`). It does not run on every migrate, so an administrator's later choice to close signup is respected.
- What a signup creates is unchanged and safe by itself: a **Website User** with no staff role and no portal role it did not ask for, the same neutral answer whether or not the address exists, at most 10 calls an hour per IP, and an emailed set-password link. Access to a product still needs an administrator's decision (the access request queue). Signup never grants staff access.

## 2. What the gate was (removed)

Before 2026-11-21 signup was closed by default behind two switches that both had to agree:

1. site config `nxerp_enable_signup` = 1 (the operator's switch), and
2. Website Settings `disable_signup` = 0.

`install.sync_signup_setting()` ran on every migrate and set the second switch to 0 only when the first was 1. A fresh site therefore stayed closed until an operator ran `bench --site <site> set-config nxerp_enable_signup 1` and migrated.

Why it existed: a business system should not accept public accounts by accident. It was a safe default for the first sites, not a requirement of the architecture.

## 3. Why it was removed

The owner decided that for now nobody should need a permission step to sign up, and that any restriction ("turn signup off at the initial stage of a site") will be added later by choice. The gate was removed rather than left on with a different default so the code has no hidden barrier.

## 4. Risks while signup is open (accepted for now)

| Risk | What limits it today | What to add if it becomes a problem |
| --- | --- | --- |
| Spam or bot accounts | rate limit of 10 calls per hour per IP; Website Users only, no access | a captcha, an email-domain allow-list, or the gate in section 5 |
| Email abuse (set-password mails to strangers) | same rate limit; neutral reply that does not reveal whether an address exists | a per-address cooldown; outgoing mail rate limit |
| Customer-role leakage | the wrapper removes Portal Settings' default role from the new account when it is a product's portal role | keep the test `test_signup_creates_a_website_user_with_no_staff_role_and_no_portal_role` |
| Accounts piling up | an administrator can disable users; the access-request queue is capped per user | a clean-up job for never-verified accounts |

Signup also needs working outgoing email (see `docs/runbooks/onboarding.md`, section 4). Without it the set-password link is never delivered.

## 5. How to bring the gate back (ready plan)

Do this only on a decision of the owner. It is small and reversible.

1. **Switch.** Add a site config key (suggested name `nxerp_signup_requires_switch`, default 0 so today's behaviour stays) or reuse the old name `nxerp_enable_signup` with the old meaning. Decide the default per environment: closed for production, open for staging, in the environment's own site config, not in code.
2. **Code, `apps/nxerp_platform/nxerp/api/account.py`:** make `signup_available()` also require the switch:

   ```python
   def signup_available() -> bool:
       gated = frappe.utils.cint(frappe.conf.get("nxerp_signup_requires_switch"))
       switched_on = frappe.utils.cint(frappe.conf.get("nxerp_enable_signup"))
       return (not gated or switched_on) and not frappe.utils.cint(frappe.get_website_settings("disable_signup"))
   ```

3. **Install hook, `apps/nxerp_platform/nxerp/install.py`:** make `open_signup()` do nothing when the gate is on and the switch is off, so a gated site is not reopened.
4. **Tests to restore** (they existed in `test_onboarding.py`, `test_onboarding_pages.py`, `e2e_fixtures.py` and `browser-tests/onboarding.test.mjs`; `git log -p -- apps/nxerp_platform/nxerp/api/account.py` shows the old versions):
   - signup is refused and creates nothing while the switch is off;
   - both the switch and Frappe's own flag must agree;
   - the page shows the unavailable state and the endpoint answers 403 while closed;
   - the browser test that checks the unavailable state.
5. **Docs.** Restore the "Enable signup" section of `docs/runbooks/onboarding.md` and the sentence in `docs/architecture/routes.md`, and add the switch to the site-config reference.
6. **Roll out** with a patch or a one-line `set-config` per site, then `migrate`. Frappe caches site config for up to 60 seconds.

## 6. Where the code is today

| What | Where |
| --- | --- |
| Availability check | `apps/nxerp_platform/nxerp/api/account.py` (`signup_available`) |
| Open on install and on existing sites | `apps/nxerp_platform/nxerp/install.py` (`open_signup`), patch `nxerp.patches.open_signup_for_everyone` |
| The page | `apps/nxerp_platform/nxerp/www/nxerp/signup.html` and `signup.py` |
| Tests | `nxerp/tests/test_onboarding.py` (class `TestAccountSignUp`), `test_onboarding_pages.py`, `browser-tests/onboarding.test.mjs` |
| History of the gate | `git log -p -- apps/nxerp_platform/nxerp/api/account.py apps/nxerp_platform/nxerp/install.py` |
