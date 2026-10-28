# Day-1 developer onboarding

Goal: by the end of day one you have the repository, a running dev platform (ERPNext + Helpdesk + `nxerp` on one site), fake users,
a green local test run, and a first pull request opened. Read [CLAUDE.md](../../CLAUDE.md) first: it holds the non-negotiable rules
(naming, "hiding an icon is not security", no cross-app imports, no secrets, no unverified claims).

This guide has been followed literally from a clean clone. What was and was not executed there is recorded at the end in
[Verification of this guide](#verification-of-this-guide); steps that need the Docker stack are marked **[stack]**.

## 0. What you are working on, in five lines

- **NXERP** is the umbrella platform; **ERPNext** is the ERP app inside it; **Helpdesk** is a separate support app; **Frappe** is the framework. Helpdesk is never "NXERP". HRMS and other future apps are **not installed** and are shown nowhere.
- This repo holds the `nxerp` platform app (`nxerp/`), the pinned build (`deploy/`), CI (`.github/`) and docs (`docs/`). Frappe and ERPNext are pinned upstream tags, never vendored. Helpdesk is a separate company fork in a sibling folder.
- `nxerp` owns the one `/login`, the post-login router `/nxerp/go`, the launcher `/nxerp/apps`, the no-access page, and a server-side app gate. Overview: [`../architecture/overview.md`](../architecture/overview.md).
- Access is Frappe roles (`NXERP Access: ERPNext`, `NXERP Access: Helpdesk`); the gate only denies on top of Frappe's permissions.
- Apps never import each other or `nxerp`; `nxerp` imports no app and declares no `required_apps`. A tool enforces it.

## 1. Prerequisites

| Need | Version / note | Why |
| --- | --- | --- |
| Git | any recent (2.47 was used) | clone, branches |
| Docker with Compose v2 | Docker Desktop 29.x, Compose v5.1.4 was used; give Docker at least 8 GB RAM | the dev stack is Docker-only: `bench` and MariaDB do not run natively on Windows (ADR-006) |
| Disk | tens of GB free (ASSUMPTION: about 30 GB; the dev workstation had 12 GB free and was tight) | images and three named volumes |
| Python **3.14** on the host | needed for the host-side checks only (`deploy/check_pins.py`, `tools/check_architecture.py`, the architecture unit test). The checker needs `tomllib` (3.11+; Python 3.7 failed with `ModuleNotFoundError` when tried) and parses the platform's 3.14-only `except A, B:` syntax (ASSUMPTION for 3.11 to 3.13: not tried) | the platform targets 3.14 (`pyproject.toml`) |
| Node | **not needed** on the host | the browser suite runs inside the container with its own Node 24 and Chromium |
| `gh` (GitHub CLI) | optional, for opening PRs | |
| Windows | run everything from **Git Bash** (or WSL). On Windows the interpreter is usually `python`, not `python3`; use whichever prints 3.14 | |

Check them:

```bash
git --version
docker --version && docker compose version
python --version        # or python3 --version; must say 3.14.x for the host checks
```

Docker Desktop must be running. Clone **outside OneDrive or another synced folder** where you can (a synced folder locked `.git` during a rename, ADR-006); the bench itself lives in a Docker volume and is unaffected.

## 2. Clone the code (one workspace, two repositories)

Everything lives side by side in one folder (ADR-001); the dev stack mounts both:

```
nxerp-workspace/
  nxerp-platform/   this repo (company repo Sria-Infotech-Pvt-Ltd/NxERP)
  helpdesk/         the Helpdesk fork (Sriainfotech/Frappe-Help-Desk)
```

```bash
mkdir nxerp-workspace && cd nxerp-workspace
git clone https://github.com/Sria-Infotech-Pvt-Ltd/NxERP.git nxerp-platform
git clone https://github.com/Sriainfotech/Frappe-Help-Desk.git helpdesk
```

**Current limitation (FACT, checked 2026-10-28 with `git ls-remote`):** the GitHub remote holds only `main` (an initial commit with a README) and the Helpdesk work for the unified
login is on a local branch (`feature/nxerp-platform-login`) that is on no remote. Until the owner publishes the phase branches
([`../governance/owner-action-list.md`](../governance/owner-action-list.md)), the platform code comes from whoever holds the local repository: clone it from their path or a git bundle,
then check out the branch you are told to work on (today `phase-4/release-readiness`):

```bash
git clone --branch phase-4/release-readiness <path-or-bundle-of-the-local-repo> nxerp-platform
git clone --branch feature/nxerp-platform-login <path-or-bundle-of-the-local-helpdesk-repo> helpdesk
```

`up.sh` installs the Helpdesk branch that is **checked out in `../helpdesk`**; without that folder it builds the pinned fork commit from `deploy/apps.json`, which is Helpdesk before the unified-login work
([`../guides/troubleshooting.md`](../guides/troubleshooting.md), section 8). Only committed work is installed, so commit in `helpdesk/` before rebuilding.

## 3. Host-side checks (about a minute, no Docker)

From the repo root:

```bash
python -I deploy/check_pins.py                                  # pins are exact commits, nxerp is last
python -I tools/check_architecture.py                           # architecture rules (ADR-005)
python -I tools/check_architecture.py --app-path helpdesk=../helpdesk   # also: no app imports nxerp, no platform code in Helpdesk
python -m unittest nxerp.tests.test_architecture                # the checker and a proof that it catches violations
```

Expected (wording may change as the checks grow): `OK: 5 apps pinned, versions.env complete`; `OK: nxerp imports no other app ... SKIPPED the other-app checks ...` (without `--app-path` it says plainly that it did not check the other apps);
`OK: ... checked other apps: helpdesk`; `Ran 17 tests ... OK`. On a Windows host whose `python3` is the Microsoft Store stub ("Python was not found"), use `python`.

Lint and formatting (ruff is what CI's pre-commit runs):

```bash
python -m venv .venv
. .venv/Scripts/activate          # Linux/macOS: . .venv/bin/activate
pip install ruff pre-commit bandit
ruff check . && ruff format --check .
pre-commit install                # ruff, ruff-format, bandit, shellcheck, gitleaks, file hygiene
pre-commit run --all-files
```

The first `pre-commit run` clones the hook repositories and builds `gitleaks` (needs network; several minutes); the `shellcheck` hook runs a small Docker image, so Docker must be up. `.venv/` is git-ignored. **As of 2026-10-28 two hooks fail on a clean checkout of this branch** (the `shellcheck` warnings in `e2e/*.sh` and `deploy/dev/up.sh`, and the `nxerp-architecture` hook on a host without a `python3` command): see the verification section; if they still fail when you read this, report it rather than skipping the hook.

## 4. Bring up the dev platform [stack]

```bash
./deploy/dev/up.sh -d
docker compose -p nxerp-dev logs -f bench       # wait for the line "[bootstrap] ready:"
```

- `up.sh` creates `deploy/dev/.env` with **random** passwords on first run (git-ignored; it holds the Administrator and MariaDB root passwords; never share or commit it), then starts the compose project `nxerp-dev`.
- A build from empty volumes took **408 s and 418 s** in Phase 1 with warm Docker caches ([`../audit/bootstrap-evidence.md`](../audit/bootstrap-evidence.md)); a first-ever run on a new machine downloads more.
- Site: <http://nxerp.localhost:8100> (ERPNext Desk at `/desk`, Helpdesk at `/helpdesk`, login at `/login`); realtime on port 9100. Sign in as `Administrator` with the password from `deploy/dev/.env`.
- The first-run setup wizard is **pending by design**; the platform sends the Administrator to Desk so the wizard can run.
- Stop: `./deploy/dev/up.sh down` (volumes kept). **Never** `docker compose down -v` to "fix" something: it destroys the dev site and database. The bench is in a named volume; your repo edits are visible in the container at once (`nxerp` is soft-linked from the `/workspace` mount), but the web process may need `docker restart nxerp-dev-bench-1` to load Python and hook changes.
- Ports 8100 and 9100 and the project name `nxerp-dev` are chosen so this stack does not collide with other Frappe stacks. Do not start a second copy of the stack.

## 5. Seed fake users [stack]

```bash
read -rs NXERP_SEED_PASSWORD; export NXERP_SEED_PASSWORD      # type a password; it is not echoed
docker compose -p nxerp-dev exec -T -e NXERP_SEED_PASSWORD bench bash -lc \
  'cd frappe-bench && bench --site nxerp.localhost execute nxerp.tests.seed_users.seed'
```

Creates `admin@`, `agent@`, `manager@`, `erpuser@`, `customer@example.test` (a System Manager, a Helpdesk Agent, an Agent Manager, an ERPNext user holding `NXERP Access: ERPNext`, and a
customer). Omit the variable to have one generated and printed once. The script refuses to run unless `developer_mode` is on. Sign in as each at `/login` and see where you land:
`agent@` and `manager@` to Helpdesk, `erpuser@` to ERPNext, `customer@` to the customer portal, and `admin@` (a System Manager, who is deliberately granted no app) to the "No access" page, which links to *Manage user access*.
No seeded user holds two apps: in Desk, give `manager@` the role `NXERP Access: ERPNext` and sign in again to see the launcher.

## 6. Run the tests

| What | Command | Needs |
| --- | --- | --- |
| Architecture unit tests | `python -m unittest nxerp.tests.test_architecture` | host only |
| All `nxerp` integration, matrix and HTTP tests [stack] | `docker compose -p nxerp-dev exec -T -e NXERP_ADMIN_PASSWORD bench bash -lc 'cd ~/frappe-bench && bench --site nxerp.localhost run-tests --app nxerp'` (run `set -a; . deploy/dev/.env; set +a` first so the Administrator password is exported) | the stack |
| One module [stack] | the same with `--module nxerp.tests.test_routing` | the stack |
| Browser suite [stack] | `e2e/site.sh create`, `e2e/site.sh snapshot` once (about 10 minutes), then `e2e/run.sh` (about 25 minutes) | the stack; uses its own fresh site, never the dev site |

On Windows Git Bash prefix `MSYS_NO_PATHCONV=1` to commands that contain a `/workspace/...` path. Do not run two heavy things in the container at the same time (the browser suite and the bench tests share it).
The layers, the traps (60-second config cache, `throttle_user_limit`, never `bench execute` for fixtures) and the flaky-test policy are in [`../guides/testing.md`](../guides/testing.md).

## 7. Make a change

1. Branch off `main` (or the branch you were told to base on): `git switch -c fix/<area>-<summary>` (`feat/`, `docs/`, `chore/` too).
2. Edit. Python uses **tabs** and the ruff config in `pyproject.toml`; see [`../guides/coding-standards.md`](../guides/coding-standards.md). Add the test with the change: a new access rule needs a "with grant" and a "without grant" test and a matrix or HTTP row ([`../guides/security-guidelines.md`](../guides/security-guidelines.md)).
3. Run the host checks of section 3 and the relevant tests of section 6.
4. Changing a version pin, an access rule, a route or an architecture rule? Update the matching ADR in the same change ([`../adr/README.md`](../adr/README.md)). Adding an app? [`../guides/how-to-add-an-app.md`](../guides/how-to-add-an-app.md).
5. Commit small and conventional: `git commit -m "fix(access): <what and why in one line>"`. Never commit `.env`, secrets, customer or personal data.

## 8. Open a pull request

```bash
git push -u origin <your-branch>
gh pr create --fill          # or open it on GitHub
```

- Fill in the PR template: what and why, the scope check, **evidence** (paste what you ran and saw; "should work" is not evidence), rollback. Say which checks you ran locally and which only CI ran.
- Required: at least one approval and a code owner for sensitive paths (`nxerp/`, `deploy/`, `.github/`, `docs/adr/`), CI green. `main` is protected; never push to it or force-push shared history.
- **Current limitation:** the GitHub account on the dev machine has READ permission on the repository, so pushes and PRs need an account with write access or a fork. Whether branch protection and CI are active is for the owner to confirm ([`../governance/owner-action-list.md`](../governance/owner-action-list.md)); this guide does not claim they are.

## 9. Where to read, and where to ask

| Need | Go to |
| --- | --- |
| Index of every doc | [`../README.md`](../README.md) |
| How it fits together | [`../architecture/overview.md`](../architecture/overview.md), [`../architecture/routes.md`](../architecture/routes.md) |
| Why it is built this way | [`../adr/README.md`](../adr/README.md) |
| What is done, what is open | [`../PROGRESS.md`](../PROGRESS.md) |
| Something broke | [`../guides/troubleshooting.md`](../guides/troubleshooting.md), [`../runbooks/login-recovery.md`](../runbooks/login-recovery.md) |
| Who owns what, who reviews | [`../governance/ownership.md`](../governance/ownership.md) and `CODEOWNERS` (the GitHub team names there are placeholders until the owner creates the teams) |
| A rule or decision is unclear | open a draft PR or an issue and tag the code owners named for that path; for an architecture question quote the ADR number |

No chat channel or mailing list is documented anywhere in this repository; ask the owner for the team's channel and add it here.

## Day-1 checklist

- [ ] Read CLAUDE.md, the overview and the ADR index
- [ ] Workspace cloned (platform and Helpdesk side by side)
- [ ] Host checks pass (section 3)
- [ ] Dev stack is up and you signed in as Administrator [stack]
- [ ] Fake users seeded; you signed in as each persona and saw the landing page [stack]
- [ ] `nxerp` tests pass locally [stack]
- [ ] A small change made on a branch with a test, committed conventionally
- [ ] A pull request opened (or a draft, if you lack write access)

## Verification of this guide

Followed literally on 2026-10-28 on the Windows 11 dev workstation, from Git Bash, in a **fresh clone** under `C:\Users\darla\dev\onboarding-test\nxerp-workspace\`
(`nxerp-platform/` and `helpdesk/` side by side, left in place). A second Docker stack could not be started (compose project `nxerp-dev` and ports 8100/9100 were in use by the running one), so
steps marked [stack] were **not** re-executed in the clone. Statements below are what was run and seen.

**Clone.** `git clone --branch phase-4/release-readiness <local path> nxerp-platform` (HEAD `bb859fa`) and `git clone --branch feature/nxerp-platform-login <local path> helpdesk` (HEAD `3897718c6`) both worked.
A clone from GitHub was **not** done because the remote holds only `main` (checked with `git ls-remote`). The documentation, `tools/check_architecture.py` and the two new test files had not been committed yet and were copied into the clone.

**Executed in the clean clone (all from the repo root):**

| Step | Result |
| --- | --- |
| `git --version`, `docker --version`, `docker compose version`, `python --version` | git 2.47.1, Docker 29.6.1, Compose v5.1.4, Python 3.14.3. `python3` printed "Python was not found" (the Microsoft Store stub): on this host the command is `python` (now stated in the guide) |
| `python -I deploy/check_pins.py` | `OK: 5 apps pinned, versions.env complete` |
| `python -I tools/check_architecture.py` | `OK: nxerp imports no other app, declares no required_apps, and the repo holds one app; SKIPPED the other-app checks (R3, R4b) ...` |
| `python -I tools/check_architecture.py --app-path helpdesk=../helpdesk` | `OK: ... checked other apps: helpdesk` (the Helpdesk branch `feature/nxerp-platform-login`: no import of `nxerp`, no platform code) |
| Python 3.7.0 `-I tools/check_architecture.py` | `ModuleNotFoundError: No module named 'tomllib'` (so the host needs a modern Python) |
| `python -m unittest nxerp.tests.test_architecture` | `Ran 17 tests ... OK` |
| `python -m venv .venv`, `pip install ruff pre-commit bandit` | ruff 0.17.3 installed |
| `ruff check .` and `ruff format --check .` | `All checks passed!`; `52 files already formatted` |
| `pre-commit install`, `pre-commit run --all-files` (hook cache kept in `..\pre-commit-cache`, first run 7 min 16 s, second run 11 s) | **14 hooks passed**, including ruff (import sorter, linter, formatter), bandit, gitleaks (built from source by pre-commit), detect-private-key and the file-hygiene hooks. **2 failed**, see below |
| `docker compose --env-file deploy/versions.env --env-file <placeholders> -f deploy/dev/compose.yaml config -q` (validation only, nothing started) | exit 0 |
| `bash -n` on `deploy/dev/up.sh`, `deploy/dev/bootstrap.sh`, `e2e/run.sh`, `e2e/site.sh` | all parse |
| `docker compose -p nxerp-dev ps` from the clone root (no compose file there) | lists the running stack: the `-p nxerp-dev logs/exec` commands in this guide need no `-f` |

**The two failing pre-commit hooks (findings, not fixed here):**

1. `shellcheck` (runs the `koalaman/shellcheck:v0.10.0` Docker image, 19.3 MB, pulled by the hook): three warnings at the configured severity: `e2e/run.sh` line 12 and `e2e/site.sh` line 11 (SC2164, `cd` without `|| exit`) and `deploy/dev/up.sh` line 28 (SC2155, declare and assign separately). CI's lint job runs the same hook, so it would fail on these.
2. `nxerp-architecture` (`entry: python3 -I tools/check_architecture.py`, `language: system`): exit code 9009 on this host because `python3` is the Store stub. The check itself passes when run as `python -I` (above). A `language: python` hook, or an entry that works on both, would fix it.

**Not re-executed in the fresh clone (needs the bench container).** `./deploy/dev/up.sh -d` (bring-up), seeding users, `bench run-tests`, `e2e/run.sh`. Their record:

- Bring-up from empty volumes: 408 s and 418 s, `[bootstrap] ready:` seen ([`../audit/bootstrap-evidence.md`](../audit/bootstrap-evidence.md) sections 2 and 8). **Not** re-run today.
- Seeding the five fake users: executed in Phase 1 ([`../audit/bootstrap-evidence.md`](../audit/bootstrap-evidence.md) section 5). **Not** re-run today; the `-e NXERP_SEED_PASSWORD` form given in section 5 above is a rewrite of the documented command and was **not** executed.
- The `nxerp` test suite and the browser suite: results are in [`../PROGRESS.md`](../PROGRESS.md) (Phase 3) and in the lead's runs. Run today **in the existing dev container** (not in the clone; its `/workspace` is the original working tree): `bench --site nxerp.localhost run-tests --app nxerp --module nxerp.tests.test_add_app_checklist` gave `Ran 31 tests ... OK`, and `--module nxerp.tests.test_architecture` gave `Ran 17 tests ... OK`. One extra attempt of the 31-test module failed in `setUpClass` with a database error while another test suite was running in the same container; it passed when rerun (see "One bench test run per site at a time" in [`../guides/testing.md`](../guides/testing.md)).

**Also not verified:** a clone from GitHub (nothing is published), opening a pull request (the account on this machine has READ access only), `pre-commit` on Linux or macOS, the guide on a machine that has never run the stack, and the disk estimate in section 1.
