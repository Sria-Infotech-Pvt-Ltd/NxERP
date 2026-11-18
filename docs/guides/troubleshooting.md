# Troubleshooting

Real problems met while building NXERP, with cause and fix. Each entry says whether the cause was **verified** (seen and
reproduced or proven by a test) or is an **assumption**. For login problems in a running environment use the runbook
[`../runbooks/login-recovery.md`](../runbooks/login-recovery.md) first. Commands run in the dev stack from `deploy/bootstrap`
(`docker compose -p nxerp-dev -f compose.yaml exec -T bench bash -lc '<command>'`); replace `<site>` with `nxerp.localhost`
(dev) or `nxerp-e2e.localhost` (browser suite). **Never** `docker compose down -v` or recreate the stack to fix a problem: that
deletes the site and its database. Restarting the one container (`docker restart nxerp-dev-bench-1`) is fine.

## Quick index

| Symptom | Section |
| --- | --- |
| ERPNext `/desk` reloads in a loop between `setup-wizard`, `/apps` and `/desk` | 1 |
| A page's guard or controller never runs; a `www` page renders but ignores its checks | 2 |
| I changed site config and nothing happened | 3 |
| My script that checks for a process always finds one | 4 |
| `bench execute` says it worked but nothing changed | 5 |
| `/workspace/...` path becomes `C:/Program Files/Git/workspace/...` | 6 |
| Command asks for a MariaDB root password and the docs do not say where it is | 7 |
| A clean build gives Helpdesk with its own login, or the bootstrap cannot fetch the Helpdesk pin | 8 |
| `ValidationError: Throttled`, "too many users", password-reset limit | 9 |
| Bootstrap and build failures seen in Phase 1 | 10 |
| Wrong login page, wrong landing, "No access" for someone who should have access | 11 |
| Running out of disk | 12 |

## 1. ERPNext reloads in a loop (`/desk` to `setup-wizard` to `/apps` to `/desk`)

- **Symptom:** opening ERPNext Desk on a site flickers and reloads forever.
- **Cause (verified, dev-site incident in Phase 3):** Frappe's global default `desktop:home_page` stays `setup-wizard` until the wizard genuinely finishes. A fixture had marked the site's setup as complete (the setup flags) without resetting that default, so Desk sent the browser to the wizard, the wizard sent it back, repeat. It was a test-fixture mistake, not a platform bug.
- **Fix:** set the default to `workspace`, which is what a finished wizard sets (ERPNext then opened with no redirects). Do not mark setup complete by hand; finish the wizard, or use its API as `apps/nxerp_platform/browser-tests/first-run.test.mjs` does. The fixtures no longer touch the dev site's setup state.
- **Status of the command:** the value and the effect were verified on the dev site in Phase 3; the exact command used was not recorded. Frappe's own source confirms the form: `frappe/desk/page/setup_wizard/setup_wizard.py:410` does `frappe.db.set_default("desktop:home_page", "workspace")` when the wizard completes, `frappe/utils/install.py:48-49` sets `setup-wizard` on install, and the patch `reset_corrupt_defaults` (`v13_0`) sets either value from `setup_complete`. One way to apply it by hand is `bench --site <site> console` then `frappe.db.set_default("desktop:home_page", "workspace")` and `frappe.db.commit()` (ASSUMPTION: this exact snippet was not run for this page). Related: the Administrator on a site with an unfinished wizard is deliberately routed to `/desk` so the wizard runs (`routing.landing_for`, ADR-004 rule 5).

## 2. A hyphenated `www` page's controller never runs

- **Symptom:** `/nxerp/no-access` rendered, but its guard code did nothing (a guest saw "Back to my applications").
- **Cause (verified):** Frappe resolves the controller of a page named `a-b` as `a_b.py`. `no-access.py` was never imported, so the page ran as a bare template. Same for the test-only page (it was publicly reachable as a static page until renamed).
- **Fix / rule:** name the controller with underscores (`no_access.py`, `test_app.py`) and add a test that proves the controller executes ([coding-standards.md](coding-standards.md)).

## 3. A site-config change takes up to a minute

- **Symptom:** `bench set-config -p nxerp_stock_login 1` (the kill-switch), `nxerp_test_apps`, or any `update_site_config(...)` in a test seems to do nothing.
- **Cause (verified, `frappe/config.py`, `ttl=60`):** every web worker caches site config for up to 60 seconds.
- **Fix:** wait up to a minute, or restart the bench process (`docker restart nxerp-dev-bench-1`) for an immediate effect. Tests poll for the effect (`wait_until`, 80 s limit) instead of sleeping. In-process tests patch `registry.get_registry` and do not use site config ([testing.md](testing.md)).

