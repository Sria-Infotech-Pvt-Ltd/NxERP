# Runbook: login recovery

When people cannot sign in, or the NXERP login page is broken, work down this list. Each step is a
`bench` command run on the server (in the dev stack: `docker compose -p nxerp-dev exec bench bash -lc '<command>'`
from `deploy/dev`). Replace `SITE` with the site name. Steps 1, 2 and 4 (and the lockout in 3) were exercised against a real browser session by
`e2e/recovery.test.mjs` and `e2e/flows.test.mjs`.

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
