# Testing NXERP

What kinds of tests exist, what each one is for, how to run it, and the traps that cost time so far. A statement here is
"verified" only when it was run and seen to work; the run records are in [`../PROGRESS.md`](../PROGRESS.md) and
[`../audit/bootstrap-evidence.md`](../audit/bootstrap-evidence.md). **A workflow file in git is not a working pipeline**:
`.github/workflows/ci.yml` runs the same commands, but per `docs/PROGRESS.md` it has not been run on GitHub from this machine.

Conventions used below. `<dc>` means the dev stack's compose command, run from Git Bash in `deploy/bootstrap` (Windows, Git Bash needs
`MSYS_NO_PATHCONV=1` in front whenever a command contains a `/workspace/...` path, or the path is rewritten to a Windows path):

```bash
cd deploy/bootstrap
set -a; . ./.env; set +a                    # exports NXERP_ADMIN_PASSWORD etc. into this shell (never echo them)
<dc> = docker compose -p nxerp-dev -f compose.yaml
```

On Linux and macOS use `python3` where this page says `python`.

## The layers

| Layer | What it proves | Needs the dev stack? | Where |
| --- | --- | --- | --- |
| 1. Static checks | formatting, lint, security patterns, pins, architecture rules | no (host or CI) | `ruff`, `bandit`, `deploy/check_pins.py`, `scripts/check_architecture.py`, pre-commit |
| 2. Plain Python tests | the architecture checker catches violations | no | `apps/nxerp_platform/nxerp/tests/test_architecture.py` |
| 3. Integration tests (in process) | registry, resolver, gate decisions, routing and redirect safety, guard, grant migration, the add-an-app checklist | yes: a Frappe site | `apps/nxerp_platform/nxerp/tests/test_*.py` (`IntegrationTestCase`) |
| 4. Persona x surface matrix | who is allowed or refused on each enforcement surface, over real HTTP | yes | `apps/nxerp_platform/nxerp/tests/test_access_matrix.py`, `world.py`; writes `docs/security/phase2-matrix.md` |
| 5. HTTP tests | real `/login`, `/nxerp/go`, `/nxerp/apps`, tile overrides, kill-switch, test-only third app, customer leaks | yes | `test_unified_experience.py`, `test_customer_leaks.py` |
| 6. Browser (Playwright) | the real login form, redirects, launcher, special flows, accessibility basics, recovery runbook, first-run wizard | yes, plus a **separate fresh site** | `apps/nxerp_platform/browser-tests/` |
| 7. Upstream regression | Helpdesk's own suite still passes with the access layer active | yes | `bench ... run-tests --app helpdesk` |

The pyramid is deliberately wide at layer 3 (fast, many cases, every decision table) and thin at 6 (slow, a few journeys). A new
access rule needs a layer 3 test and a matrix or HTTP row; a UI change needs a browser test.

## Layer 1: static checks (host, no stack)

```bash
python -I deploy/check_pins.py            # pins are exact, nxerp is last
python -I scripts/check_architecture.py     # architecture rules, see below
pre-commit run --all-files                # ruff, ruff-format, bandit, shellcheck, gitleaks, file hygiene
ruff check . --config apps/nxerp_platform/pyproject.toml --config src=["apps/nxerp_platform"] --config extend-exclude=["docs"] && ruff format --check . --config apps/nxerp_platform/pyproject.toml --config src=["apps/nxerp_platform"] --config extend-exclude=["docs"]   # what pre-commit runs for Python
bandit -r nxerp -x apps/nxerp_platform/nxerp/tests -q && bandit -r apps/nxerp_platform/nxerp/tests -s B101,B105,B106,B311 -q
```

`scripts/check_architecture.py` (stdlib only) fails when: `nxerp` imports another Frappe app in any form (import, from, `importlib.import_module("x")`, `__import__("x")`;
`frappe.get_attr("x.y")` strings are fine); `nxerp` declares `required_apps` or lists another app in `pyproject.toml`; the repo holds a second Frappe app; and,
**when given the other apps' checkouts**, an app imports `nxerp` or carries platform code (the `/login` page, `www/nxerp/`, the login assets, a copy of the resolver):

```bash
python -I scripts/check_architecture.py --app-path helpdesk=../helpdesk     # or: NXERP_APP_PATHS="helpdesk=../helpdesk"
```

Without `--app-path` the other-app checks are **skipped** and the output says so ("SKIPPED ... NOT verified by this run"); a green line without them
does not mean no app imports `nxerp`. `--root PATH` checks another tree with the same layout (the negative tests use it).

## Layer 2: plain Python tests (host, no stack)

```bash
python -m unittest nxerp.tests.test_architecture -v
```

