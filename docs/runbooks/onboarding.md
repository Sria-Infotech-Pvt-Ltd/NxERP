# Runbook: signup, onboarding and access requests

Applies to the NXDESK public flow (Phase 2): `/signup`, `/get-started`, `/welcome/<key>` and the Desk queue **NXERP Access Request**.
Self-signup never grants staff access by itself: an administrator decides every request.

## 1. Enable signup (off by default)

Signup is closed on every site until an operator opens it. Two settings must agree, and `/signup` shows "Signup is not available" otherwise.

```bash
bench --site <site> set-config nxerp_enable_signup 1
bench --site <site> migrate            # or: bench --site <site> execute nxerp.install.sync_signup_setting
```

`sync_signup_setting` (also the patch `nxerp.patches.enable_signup_when_configured`, and run on every migrate) sets Website Settings
`disable_signup` to 0 **only** when `nxerp_enable_signup` is 1; it never closes a site. To close signup again:

```bash
bench --site <site> set-config nxerp_enable_signup 0
bench --site <site> set-value "Website Settings" "Website Settings" disable_signup 1     # or untick "Disable Customer Signup" in Desk
```

Site config is cached by each web worker for up to 60 seconds. Signup also needs working outgoing email (section 4).

## 2. What a signup does

- Frappe's own `sign_up` creates a **Website User** and emails the set-password link. The platform wrapper (`nxerp.api.account.sign_up`) answers the
  same message whether or not the address already exists, is limited to 10 calls per hour per IP, and removes Portal Settings' *default role* from
  the new account when that role is a product's portal role (otherwise every signup would silently get the Helpdesk customer role).
- After setting the password the person lands on `/welcome/<key>`, answers up to three short steps, and the request is created (policy `request_access`).
- Policies are set per product in `nxerp/registry.py` (`signup_policy`): `invite_only` (no request is created), `request_access` (default, both products),
  `open_portal` (grants the product's *portal* role only; no registry entry uses it).

## 3. Approve or reject a request

Desk: **`/desk/nxerp-access-request`** (filter by Status = Pending). Open a request and use **Decision > Approve** or **Reject**. Or by API (System Manager, POST):

```bash
curl -s -X POST http://<site>/api/method/nxerp.api.access_request.decide \
  -H 'Content-Type: application/json' -H "Authorization: token <api_key>:<api_secret>" \
  -d '{"name": "NXAR-00001", "decision": "Approve", "note": "Welcome"}'
```

Approve runs the platform's single grant path (`nxerp.api.access.set_app_access`, so the last-administrator guard and the Version log apply), then, because a
self-signed account is a Website User, also gives the **Desk User** role so the account becomes a System User (staff access ignores Website Users). It does
not give any product role: assign Agent / ERPNext roles or a Role Profile in the User form, as for any new colleague. Deciding twice changes nothing.

## 4. Read a verification link on a development stack

Dev sites normally set `mute_emails` = 1, which drops every email. To see the verification link:

1. `bench --site <site> set-config mute_emails 0` (wait up to 60 s).
2. Sign up. The message is in **Email Queue** (Desk `/desk/email-queue`, newest first); open it and copy the `update-password?key=...` link from the message.
3. With no outgoing Email Account the queue entry stays "Not Sent": that is fine, the link is in the stored message. To actually deliver it, point the default
   outgoing account at a capture server (the browser tests start one on port 2525: `apps/nxerp_platform/browser-tests/mailsink.mjs`, fixture `use_mail_sink`).
4. Set `mute_emails` back to 1 afterwards.

If the dev queue holds hundreds of old "Not Sent" test mails, `flush` stops at the first one it cannot send: delete those rows first.

## 5. Privacy and limits

- Answers are stored in **NXERP Onboarding** (language, time zone, kind of work, team size) and, for language and time zone, on the User's own fields. They are never logged;
  the access log (`nxerp.access` logger) records only a hashed user reference and the app key.
- A person can have at most 10 access requests in total and one open request per application. A note is at most 500 characters, has HTML stripped and is escaped on output.
- `nxerp.api.onboarding.*` always works on the session user; there is no user parameter.
