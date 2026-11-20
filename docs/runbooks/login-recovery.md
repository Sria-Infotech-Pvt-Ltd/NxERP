# Runbook: login recovery

When people cannot sign in, or the NXERP login page is broken, work down this list. Each step is a
`bench` command run on the server (in the dev stack: `docker compose -p nxerp-dev exec bench bash -lc '<command>'`
from `deploy/bootstrap`). Replace `SITE` with the site name. Steps 1, 2 and 4 (and the lockout in 3) were exercised against a real browser session by
`apps/nxerp_platform/browser-tests/recovery.test.mjs` and `apps/nxerp_platform/browser-tests/flows.test.mjs`.

**Do not paste passwords into a shared chat, ticket or shell history.** Where a command takes a password, leave
it off and the command prompts for it.

## 0. Is it the login page, or the credentials?

| Symptom | Likely cause | Go to |
| --- | --- | --- |
| `/login` is blank, unstyled or shows a template error | the NXERP login layer | 1 |
| Everyone is bounced back to `/login` or lands on a page that errors | the router or the launcher | 1 (the stock login still uses the router; if it persists see 5) |
| One person: "Invalid login credentials" | wrong or forgotten password | the person uses **Forgot password?**; an administrator can set one in Desk; if the administrator is the one locked out, 2 |
| One person: "locked" or "too many attempts" | Frappe's lockout | 3 |
| The Administrator cannot sign in | forgotten or lost password | 2 |
| Nobody who administers can sign in | no working administrator | 2, then 4 |

## 1. Kill-switch: serve Frappe's own login

Reverts **only the page**. Authentication, grants, the router and enforcement are unchanged, so people still
land where they are authorised to be.

```bash
bench --site SITE set-config -p nxerp_stock_login 1     # -p stores the number 1, not the text "1"
```

Site config is cached by each web worker for up to 60 seconds, so the stock login appears within a minute. A
restart makes it immediate. Check: open `/login`; the page is Frappe's standard login (no NXERP hero panel), and a
known account can sign in.

Put it back when the cause is fixed:

```bash
bench --site SITE set-config -p nxerp_stock_login 0
```

(`bench --site SITE set-config -p nxerp_stock_login 0` leaves the key with the value 0, which is off. Removing the
key from `sites/SITE/site_config.json` also works.)

## 2. Reset the Administrator password

```bash
bench --site SITE set-admin-password                  # prompts for the new password
bench --site SITE set-admin-password --logout-all-sessions   # also ends every session, if you suspect a leak
```

Sign in at `/login` as `Administrator`. Rotate any shared copy of the old password.

## 3. A locked-out account

Frappe locks an account for about a minute after repeated failures and refuses even the right password meanwhile.
Wait, then sign in. There is nothing to clear by hand. If an account keeps locking, someone is guessing: look
at *Authentication Log* in Desk, and consider disabling the account.

## 4. No working administrator at all: create a break-glass System Manager

```bash
bench --site SITE add-system-manager recovery@your-company.example --first-name Recovery
```

The command prompts for the password if `--password` is omitted. **FACT (tested):** Frappe gives a user created this way
every role, including both `NXERP Access:` roles, so they sign in to the launcher with every app (the same as the person who
finished the setup wizard). Treat it as a full administrator: fix the real problem, then delete the break-glass user in Desk and
record who created it and when.

A System Manager who was *not* created this way holds no app by default (ADR-003): they land on the "No access" page, which
links to *Manage user access* in Desk, where an `NXERP Access:` role can be granted.

## 5. The platform itself is the problem

If the kill-switch does not help, the fault is not the login page. Check, in this order:

1. `bench --site SITE doctor` and `bench --site SITE migrate` ran cleanly after the last deploy.
2. `nxerp` is the **last** installed app (`bench --site SITE list-apps`): its `/login` only wins when it is.
3. The web log for the failing request.

Uninstalling `nxerp` is **not** a recovery step: it removes the access roles and the audit trail, and the other
apps would then be reachable by anyone with a Frappe role. Ask for a code fix instead.

## After any recovery

- Say in the incident note what was changed and by whom.
- Confirm one account per app can sign in and lands correctly (Helpdesk-only: Helpdesk; ERPNext-only: ERPNext;
  both: the launcher).
- Turn the kill-switch back off.

## 6. Federated sites (Phase 6): break-glass per app

Applies once the sites use single sign-on (`nxerp_site_role` set, ADR-003 amendment 2). Each app site and the identity site keep their OWN
break-glass Administrator: if the identity site or the single sign-on flow fails, a site can still be reached locally.

**Before disabling local password login on an app site (do all three, record them):**

1. A working single sign-on test for a fake user on that site (`docs/architecture-isolation/phase-6-user-actions.md`, step 6.7).
2. A break-glass Administrator password set and stored offline: `bench --site SITE set-admin-password` (it prompts; do not put the password on the
   command line). For a stack: `deploy/scripts/stack.sh <stack> bench set-admin-password`.
3. The way back below rehearsed on staging.

**Switching local login off or on is a person's decision** (Desk: System Settings, "Disable Username/Password Login"; Frappe refuses it unless a Social
Login Key is enabled). Code and the federation helpers never set it.

**If single sign-on is broken and local login is off:** re-enable local login from the server, with an interactive console:

```bash
bench --site SITE console
>>> frappe.db.set_single_value("System Settings", "disable_user_pass_login", 0)
>>> frappe.db.commit()
>>> frappe.clear_cache()
```

For a stack: `deploy/scripts/stack.sh <stack> bench console` (needs an interactive terminal). Then sign in at `/login` as `Administrator` with the
break-glass password. Site config is cached up to 60 seconds; `frappe.clear_cache()` makes the setting effective at once.

If the NXERP login page itself is the problem (not the credentials), the kill-switch in section 1 still works on every site. If the **identity site**
is down: app sites keep working for open sessions; people with a break-glass account sign in locally (local login must still be on for those sites).

**What was tested and what was not (2026-11-19, Phase 5 stacks `id` and `hd`, fake data):**

| Command or behaviour | Result |
| --- | --- |
| With `disable_user_pass_login` = 1: `/login` shows no password form; `POST /api/method/login` answers 401 "Login with username and password is not allowed" and issues no `sid`; the single sign-on flow still signs the user in | **TESTED** (`scripts/spike_federation_flow.py`, scenario S5) |
| Setting `disable_user_pass_login` back to 0 with `frappe.db.set_single_value` and `frappe.clear_cache()` (the second step of the console recovery) | **TESTED** (the same script resets it that way) |
| The same two lines typed in an interactive `bench console` | **UNVERIFIED**: a console needs an interactive terminal, which the automated run does not have; rehearse it on staging before relying on it |
| `bench --site SITE set-admin-password` followed by signing in with local login on | **UNVERIFIED** on the federated stacks (the Phase 1 recovery drill covered it on the single-site stack) |
| Switching local login off in Desk when no Social Login Key is enabled | **TESTED** by reading Frappe's own check (`system_settings.py: validate_user_pass_login`), not by clicking |