Runs the checker against this repository **and** against synthetic trees that contain each violation, to prove the checker fails when it should. No Frappe, no site.

## Layers 3 to 5: the bench test suites (inside the container)

```bash
# everything in the platform app (about a few minutes; the HTTP tests wait out the config cache, see below)
MSYS_NO_PATHCONV=1 <dc> exec -T -e NXERP_ADMIN_PASSWORD bench bash -lc 'cd ~/frappe-bench && bench --site nxerp.localhost run-tests --app nxerp'

# one module
MSYS_NO_PATHCONV=1 <dc> exec -T bench bash -lc 'cd ~/frappe-bench && bench --site nxerp.localhost run-tests --app nxerp --module nxerp.tests.test_routing'
MSYS_NO_PATHCONV=1 <dc> exec -T bench bash -lc 'cd ~/frappe-bench && bench --site nxerp.localhost run-tests --app nxerp --module nxerp.tests.test_add_app_checklist'

# Helpdesk's own suite with the layer active (about 6 minutes)
<dc> exec -T bench bash -lc 'cd ~/frappe-bench && bench --site nxerp.localhost run-tests --app helpdesk'
```

- `NXERP_ADMIN_PASSWORD` (from the git-ignored `deploy/bootstrap/.env`) is needed only by the tests that sign in as Administrator (`test_unified_experience`); without it those are skipped, visibly. Pass it with `-e NXERP_ADMIN_PASSWORD` so the value is read from your shell and never typed or printed. The container's own environment can be stale: pass it explicitly.
- `NXERP_TEST_BASE` (default `http://localhost:8000`) is where the HTTP tests send requests: the dev web server **inside** the container. `NXERP_MATRIX_OUT=<path>` also writes the persona matrix as Markdown.
- The suites create clearly fake users (`nxt-*@example.test`, committed so a rollback keeps them) and remove them; `purge_test_users()` at the start of each class clears leftovers from an aborted run.
- Tests that must not depend on NXERP's deny layer call the app's own permission hook directly, not `frappe.has_permission` (a System Manager is refused Helpdesk records by the platform even when Helpdesk allows them).
- **One bench test run per site at a time.** Every class starts by deleting leftover `nxt-*@example.test` users, so two concurrent runs delete each other's fixtures, and they contend for database locks (observed 2026-10-28: a second run's `setUpClass` failed with a database error from `INSERT INTO tabUser` while another suite was running; it passed when run alone). Check `ps` in the container (or ask) before you start one.
- Hooks changed? Restart the bench process before testing: `docker restart nxerp-dev-bench-1` (restart, never recreate or `down -v` the stack: that destroys the site and database).

### The persona matrix

`test_access_matrix.py` builds ten personas (administrator, system manager, Helpdesk agent, ERPNext user, both, customer, no apps, revoked, disabled, guest) and calls every
enforcement surface of [`../security/phase2-coverage.md`](../security/phase2-coverage.md) over HTTP, with the expected `A` (reaches the app) or `D` (refused) per cell. Adding a surface or an app means adding rows,
not editing the engine. The rendered table is [`../security/phase2-matrix.md`](../security/phase2-matrix.md).

## Layer 6: browser suite (fresh-site harness)

The dev web server always answers with the default site, and the first-run wizard can only be exercised once per database, so the browser suite uses **its own fresh site**
`nxerp-e2e.localhost`, served on port 8001 inside the same container. The dev site is never touched.

```bash
apps/nxerp_platform/browser-tests/site.sh create      # about 10 minutes the first time: a new site with the same apps, NO setup wizard done
apps/nxerp_platform/browser-tests/site.sh snapshot    # save the pristine database once, so the first-run flow is repeatable
apps/nxerp_platform/browser-tests/run.sh              # everything (about 25 minutes); or: apps/nxerp_platform/browser-tests/run.sh journeys   (one file; "first-run" is the wizard suite)
apps/nxerp_platform/browser-tests/site.sh status | reset | drop
```

`apps/nxerp_platform/browser-tests/run.sh` resets the site to the snapshot, runs the first-run flow (which completes the wizard), creates fake users with `nxerp.tests.e2e_fixtures`, runs `case3`, `journeys`, `flows`, `pages`, `recovery`, always removes the users and restores the site, and copies screenshots to `docs/evidence/phase3/`. Passwords are generated per run and passed through the environment.
Chromium is the one in the bench image; the script installs `playwright-core` into `/tmp` of the container.

**Do not run `apps/nxerp_platform/browser-tests/run.sh` while another browser run, or the bench test suites, are using the same container**: they share the fresh site, port 8001 and the container's CPU, and the second run's resets and fixtures corrupt the first.