## 4. `pgrep -f` always finds a process: it found itself

- **Symptom:** a harness script "detects" that a server is already running when it is not (or fails to start one).
- **Cause (verified):** `pgrep -f '<pattern>'` run from `bash -lc '... <pattern> ...'` matches the very shell whose command line contains the pattern.
- **Fix:** probe the port instead (`curl -s -o /dev/null http://localhost:8001/login`), and when you must match a process use a bracketed pattern (`pkill -f 'bench_[h]elper.*serve --port 8001'`). This is what `apps/nxerp_platform/browser-tests/run.sh` does.

## 5. `bench execute` hides the real exception

- **Symptom:** a fixture or check run with `bench execute ...` prints something harmless and exits as if it worked; the data is not there.
- **Cause (verified):** `bench execute` swallows the function's real exception.
- **Fix:** run fixtures with `python -m` from the bench's `sites` directory so a failure is a traceback: `cd ~/frappe-bench/sites && E2E_SITE=<site> ../env/bin/python -W ignore -m nxerp.tests.e2e_fixtures setup`. For read-only one-liners `bench execute` is fine, but never trust a silent success for a write. (The dev-seed command in `deploy/README.md` uses `bench execute` and prints one line per user: check that output.)

## 6. Git Bash rewrites `/workspace/...` into a Windows path

- **Symptom:** `docker compose exec bench ls /workspace` fails, or complains about `C:/Program Files/Git/workspace`.
- **Cause (verified):** MSYS path conversion in Git Bash rewrites arguments that look like POSIX paths.
- **Fix:** prefix the command with `MSYS_NO_PATHCONV=1`, or keep the path inside the quoted `bash -lc '...'` string (observed: a path embedded in a longer quoted string, as `apps/nxerp_platform/browser-tests/run.sh` does, is left alone). Using WSL avoids it.

## 7. Where is the MariaDB root password?

- **Symptom:** `bench new-site`, `drop-site` or `restore` asks for a root password and no document says where it is.
- **Answer:** the dev stack generates it on first run into the git-ignored `deploy/bootstrap/.env` as `NXERP_DB_ROOT_PASSWORD` (next to `NXERP_ADMIN_PASSWORD`). It is deliberately in no document and no script. `apps/nxerp_platform/browser-tests/site.sh` passes it into the container for you. For an ad-hoc command: `cd deploy/bootstrap; set -a; . ./.env; set +a; docker compose -p nxerp-dev -f compose.yaml exec -T -e NXERP_DB_ROOT_PASSWORD bench bash -lc 'cd ~/frappe-bench && bench --site <site> restore <file> --db-root-password "$NXERP_DB_ROOT_PASSWORD"'` (the variable is read from your shell, never typed or printed). Day-to-day work does not need the root password: the site has its own database credentials.
- If `deploy/bootstrap/.env` is lost, ASSUMPTION: the passwords already stored in the existing volumes still apply and a regenerated `.env` would not change them (not tested). Do not recreate the stack to "reset" them; ask the person who ran the first `up.sh`.

## 8. The Helpdesk pin in `deploy/apps.json` is not the code you are running

