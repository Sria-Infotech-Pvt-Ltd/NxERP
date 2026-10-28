# Managing application access

Who may use which NXERP app is decided by **Frappe roles** (ADR-003). There is no separate grant table.

| App | Grant | Also counts as staff access |
| --- | --- | --- |
| ERPNext | role `NXERP Access: ERPNext` | nothing (business roles such as `Sales User` do **not** grant the app) |
| Helpdesk | role `NXERP Access: Helpdesk` | `Agent`, `Agent Manager` (Helpdesk's own invite flow keeps working) |

Customers (Website Users with `HD Customer`) use Helpdesk's customer portal only; they hold no staff access.

## Grant or revoke in Desk

1. Open **User** (or a **Role Profile**), tick or untick the access role, **Save**.
2. The change is recorded in the User's **Version** history (who, when, which role).
3. It applies on the user's next request. No re-login is needed.

Only a **System Manager** can change an `NXERP Access:` role. Anyone else, including the user editing their own
record, gets a permission error, even if they have write access to User through another route.

## Grant or revoke by API (System Manager only)

```
POST /api/method/nxerp.api.access.set_app_access   {"user": "...", "app_key": "helpdesk", "grant": 1}
GET  /api/method/nxerp.api.access.get_user_access?user=...
GET  /api/method/nxerp.api.access.get_my_access         (any logged-in user: their own landing and apps)
```

`set_app_access` accepts only `user`, `app_key`, `grant`. Revoking an app also removes any implied roles that confer it
(for Helpdesk: `Agent`, `Agent Manager`).

## Administrator lockout guard

| Rule | Where |
| --- | --- |
| `Administrator` always passes the gate and cannot be disabled | `nxerp.enforcement`, `nxerp.guard` (Frappe also refuses) |
| A resolver or gate error never locks out `Administrator` (it is never evaluated) | `nxerp.enforcement.auth_hook` |
| The **last named System Manager** cannot lose the role, be disabled or be deleted | `nxerp.guard.validate_user`, `on_trash_user` |
| A System Manager always keeps the Desk shell and the shared set, whatever apps they hold | `AppEntry.admin_shell` |
| Install, patch and migrate code is not blocked by the guard | `frappe.flags.in_install/in_patch/in_migrate` |

"Named" means a real account other than the reserved `Administrator`. If only `Administrator` exists, there is no named
administrator to protect.

## What a user sees when refused

| Request | Response |
| --- | --- |
| Page (`/desk`, `/helpdesk/...`) without the app | 302 to `/nxerp/no-access` (a plain page that names no app) |
| Page as a guest | 302 to `/login?redirect-to=...` |
| API call without the app | 403 JSON `You do not have access to this application` (no traceback) |
| Any request from a disabled account | page: 302 to `/login`; API: 403 JSON |

## Denial log

Each denial writes one JSON line to the `nxerp.access` log (`logs/<site>/nxerp.access.log`):
`{"event":"nxerp.access.denied","surface":"api_resource","app":"erpnext","user_ref":"u:ab12cd34ef","reason":"no_access","doctype":"Customer","http_method":"GET"}`.
`user_ref` is a salted hash, never an email; record names, query strings and bodies are never logged.
