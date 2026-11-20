# Phase 6: what the human does (identity site and login federation)

The nine steps of the blueprint's "identity site and login federation" phase, in order, with their commands. Replace `<domain>`. Secrets appear as
`<PLACEHOLDER>`: generate them with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`, keep them in your password manager and never paste
them into a chat, a ticket or a shell history line. Do this on the **staging stacks**, never first on the live stack. Use fake users such as
`user@example.test`. Findings that changed the original text are marked **(spike)**: see `spike-federation.md`.

Two points the first version of this plan got wrong **(spike)**:
- The OAuth Client's secret field is read-only in Desk and Frappe fills it with 10 hexadecimal characters stored in clear text. For anything beyond a
  rehearsal set a strong secret with the helper (step 6.5), not by clicking "New".
- A newly provisioned person has no password and holds only the app's access role. Frappe treats a user without a desk-access role as a Website User, so the
  app's own administrator must also give them a business role on that site (for Helpdesk: Agent) before they are staff there.

## Step 6.1 Read the spike and decide go or no-go

Open `docs/architecture-isolation/spike-federation.md`. **Expected:** items (a) to (h) each have an answer with evidence and the decision is GO.
**Undo:** nothing.

## Step 6.2 Turn on the site roles (configuration, reversible)

```
deploy/scripts/stack.sh id  bench set-config nxerp_site_role identity
deploy/scripts/stack.sh erp bench set-config nxerp_site_role app
deploy/scripts/stack.sh hd  bench set-config nxerp_site_role app
```

**Check:** `docker compose -p nxerp-hd exec backend bash -lc 'cd /home/frappe/frappe-bench && python3 -c "import json;print(json.load(open(\"sites/hd.<domain>/site_config.json\")).get(\"nxerp_site_role\"))"'`
prints only that key. Frappe caches site config for up to 60 seconds. Then run `bench --site <site> migrate` once on each stack so the new DocTypes and the
`NXERP Provisioner` role exist. **Undo:** `bench --site <site> set-config nxerp_site_role ""`.

## Step 6.3 Create the provisioning service user on each app site

On `erp` and on `hd`:

1. Open `https://<stack host>/app/user/new` as the stack's `Administrator` (password in `deploy/env/isolated/<stack>.env`; local login is still on).
2. Email `svc-provisioner@<domain>`, First Name `Provisioner`. Untick "Send Welcome Email".
3. Roles: tick only `NXERP Provisioner`. Save. **(spike)** Frappe will show the user as a Website User: that is expected and token authentication works for it.
4. "API Access" > "Generate Keys". The API Secret is shown **once**: copy it into your password manager now. The API Key stays on the form.

**Check:** the role list shows exactly `NXERP Provisioner`. **Undo:** untick Enabled; "Generate Keys" again invalidates the old secret.

## Step 6.4 Register the app sites on the identity site

At `https://id.<domain>/app/nxerp-peer/new`, one record per app site:

| Field | `erp` record | `hd` record |
| --- | --- | --- |
| App Key | `erpnext` | `helpdesk` |
| Origin | `https://erp.<domain>` | `https://hd.<domain>` |
| Internal URL | `http://erp-backend:8000` | `http://hd-backend:8000` |
| Site Name | `erp.<domain>` | `hd.<domain>` |
| API Key / API Secret | from step 6.3 on `erp` | from step 6.3 on `hd` |
| Enabled | ticked | ticked |

**Check:** reopen a record: the secrets show dots. **Undo:** untick Enabled (stops provisioning to that site and removes its origin from the redirect allow-list).

## Step 6.5 Create the OAuth clients on the identity site