- **Facts (verified 2026-10-28):** `apps.json` pins the Helpdesk fork commit `1c6981cc5` on `feature/nxerp-login-page`, which exists on the `company` remote and still contains Helpdesk's own `www/login.*`. The Phase 3 Helpdesk work (login removed, title "Helpdesk", Apps menu) is on the local branch `feature/nxerp-platform-login` (`3897718c6`), which **is not on any remote**.
- **Consequences:** `./deploy/bootstrap/up.sh` installs the branch checked out in the sibling `../helpdesk` folder when it exists (the intended dev setup), so a developer with that checkout sees Phase 3. A build **without** the sibling folder (a clean CI runner, a new colleague's machine) installs the pinned commit, i.e. Helpdesk before Phase 3. `nxerp` is installed last so its `/login` still wins, but the rest of the Phase 3 changes are absent. Whether the full test suite passes on that build is NOT verified.
- **If the bootstrap cannot fetch a pin:** it fails on purpose (`fetch_pinned` aborts when the commit does not resolve; the exact message was not reproduced for this page). Push the commit to the fork first (needs write access to `Sriainfotech/Frappe-Help-Desk`), then update `apps.json` to that exact commit, update [ADR-002](../adr/ADR-002-version-matrix.md) and run `python3 -I deploy/check_pins.py`.
- **Rule:** the release must pin a commit that exists on a remote ([release-process.md](release-process.md)); a local-only branch cannot be a release.

## 9. `ValidationError: Throttled` and rate limits in tests

- **Symptom:** tests that create users fail with `Throttled`; a password-reset or email-link flow is refused in the browser suite; seven Helpdesk tests errored this way in Phase 1.
- **Cause (verified for user creation):** Frappe refuses more than `throttle_user_limit` (default 60) new users per hour per site, and rate-limits password-reset and email-link requests. The suites create many throwaway users.
- **Fix:** in process, `nxerp.tests.utils.allow_many_test_users()` lifts the limit for that process only. On a site that runs the suites: `bench --site <site> set-config -p throttle_user_limit 100000`. **Use `-p`**: without it the value is stored as a string and has no effect. The browser fixtures raise `password_reset_limit` and `rate_limit_email_link_login` on the fresh site. Login lockout after repeated wrong passwords is a different, intended Frappe behaviour: wait about a minute.

## 10. Bootstrap and build failures seen in Phase 1 (all fixed in the repo)

| Symptom | Cause (verified) | Fix |
| --- | --- | --- |
| `bench build` fails: `ENOENT .../sites/common_site_config.json` from `erpnext/banking/vite.config.ts` | a soft-linked app resolves `../../sites` from its real path | pinned apps are real clones in `apps/`; only `nxerp` is soft-linked |
| `set: pipefail: invalid option name` in `bootstrap.sh` | CRLF line endings written on Windows | `.gitattributes` forces `eol=lf`; keep shell files LF |
| `DocType Payment Gateway not found` | ERPNext links to a DocType only the separate `payments` app defines; `bench get-app` skips dependencies | `payments` is pinned in `apps.json` |
| 67 test errors `No module named 'freezegun'` | test-only dependency not installed | `bench setup requirements --dev` is in the bootstrap |
| `bench` not found on the Windows host | bench is not supported natively on Windows | everything runs in the container ([ADR-006](../adr/ADR-006-dev-environment.md)) |
| `git` fails to rename or lock inside the clone | OneDrive-synced folder locked `.git` | the bench lives in a named Docker volume; for a new clone prefer a folder outside OneDrive (ADR-006) |

## 11. Wrong login page, wrong landing, unexpected "No access"

| Symptom | Check |
| --- | --- |
| `/login` looks like stock Frappe | the kill-switch is on (`sites/<site>/site_config.json` contains `nxerp_stock_login` set to a true value); or `nxerp` is not the last installed app (`bench --site <site> list-apps`) |
| A user lands in Helpdesk although they hold ERPNext too, or the reverse | they have one app, not two: apps are derived from roles. `GET /api/method/nxerp.api.access.get_my_access` (as that user) or `get_user_access` (as System Manager) shows exactly which. A role such as `Sales User` does **not** grant ERPNext; `NXERP Access: ERPNext` does |
| A new user sees "No access" | they hold no access role. Grant one in Desk (User or Role Profile) or `set_app_access`; it applies on the next request, no re-login |
| A System Manager cannot open ERPNext records | by design: they keep the Desk shell to administer, not ERPNext data ([access-admin.md](../architecture/access-admin.md)); grant `NXERP Access: ERPNext` |
| A role was changed by SQL and the old access persists | Frappe's role cache: `bench --site <site> clear-cache`; use Desk or the API instead |
| Hook changes do not apply | restart the bench container (`docker restart nxerp-dev-bench-1`) |
| `bench run-tests` skips the Administrator tests | pass `-e NXERP_ADMIN_PASSWORD` explicitly: the container's own environment can be stale ([testing.md](testing.md)) |
| Mail from Frappe is titled "Login To Frappe" | known and not fixed: email branding is not done |

## 12. Disk space

The host and Docker Desktop can fill up (the dev workstation had about 12 GB free on 2026-10-28). `docker system df` shows what Docker holds. Prune only what you understand: `docker image prune` removes dangling images; **do not** `docker volume prune` or `docker compose down -v` casually, because the dev site, its database and the browser-suite site live in named volumes. Do not pull large images "to try something" on a nearly full disk.
