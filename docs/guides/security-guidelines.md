# Security guidelines

For everyone who writes or reviews code in this repo. These are engineering rules, not legal, compliance or audit advice: a
compliance claim (data protection, certification) needs a professional review that this repository does not contain. The access
design is in [ADR-003](../adr/ADR-003-access-model.md) and its [amendment](../adr/ADR-003-amendment-1.md); the review that tested it is
[`../security/phase2-review.md`](../security/phase2-review.md); what is and is not covered is [`../security/phase2-coverage.md`](../security/phase2-coverage.md)
and [`../security/shared-set.md`](../security/shared-set.md).

## The rules

1. **Hiding is not security. Enforce on the server.** A hidden tile, a missing menu item, a disabled button or a client-side route guard is display. Every
   page, API call, file, print, report and realtime room must be refused **on the server** for someone without the grant, including when they type the URL or call the API
   directly. The frontend is never the boundary. The persona matrix exists to prove this per surface.
2. **Authentication, authorisation, visibility and routing are four separate things.** Login (who), grants and permissions (what is allowed), the launcher (what is shown),
   the router (where you go). Never let one stand in for another: landing a user somewhere does not authorise them, and a route that works for a user is not a permission.
3. **Roles are the grants.** Reuse Frappe roles, DocType permissions, User Permissions and desk access. Do not build a parallel permission store. The app-level gate in `nxerp` only **denies** on top of Frappe; it never grants.
4. **Fail closed.** If the resolver or the gate errors, deny (everyone except `Administrator`, who is never evaluated so a bug cannot lock the superuser out). A new surface that cannot be classified is a finding, not an allow.
5. **The shared set is deliberate.** Frappe core DocTypes and `frappe.*` methods are governed by Frappe alone ([shared-set.md](../security/shared-set.md)). Put an app's data in the app's own modules so the gate covers it; do not put app data in a custom or core module.
6. **Customers get the restricted customer portal only.** Never Desk, never internal ticket data, never another customer's data, never the assigned agent's address. Portal-only users get document-info endpoints refused and `_assign`/`_comments` stripped from responses; do not add an endpoint that bundles that data.
7. **No new `allow_guest=True`** without a written reason in the PR and a test that the endpoint reveals nothing beyond what a guest may see. Guests are never gated by NXERP, so a guest endpoint is only as safe as its own code.
8. **Disabled accounts reach nothing**, not even shared endpoints, and revocation applies on the next request. Do not add a cache of grants (the resolver has none on purpose).

## Redirects (open-redirect safety)

- Every redirect target the platform issues is a **site-relative path**; never a scheme, host, `//` or backslash. Use `routing.safe_target` (it percent-decodes up to three rounds before judging, rejects control characters and over-long input, normalises `..`), then `routing.authorised_target` (the path must belong to an installed app **and** the user may use it). Do not write a second validator and do not use Frappe's `sanitize_redirect` as the decision (ADR-004 amendment 1).
- Never trust `redirect-to`, a User Invitation's `redirect_to_path` (still unvalidated by Frappe and open in ADR-004 amendment 1), or the browser's `localStorage["last_visited"]`.
- A new redirect payload that slipped through becomes a case in `HOSTILE` in `apps/nxerp_platform/nxerp/tests/test_routing.py` first, then a fix.

## Secrets and personal data

- **Never commit** secrets, `.env` files, keys, production config, database dumps, customer data or personal data. `.gitignore` excludes `.env*`, `*.pem`, `*.key`, `*.sql.gz`, `sites/`; pre-commit runs `gitleaks` and `detect-private-key`. They are a net, not permission.
- The dev stack generates **random** passwords into the git-ignored `deploy/dev/.env` on first run (the Administrator password and the MariaDB root password). They are never in a doc, a script or a log. A command that needs one reads it from the environment or prompts (`bench set-admin-password` prompts). Do not paste a password into a chat, ticket, PR, shell history or screenshot.
- Test data is clearly fake: `*@example.test`, generated per run (`secrets.token_urlsafe`), removed afterwards. Never copy production data to a dev or test site. The seed script refuses to run unless `developer_mode` is on.
- Docs and examples use placeholders (`<site>`, `<password>`), never a real address, name, token or customer.
- Dev-only code must be **inert in production**: test-only registry entries are honoured only when the site has `allow_tests`, are flagged `test_only`, and their stand-in page answers 404 on any other site; fixtures refuse to run without `developer_mode` **and** `allow_tests`. Keep that pattern for anything similar.