Recommended (strong secret, gated to the app's access role): from an interactive shell on the identity stack, with the secret in the environment, not on the command line:

```
export NXERP_SSO_SECRET_HELPDESK='<PLACEHOLDER 32+ characters>'
export NXERP_SSO_SECRET_ERPNEXT='<PLACEHOLDER 32+ characters>'
NXERP_PASSTHROUGH="NXERP_SSO_SECRET_HELPDESK NXERP_SSO_SECRET_ERPNEXT" deploy/scripts/stack.sh id bench execute nxerp.federation.setup.configure_identity_site
```

It creates one OAuth Client per enabled peer (App Name `NXERP <title>`, Scopes `all openid`, Redirect URIs and Default Redirect URI
`<origin>/api/method/frappe.integrations.oauth2_logins.login_via_frappe`, Authorization Code, Code, Skip Authorization on, **Allowed Roles** =
`NXERP Access: <app>`) and prints each client id (not a secret). Run it twice: the second run changes nothing. Copy each client id.
Desk alternative for a rehearsal only: `https://id.<domain>/app/oauth-client/new` with the same values, adding the Allowed Roles row (an empty list allows nobody).
**Undo:** delete the OAuth Client (that app can then no longer sign in through `id`).

## Step 6.6 Tell each app site to accept logins from the identity site

Recommended, on each app stack (same secret as step 6.5 for that app):

```
export NXERP_IDENTITY_ORIGIN='https://id.<domain>' NXERP_SSO_CLIENT_ID='<client id from 6.5>' NXERP_SSO_CLIENT_SECRET='<PLACEHOLDER same secret>'
NXERP_PASSTHROUGH="NXERP_IDENTITY_ORIGIN NXERP_SSO_CLIENT_ID NXERP_SSO_CLIENT_SECRET" deploy/scripts/stack.sh hd bench execute nxerp.federation.setup.configure_app_site
```

It creates the Social Login Key named `frappe`: provider Frappe, Base URL = the identity origin, Authorize URL `/api/method/frappe.integrations.oauth2.authorize`,
Access Token URL `/api/method/frappe.integrations.oauth2.get_token`, Redirect URL `/api/method/frappe.integrations.oauth2_logins.login_via_frappe`,
API Endpoint `/api/method/frappe.integrations.oauth2.openid_profile`, Auth URL Data `{"response_type": "code", "scope": "openid"}`, Enable Social Login on,
**Sign ups = Deny**, **Custom Base URL ticked** (without it the button's link points at the app itself and sign-in loops). Desk alternative: `https://hd.<domain>/app/social-login-key/new` with those values.
**Check:** `https://hd.<domain>/login` shows a "Sign in with NXERP" button AND its link starts with `https://id.<domain>/` (right-click, copy link address). **Undo:** untick Enable Social Login.

## Step 6.7 Test single sign-on with a fake user

1. On `id` create `user@example.test` (a System User with a password) and grant Helpdesk (User form: role `NXERP Access: Helpdesk`, or `set_app_access`).
2. Wait up to one minute. On `hd` open `https://hd.<domain>/app/user/user@example.test`: it exists, enabled, role `NXERP Access: Helpdesk`, no password. Give the person the
   Helpdesk business role they need there (Agent).
3. In a private browser window sign in at `https://id.<domain>/login` as the test user, then open `https://hd.<domain>/helpdesk`.

**Expected:** no second password prompt; you land in Helpdesk. **Check:** `https://erp.<domain>/desk/home` for the same user shows the friendly "no access" page, and
the identity site refuses the sign-in to `erp` outright (no grant). **Undo:** disable the test user on `id`; the next reconcile disables it on `hd`.

## Step 6.8 Make sure you cannot be locked out, then disable local login

Only after 6.2 to 6.7 work. Read `docs/runbooks/login-recovery.md` section 6 first.

1. Break-glass `Administrator` on each app site, stored offline: `deploy/scripts/stack.sh hd bench set-admin-password` (it prompts; do not put the password on the command line).
2. Rehearse the way back on staging: `deploy/scripts/stack.sh hd bench console`, then `frappe.db.set_single_value("System Settings", "disable_user_pass_login", 0)`, `frappe.db.commit()`, `frappe.clear_cache()`.
3. Only then, on the app site: `https://hd.<domain>/app/system-settings`, tick "Disable Username/Password Login", Save. (Frappe refuses unless a Social Login Key is enabled.)

**Expected:** `/login` offers only the SSO button; a direct password POST issues no `sid` cookie; the test user still gets in through `id`. **Undo (locked out):** the console lines in point 2.

## Step 6.9 Test revocation and reconcile

1. On `id` remove the test user's `NXERP Access: Helpdesk` role.
2. Within a minute `https://hd.<domain>/app/user/user@example.test` is disabled with the role removed.
3. Run the reconcile once by hand: `deploy/scripts/stack.sh id bench execute nxerp.federation.reconcile.run`.

**Expected:** the answer ends `'message': '0 differences'`. **Check:** the scheduler is active on the identity site (`deploy/scripts/stack.sh id bench doctor`). **Undo:** re-grant the role.
