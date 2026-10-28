# CI design (`.github/workflows/ci.yml`)

**Status: NEVER run on GitHub.** Workflow syntax and expressions were checked with `actionlint` 1.7.12 + shellcheck 0.11.0 (clean). The
commands inside were run locally where stated in "What was and was not verified". Timings below are **estimates, not measurements**.

## Required checks

Branch protection requires one check, **`ci-gate`**, which `needs` every job and fails unless each one succeeded (a skipped `codeql` is
accepted only when the owner sets `CODEQL_ENABLED=false`). Job names are stable on purpose: add jobs freely, add them to `ci-gate`'s
`needs`, never rename.

| Job | What it runs | Needs the stack? |
| --- | --- | --- |
| `lint` | pre-commit (hygiene, ruff, bandit, shellcheck), `ruff check/format`, bandit, Conventional Commit check (PR title strict, commits format-only) | no |
| `pins-and-architecture` | `deploy/check_pins.py`, `tools/check_architecture.py`, actionlint, `bash -n` on scripts, `docker compose config` of the staging-like file, `docker buildx build --check` | no |
| `frontend` | Helpdesk SPA (separate repo, checked out at its pin): `yarn install --frozen-lockfile`, `theme:check`, `theme:audit`, `yarn build` | no |
| `nxerp-tests` | every `nxerp/tests/test_*.py` module except the matrix and the ERPNext smoke | yes |
| `access-matrix` | `test_access_matrix`; uploads `docs/security/phase2-matrix.md` as artifact `access-matrix` | yes |
| `erpnext-smoke` | `test_erpnext_smoke` | yes |
| `helpdesk-regression` | `bench run-tests --app helpdesk` with the access layer active | yes |
| `e2e` | Playwright via `e2e/run.sh <suite>`, 6 shards (`first-run journeys flows case3 recovery pages`); uploads `docs/evidence/phase3` per shard | yes (+ fresh e2e site) |
| `fresh-install-migrate` | bootstrap from EMPTY volumes (no cache), apps installed and `nxerp` last, second `migrate`, `healthcheck.sh`, `backup.sh` + `restore.sh` round trip | its own |
| `upgrade-from-previous-tag` | install the previous release tag on empty volumes, seed fake users, switch to this commit on the same volumes, `migrate`, health, a few tests. **Skips with a clear notice when no `vX.Y.Z` tag exists (today)** | its own |
| `dependency-audit` | resolves Frappe + pinned apps' Python deps (`tools/resolve_python_deps.py`), `pip-audit`, `npm audit` (e2e), `yarn audit` (Helpdesk SPA) | no |
| `secret-scan` | gitleaks 8.28.0 CLI image over the full history with `.gitleaks.toml` | no |
| `codeql` | CodeQL for `python` and `javascript-typescript` | no |
| `license-check` | `tools/check_licenses.py` for PyPI metadata of the Python set and npm (`license-checker-rseidelsohn`) for e2e and the SPA against `.github/license-policy/` | no |
| `docker-build` | builds `deploy/docker/Dockerfile` (no push), then asserts `apps.txt` ends with `nxerp` and `bench version` works | no |
| `stack-cache` | helper: builds the shared stack cache when missing; consumed by the stack jobs | builds it |
| `ci-gate` | aggregate | no |

Also: `concurrency` (one run per PR, older runs cancelled), top-level `permissions: contents: read` (only `codeql` gets
`security-events: write`; `release`/deploy workflows get what they need per job), actions pinned to commit SHAs, caches for pre-commit,
pip, yarn, Docker layers (`type=gha`) and the stack volumes.

## Why a volume cache instead of sharing a stack

A bench stack cannot be handed from one GitHub job to another. Options: (a) every stack job bootstraps from scratch: simplest, but each
pays the cold build (408 s measured locally, `docs/PROGRESS.md`; more on a shared runner) seven times; (b) one job runs every test
serially: no duplicate build but the serial test time is far beyond 20 minutes (the browser suite alone took about 25 min); (c)
**chosen:** build the stack once, save its three Docker volumes (bench with all apps installed and built, MariaDB data, vendor clones;
3.9 GB on the dev machine before compression) in `actions/cache` keyed on `hash(deploy/apps.json, versions.env, bootstrap.sh,
compose.yaml, e2e/site.sh)`, restore them in each stack job, run `bench migrate` so the cached site matches the checkout, and run the
test jobs in parallel. A pin change correctly invalidates the cache. `fresh-install-migrate` and `upgrade-from-previous-tag` bypass it on
purpose because they prove installation, not tests.