## Logging

- Log **what happened, not who or what was in it.** The denial log (`nxerp.access`, one JSON line per denial) records the surface, the app key, the reason, the DocType and the HTTP method; the user is a salted hash (`user_ref`), never an email or name. Record names, query strings, request bodies, passwords and tokens are never logged.
- Do not log an exception message that may contain data; log the exception type and `exc_info=True` to a named logger, and answer the caller with a generic message.
- A logging failure must never turn a denial into an error (the one `# nosec B110`), and must never be the only record of a security-relevant change: grants are recorded in the User's **Version** history (who, when, which role).
- Responses carry no traceback, no list of apps the user lacks and no role names (the tests assert it; developer mode on a dev site is the exception that is tested as such).

## Dependencies and supply chain

- Versions are pinned to exact commits in `deploy/` and checked by `deploy/check_pins.py`; the `frappe/bench` image is pinned by digest. A bump is a reviewed change with an [ADR-002](../adr/ADR-002-version-matrix.md) update, then a rebuild from empty volumes and the full test run.
- Security releases of Frappe, ERPNext and Helpdesk are taken by bumping the pin, not by patching vendored code (nothing is vendored). The review window and who owns it are an owner decision (ADR-002 lists an ASSUMPTION of seven days for critical fixes).
- `bandit` runs over `nxerp/` (tests with a documented skip list: asserts, generated fake passwords, `secrets`-based fixtures). A new finding is fixed or justified in a comment with its ID.

## Review checklist (copy into the PR review)

- [ ] **Enforced on the server?** Name the URL or method and the test that refuses a user without the grant, and a guest. Not "the button is hidden".
- [ ] **Both directions tested?** A persona that holds the grant is allowed, a persona that does not is refused, a revoked one is refused on the next request, a disabled one reaches nothing.
- [ ] **Does it grant anything?** It must not: the gate only denies. Anything that adds a role, a share or `ignore_permissions` needs a stated reason and a platform-administrator check (`access.is_platform_admin`).
- [ ] **New surface?** Is it classified by `path_prefixes`, `owns` or a DocType's module? If not, it is in the shared set: is that intended and documented? Add a matrix row.
- [ ] **Redirects:** every target through `safe_target` and `authorised_target`; no new reflection of `redirect-to` into HTML.
- [ ] **Customer data:** can a portal-only user reach internal notes, assignments, another customer's records, or an agent's address through this change?
- [ ] **Input:** accepted parameters are named and typed; no `**kwargs` passthrough; state changes are POST; no SQL built from input (use `frappe.db` parameters or the query builder).
- [ ] **Errors:** fail closed, generic message, no traceback, no names of apps or roles.
- [ ] **Secrets and PII:** none in code, config, fixtures, logs, docs or the PR text.
- [ ] **Dev-only code** is guarded by `developer_mode`/`allow_tests` and inert in production.
- [ ] **Architecture rule:** no app imports another; `scripts/check_architecture.py` passes.
- [ ] **Docs and ADR updated** if an access rule, a route or a pin changed.
- [ ] **What was not verified** is written down in the PR.

## Reporting a problem

A suspected vulnerability is reported privately to the security owners named in `CODEOWNERS` and [`../governance/ownership.md`](../governance/ownership.md), not in a public issue or PR. Do not exploit it against shared data to prove it; a fake-data test site reproduces everything here.