## Traps (each one cost time)

- **Site config is cached for up to 60 seconds** in every web worker (`frappe/config.py`, `ttl=60`). `update_site_config(...)` or `bench set-config ...` (the kill-switch `nxerp_stock_login`, test-only apps `nxerp_test_apps`) is therefore seen by the web server **within a minute, not at once**. Tests **poll** for the effect (`wait_until(...)`, up to 80 s) instead of sleeping, and an in-process test that needs a different registry patches `registry.get_registry` instead of using site config. A restart makes a change immediate.
- **`throttle_user_limit`.** Frappe refuses more than 60 new users per hour per site; the suites create many throwaway users. In process, `allow_many_test_users()` raises the limit for that process only. On a site that will run the suites: `bench --site <site> set-config -p throttle_user_limit 100000`. **`-p` matters**: `bench set-config` stores a *string* by default, and a string limit is silently useless. The same flag applies to every numeric setting, including `nxerp_stock_login` (`-p ... 1`). Seven Helpdesk tests failed with `Throttled` on a site that had been through repeated runs (Phase 1 evidence).
- **Never run a fixture or a check with `bench execute`.** It swallows the function's real exception and prints a misleading result, so a broken fixture looks like it worked. Run fixtures with `python -m` from the bench's `sites` directory, as `apps/nxerp_platform/browser-tests/run.sh` does: `cd ~/frappe-bench/sites && E2E_SITE=nxerp-e2e.localhost ../env/bin/python -W ignore -m nxerp.tests.e2e_fixtures setup`. (The documented seeding command for fake dev users, `nxerp.tests.seed_users.seed`, is a `bench execute` call and has no `python -m` entry: it prints one line per user, so check that output.)
- **Do not `pgrep -f` for your own server from a shell that contains the pattern**: the shell matches itself. `apps/nxerp_platform/browser-tests/run.sh` probes the port instead (`curl http://localhost:8001/login`) and kills with a bracketed pattern (`'bench_[h]elper...'`).
- **Git Bash rewrites `/workspace/...`** in command arguments into a Windows path; prefix `MSYS_NO_PATHCONV=1`.
- **Developer mode puts tracebacks in JSON errors**; the dev site has it on, so "no traceback in the response" assertions only run where a production site would behave that way (`no_traceback(...)` in `test_unified_experience.py`).
- **Frappe skips Version records during tests** unless the code saves with `ignore_version=False` (the grant API does, so the audit trail is real).
- **First-run state matters.** Frappe's `desktop:home_page` default is `setup-wizard` until the wizard really finishes; marking setup complete in the database without resetting it made ERPNext reload in a loop on the dev site ([troubleshooting.md](troubleshooting.md)). Fixtures never touch the dev site's setup state.
- A hyphenated `www` page whose controller is not named with underscores is never executed; add a test that the controller's guard really runs.

## What to test for each kind of change

| Change | At least |
| --- | --- |
| New or changed gate rule, route, role | layer 3 decision test, a matrix or HTTP row for the surface, and both a "with grant" and a "without grant" persona; guest too |
| Redirect handling | add the payload to `HOSTILE` in `test_routing.py` (it is reused by the HTTP and browser suites) |
| New app | [`how-to-add-an-app.md`](how-to-add-an-app.md): the checklist test, matrix rows, `check_architecture.py --app-path` |
| Login page or launcher UI | browser test (`apps/nxerp_platform/browser-tests/`) and the accessibility basics in `apps/nxerp_platform/browser-tests/a11y.mjs` |
| Pin bump | `check_pins.py`, rebuild from empty volumes, run layers 3 to 7 |
| Patch or migration | run it twice on a copy and show the second run changes nothing |

## Flaky-test policy

DECISION proposed for the owner to ratify; the project has no flaky-test record to base numbers on yet.

1. **A flaky test is a defect, not noise.** Do not re-run until green, do not add retries to hide it, and do not report a run as passing that needed a second attempt without saying so.
2. **Classify before you fix.** The causes seen here: the 60 s config cache, rate limits and throttles, leftover fixtures from an aborted run, a server that is not ready, two runs sharing one site or port, and time. Fix the cause (poll for the condition, raise the limit in the fixture, purge leftovers, wait for readiness), not the symptom.
3. **Quarantine only with a name and a date.** A test may be skipped with `@unittest.skip("reason, issue #N, owner <team>, review by <date>")` so it is visible in every run; no silent skips, no deleting, and no quarantine longer than two weeks (ASSUMPTION: the owner may set another window).
4. **A fixed test must have been seen to fail first** (or the cause demonstrated), then pass; say so in the PR.
5. CI must not mask failures: no `continue-on-error` on test steps.