**Estimate (not measured):** warm cache: restore and start 4-8 min + migrate 1-2 min + the slowest job. If the 25-minute browser suite
splits evenly over six shards, each shard is about 4-6 min, so a PR needs roughly 12-20 minutes of wall clock; `helpdesk-regression`
(569 tests) and `docker-build` (a build with `bench build` of ERPNext and Helpdesk assets) are the two jobs most likely to exceed that and
could not be timed. Cold cache (first run, after a pin change, or after 7 days unused; a weekly scheduled run refreshes it): add 10-15 min
for `stack-cache`, so 25-35 minutes. The 20-minute goal is therefore a design intent that the first real runs must confirm or refute.

## Risks and things that will probably need fixing on the first run

- **Helpdesk pin**: `deploy/apps.json` pins `1c6981cc5`, which predates the platform login. Stack jobs fetch exactly that commit, so the
  nxerp tests/e2e that depend on Phase 3 will fail until the pin is updated to a pushed commit (owner-action-list 3). The fork may be
  private: `HELPDESK_READ_TOKEN` is required then.
- **Known failing today, independent of GitHub:** the local browser run of 2026-10-28 (`/tmp/e2e-full.log`) had failing tests in
  `flows`, `journeys`, `pages` (alt text on the login logo, accessibility) and `recovery`; the `e2e` job will report them.
- The cached site was installed with the random passwords of `deploy/dev/.env`, so that file is saved into the cache with the volumes
  (a throwaway CI stack's values, used nowhere else; readable by anyone who can read the repository's caches).
- **Volume cache** is unproven on GitHub: restoring a MariaDB data directory from a tarball taken after a clean `down` is assumed safe;
  the extracted volume must be about 4 GB of free disk (the jobs free ~25 GB first). If it misbehaves, set the key to something new or
  drop `stack-cache` and let each job bootstrap (the code path exists: no cache hit means a cold start).
- `pre-commit` (all hooks except gitleaks) passed locally on every tracked and new file on 2026-10-28, after the `cd ... || exit` fix in `e2e/*.sh`
  that its shellcheck hook needed (the hook runs on every `*.sh` at `--severity=warning`).
- **Dependency audit** reports advisories (59 in Frappe's resolved set on 2026-10-28) without failing until `AUDIT_ENFORCE=true`.
- **CodeQL** on a private repository needs GitHub Advanced Security.
- `docker-build` on a runner: free disk was a problem in other Frappe CI setups; the job frees space first.
- `gitleaks-action` is not used (it needs a paid licence for organisations); the CLI image is.

## What was and was not verified (FACT)

| Item | Result |
| --- | --- |
| `actionlint` on all workflows | clean |
| YAML parse (python yaml) of workflows, composite actions, dependabot, compose | clean |
| `tools/check_commits.py` | runs; found nine over-long subjects in local history (hence the 150 limit for commits) |
| `tools/changelog.py`, `tools/upstream_watch.py` | ran; real output |
| `pre-commit run --files <all tracked + new files>` with `SKIP=gitleaks` | all hooks passed (ruff, bandit, shellcheck 0.10.0, check-yaml, architecture) |
| `tools/check_licenses.py` | ran on Frappe's resolved set (142 packages): 0 outside policy after tuning, 2 `PENDING` exceptions |
| `pip-audit` on Frappe's resolved set | 59 advisories / 5 packages |
| `pip install --dry-run --report` for Frappe alone | works (143 packages); the all-apps resolution was not run (ERPNext does not check out on Windows: path length) |
| gitleaks 8.28.0 with `.gitleaks.toml` on this repository (22 commits + working tree) | no findings in git history; one finding in the git-ignored local `deploy/dev/.env` (a real local secret, not committed) |
| `docker compose config`, nginx `-t`, `buildx --check` | pass |
| everything that needs GitHub (runners, caches, artifacts, environments, secrets, CodeQL, the cache restore) | **not run** |
