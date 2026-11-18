# NXERP workspace restructure: audit and plan

Status (2026-10-29): **Part B is done and pushed to `develop`.** This file is the audit and plan as written before the work; the sections below are kept as history. What was actually done, kept or reverted is in the final report in the pull request / `docs/PROGRESS.md`. The 14 uncommitted Helpdesk files (section 1, D3) were later applied to `develop` on the owner's instruction. Baseline logs: `baseline/`.
Audit date: 2026-10-28. Written for: the owner and the engineers who will review the restructure.
Labels: **FACT** = verified by a command in this audit. **ASSUMPTION** = not verified. **DECISION** = needs the owner.

Baseline commands and raw outputs are saved in `docs/restructure/baseline/` (next to this file).

---

## 0. Read this first: five findings that change the plan

| # | Finding | Effect on the target hierarchy |
|---|---|---|
| 1 | **The platform's Frappe app is named `nxerp`, not `nxerp_platform`** (`hooks.py` `app_name = "nxerp"`, package `nxerp/`). Dotted paths such as `nxerp.enforcement.auth_hook` sit in `hooks.py`; the site database stores the installed app name and the patch log entry `nxerp.patches.create_access_roles`; routes and assets are `/nxerp/...` and `/assets/nxerp/...`. | Renaming the package is a Tier 3 violation and would change behaviour on every existing site. **The package stays `nxerp`.** Only the outer folder is named `apps/nxerp_platform/`. |
| 2 | **`realtime/` cannot be renamed.** Frappe's realtime server loads `../../<app>/realtime/handlers.js` by hard-coded path (`apps/frappe/realtime/index.js:54`, read in the pinned Frappe v16.53.0 inside the dev container). | `hd-realtime/` is **not created**. `realtime/` stays and gets a README. Renaming would silently disable Helpdesk's socket handlers (ticket viewers, typing, ping). |
| 3 | **The target is a monorepo; ADR-001 (Accepted) rejected a monorepo.** `bench get-app <url>` needs an app at the repository root. Also, Helpdesk's frontend links `@framework/ui` as `link:../../frappe/ui` and `socket.ts` imports `../../../../sites/common_site_config.json`, so Helpdesk must be a **real copy inside `bench/apps/`**, not a soft link. | The layout is workable, but the install tooling must change (see section 6, "non-rename edits"). Those edits are not renames. **You must approve them explicitly.** A new ADR-007 will supersede ADR-001. |
| 4 | **The Helpdesk working copy `helpdesk/` has 14 files of uncommitted work** that exists in no commit. It is a partial port of the `nxerp-stable` line ("Assignee follows Team" plus "System Manager / Agent Manager see every ticket"). It is **not** in the pinned commit. | It would change behaviour, so by the strict rule it is **not** carried into `develop`. It is preserved as a patch in `_archive/`. Your call (section 7). |
| 5 | **`handoff/helpdesk-fork.bundle` is 62.7 MB** (limit: 50 MB). | It cannot be committed. `docs/handoff/` will hold a README only; the bundles go to `_archive/`. |

---

## 1. Audit: every item in the workspace

| Item | Git repo? | Remote | Branch / last commit | Uncommitted | Contents | Verdict |
|---|---|---|---|---|---|---|
| `nxerp-platform/` | yes | `origin` = company `NxERP` | `phase-4/release-readiness` @ `1253473` (2026-10-28), equals the remote | none (clean; ignored: `.env`, `.env.seed-users`, `__pycache__`) | Platform app `nxerp`, `deploy/`, `tools/`, `e2e/`, `docs/`, `.github/`, 286 files, 5.7 MB | **Canonical platform source** |
| `helpdesk/` | yes (the only real Helpdesk git dir) | `origin` = upstream `frappe/helpdesk`; `company` = fork under `Sriainfotech/Frappe-Help-Desk` | checked out: `feature/nxerp-platform-login` @ `3897718`. Also holds `phase-4/helpdesk-parity` @ `8f77254` (23 commits ahead of upstream base `58b82a6e2`, 2026-10-11) | **14 modified files** (+182/-34), nothing untracked | Helpdesk app, 1,128 files, 30.8 MB (excluding `node_modules`) | **Canonical Helpdesk history** |
| `helpdesk-parity/` | no own repo: a **linked worktree** of `helpdesk/` whose link file points at the old workspace name (`frapper sria`), so `git` fails inside it ("prunable") | n/a | `phase-4/helpdesk-parity` @ `8f77254`, equals `company/phase-4/helpdesk-parity` | **none**: compared against its index, only the 2 parity commits differ from `3897718` | Same tree as `helpdesk/` plus the "unseen tickets" badge (5 files) | **Not canonical: archive** (it is a copy of a commit already on the remote) |
| `NXERP/nxerp/` | yes, **zero commits**, branch `master`, remote = company `NxERP` | `origin` | none | all files untracked | Earlier `nxerp` app: login override, `branding.py`, CSS, 8 images (4 MB) | **Leftover of the rejected earlier attempt: archive** (see below) |
| `frappe-helpdesk-docker/` | no | n/a | n/a | n/a | `docker-compose.yml`, `init.sh`: upstream quick-start, identical to `helpdesk/docker/` except 4 lines in `init.sh`; holds upstream demo DB/admin passwords (public defaults, not company secrets) | Keep as `deploy/docker/helpdesk-local-dev/` (copy). **Three containers from it are running now**, so the original stays until you stop that stack |
| `handoff/` | no | n/a | n/a | n/a | `helpdesk-fork.bundle` (62.7 MB), `nxerp-platform.bundle` (4.6 MB) | Older snapshots (see bundles). Bundles to `_archive/`; README in `docs/handoff/` |
| `nxerp-phase-2-access-layer.bundle` | n/a | n/a | one head: `phase-2/access-layer` @ `1d90f11` | n/a | 216 KB bundle | Superseded: archive |
| 5 loose notes (`FRAPPE_HELPDESK_KNOWLEDGE_MAP.md`, `FRAPPE_HELPDESK_PIPELINE.md`, `HELPDESK_PIPELINE.html`, `HELPDESK_MASTERY_GUIDE.md`, `HELPDESK_TEST_PLAYBOOK.md`) | no | n/a | n/a | n/a | Reference notes, 35 to 70 KB each | Move to `docs/reference/` (renamed). The knowledge map has **16 absolute `file:///c:/Users/<user>/...` links**; the target repo is public |

### Which Helpdesk copy is canonical (FACT)

- Lineage: `3897718` (`feature/nxerp-platform-login`) is an ancestor of `8f77254` (`phase-4/helpdesk-parity`), which is 2 commits ahead. `feature/nxerp-login-page` is also an ancestor.
- `8f77254` is on the company remote and is the commit pinned in `deploy/apps.json`. **The new `apps/helpdesk/` is the tree of `8f77254`.**
- `helpdesk-parity/` adds nothing that is not in `8f77254`. `helpdesk/` is the real git directory: it holds every branch and both remotes.

### Uncommitted work in `helpdesk/` (FACT)

- 14 files: 5 SPA files (`AssignTo.vue`, `TicketDetailsTab.vue`, `useTicket.ts`, `MobileTicketAgent.vue`, `TicketNew.vue`) and 9 backend/test files (`utils.py` adds `is_ticket_admin`, `api/auth.py`, `dashboard.py`, `ticket_stats.py`, `extends/comment.py`, `hd_ticket.py` and three test files).
- It overlaps `company/nxerp-stable` (commit `473a4d871` "Assignee follows Team"; `a9949febb` "System Manager and Agent Manager see every ticket"), which is a different, Frappe 15 line.
- The dev container was running **parity + these 14 files**. So the dev site's visible behaviour includes this work, and the pinned commit does not.
- Saved copies: `_baseline/uncommitted-helpdesk.patch` (and the same diff from the container).

### NXERP: leftover or not? (FACT: leftover)

- Empty git history; `ADR-001` and `ADR-005` already record it as "not used, Phase 2 input"; the same package name `nxerp` would collide with the real app.
- Its login, branding and theme CSS were superseded by `nxerp-platform` (`www/login`, `nxerp_login/`, generated theme). Two CSS files are byte-identical copies of files in the platform.
- It has **assets found nowhere else** (`bg-control-room.jpg`, `bg-office.jpg`, `bg-skyline.png` 3.3 MB, logo and favicon PNGs, `nxerp-login.css`). They go to `_archive/` intact, not deleted.

### Bundles (`git bundle list-heads`, FACT)

| Bundle | Heads | Verdict |
|---|---|---|
| `nxerp-phase-2-access-layer.bundle` | `phase-2/access-layer` `1d90f11` | Local branch is `7c41d8d`; trees differ. Older snapshot |
| `handoff/nxerp-platform.bundle` | `phase-1..4` (`3f1780a`, `1d90f11`, `bb859fa`, `1c37157`) and tag `v0.1.0-pre.1` | 28 commits on phase-4 versus 39 on the remote. Tree differs by 22 files (mostly executable-bit changes, 7 added and 3 removed lines). Older snapshot, **tag is not on the remote** |
| `handoff/helpdesk-fork.bundle` | `feature/nxerp-platform-login` `3897718`, `phase-4/helpdesk-parity` `8f77254` | Both heads are on the company remote. Redundant. 62.7 MB |

The tag `v0.1.0-pre.1` exists only in the handoff bundle. It goes to `_archive/` with the bundle; tell me if you want it re-created in the new repo.

### The real platform app (FACT)

`nxerp-platform/` root **is** the Frappe app: `pyproject.toml` (`name = "nxerp"`, flit) plus package `nxerp/`:

```
nxerp/  hooks.py modules.txt patches.txt __init__.py
        access.py enforcement.py guard.py routing.py launcher.py registry.py audit.py install.py migration.py   (flat modules)
        api/access.py   config/   patches/create_access_roles.py   templates/   public/{css,nxerp_login}
        www/login.*  www/nxerp/{apps,go,no-access,test-app}.*
        nxerp_platform/  (the Frappe module folder for modules.txt "NXERP Platform", holds a .frappe marker)
        tests/  (15 test files)
```

It has **no** `access/`, `login/`, `launcher/`, `branding/` sub-packages today. Login and launcher are `www/` pages plus flat modules.

---

## 2. Baseline (FACT; run 2026-10-28 on the dev stack)

Pinned state under test: helpdesk `8f77254e9f` (clean), nxerp `1253473953` (`phase-4/release-readiness`), frappe `e8d41dd006` (v16.53.0), erpnext `ade850bbd6` (v16.52.1). Site `nxerp.localhost`.

| # | Check | Command | Result |
|---|---|---|---|
| B1 | Platform backend tests | `bench --site nxerp.localhost run-tests --app nxerp` | **211 tests, OK** (368 s) |
| B2 | Helpdesk backend tests | `bench --site nxerp.localhost run-tests --app helpdesk` | **574 tests, OK** (275 s) |
| B3 | Frontend build | `bench build --app helpdesk` | **rc 0** (76 s) |
| B4 | Theme checks | `cd desk && NXERP_PUBLIC=/workspace/nxerp/public/css yarn theme:check` and `yarn theme:audit` | **rc 0 / rc 0** (384 tokens covered, 99 contrast checks, 27 palette files tracked). *First run failed because of a stray git-ignored `desk/src/theme/theme/` copy left in the container by an earlier `docker cp`; I moved it to `/home/frappe/stray-artifacts/`, the repo was not at fault* |
| B5 | Platform lint | `python -m ruff check .` and `python -m ruff format --check .` (ruff 0.16.9) | **All checks passed / 58 files formatted** |
| B6 | Architecture rules | `python -I tools/check_architecture.py --app-path helpdesk=../helpdesk-parity` | **OK, rc 0** |
| B7 | Pin check | `python -I deploy/check_pins.py` | OK: 5 apps pinned |
| B8 | Shell syntax | `bash -n` on `deploy/**/*.sh`, `e2e/*.sh`, `tools/*.sh` | all ok |
| B9 | HTTP smoke | `NXERP_BASE_URL=http://localhost:8100 bash deploy/scripts/smoke.sh` | **8/8 OK** |
| B10 | Helpdesk Playwright discovery | `npx playwright test --list` in the Helpdesk root | **174 tests in 30 files** (output hash `469b448e`). The suite itself needs a seeded bench site: **not run** |
| B11 | Helpdesk e2e typecheck | `tsc --noEmit -p e2e/tsconfig.json` | rc 2 with 2 **pre-existing** errors (`filter.spec.ts` 24 and 25); recorded as baseline, not fixed |
| B12 | Platform browser suite | `e2e/run.sh` (Chromium in the bench container, fresh site `nxerp-e2e.localhost`) | **Failed at baseline**: the first-run flow errored on the reset e2e site (a Frappe `System Settings` mandatory-field error) and later suites also failed; the run was stopped before finishing. Not a usable baseline. |

Not run, and why: Helpdesk's own Playwright suite (needs a seeded site and a Playwright browser set; discovery only), Helpdesk's pre-commit `black`/`flake8`/`isort`/`semgrep` (not installed here), GitHub Actions (never ran on GitHub; `ci.yml` says so itself), the staging and production deploy scripts (no target).

**Side effects of the baseline on the machine (no repo file was modified):** recreated the `nxerp-dev-bench-1` container (its `/workspace` mount was dead because the folder was renamed, so `apps/nxerp` was a broken link; data volumes untouched); in the container's Helpdesk checkout I ran `git stash -u` (stash message "pre-baseline dev-container state") and checked out `8f77254`; moved the stray theme folder; ran the browser suite, which resets and re-seeds the separate e2e site. Section 8 says how this is restored.

---

## 3. Target hierarchy: what changes and why

The target is kept, with three adjustments the audit forces:

1. `apps/nxerp_platform/` contains `pyproject.toml`, `README.md` and the package **`nxerp/`** (not `nxerp_platform/`): see finding 1.
2. **No sub-packages** `access/ login/ launcher/ branding/ api/` are created (architecture rule 4 allows moving code only if tests prove nothing changes). Moving a flat module to a package changes its dotted path in `hooks.py` (Tier 3) and in tests. I would not do that inside a rename-only restructure. `docs/architecture/code-map.md` maps each function to its current path, and the follow-up is recorded in `docs/PROGRESS.md`.
3. `hd-realtime/` is not created: finding 2.

Everything else follows your tree. Extras that exist today and have no slot in your tree keep their place or get the nearest one:

- `docs/{acceptance,audit,evidence,governance,guides,onboarding,parity,research}`: stay as they are (Tier 1), listed in `docs/README.md`.
- `deploy/{versions.env,check_pins.py,scripts/,docker/Dockerfile+build.sh+entrypoint.sh+install_apps.sh,README.md}`: stay (production image and operations scripts, not named in your tree).
- Platform `e2e/` becomes `apps/nxerp_platform/browser-tests/` so it cannot be confused with Helpdesk's `hd-e2e-tests/` (same-or-near-identical names are forbidden).
- `tools/` becomes `scripts/`.

---

## 4. Old path to new path

Tier: **1** free rename, **2** rename only with proof, **3** never renamed (moved as a whole, name unchanged).

### Workspace level

| Old | New | Tier | Note |
|---|---|---|---|
| `nxerp-platform/` + `helpdesk/` (commit `8f77254`) | `NxERP/` (fresh clone of the company repo, branch `develop`) | 1 | `develop` starts at `origin/phase-4/release-readiness` (keeps platform history); Helpdesk enters as a **snapshot**, no upstream history |
| `NXERP/` | `_archive/NXERP-earlier-attempt/` | 1 | whole folder, including its empty `.git` |
| `helpdesk-parity/` | `_archive/helpdesk-parity-worktree/` | 1 | |
| `nxerp-phase-2-access-layer.bundle` | `_archive/bundles/` | 1 | |
| `handoff/*.bundle` | `_archive/bundles/` | 1 | `handoff/` in the repo becomes a README |
| 5 loose notes | `NxERP/docs/reference/` (names below) | 1 | originals then moved to `_archive/loose-notes/` |
| `frappe-helpdesk-docker/` | `NxERP/deploy/docker/helpdesk-local-dev/` | 1 | **copy**; original stays until its 3 running containers are stopped |
| `helpdesk/` and `nxerp-platform/` (originals) | untouched in Part B; moved to `_archive/` only after your go-ahead | 1 | the dev stack mounts them |
| uncommitted work in `helpdesk/` | `_archive/helpdesk-uncommitted-work/` (patch + README) | n/a | not in `develop` unless you say so |

Loose notes: `FRAPPE_HELPDESK_KNOWLEDGE_MAP.md` to `helpdesk-knowledge-map.md`; `FRAPPE_HELPDESK_PIPELINE.md` to `helpdesk-pipeline.md`; `HELPDESK_PIPELINE.html` to `helpdesk-pipeline.html`; `HELPDESK_MASTERY_GUIDE.md` to `helpdesk-mastery-guide.md`; `HELPDESK_TEST_PLAYBOOK.md` to `helpdesk-test-playbook.md`.

### Inside the repo

| Old (in `nxerp-platform`) | New | Tier |
|---|---|---|
| `nxerp/` | `apps/nxerp_platform/nxerp/` (package name unchanged) | 3 (moved, not renamed) |
| `pyproject.toml` | `apps/nxerp_platform/pyproject.toml` | 3 (moved) |
| (new) | `apps/nxerp_platform/README.md` (pyproject says `readme = "README.md"`) | 1 |
| `e2e/` | `apps/nxerp_platform/browser-tests/` | **2** |
| `tools/` | `scripts/` | **2** |
| `deploy/dev/compose.yaml` | `deploy/docker/compose/dev.compose.yaml` | **2** |
| `deploy/staging-like/{compose.yaml,nginx.conf.template}` | `deploy/docker/compose/staging-like.compose.yaml`, `.../staging-like.nginx.conf.template` | **2** |
| `deploy/dev/{up.sh,bootstrap.sh}` | `deploy/bootstrap/{up.sh,bootstrap.sh}` | **2** |
| `deploy/environments/*`, `deploy/staging-like/.env.example` | `deploy/env/` (templates only) | **2** |
| `deploy/dev/.env`, `.env.seed-users` | **never copied** (git-ignored local files with generated passwords) | n/a |
| `.github/ .gitignore .editorconfig .pre-commit-config.yaml CODEOWNERS CONTRIBUTING.md CLAUDE.md README.md .gitleaks.toml .dockerignore .gitattributes` | same place; **contents edited for new paths** | 3 / 1 |
| `docs/**` | same place (plus new files, section 6) | 1 |

| Old (Helpdesk, tree of `8f77254`) | New | Tier |
|---|---|---|
| `helpdesk/` (Python package) | `apps/helpdesk/helpdesk/` | 3 |
| `desk/` | `apps/helpdesk/hd-frontend/` | **2** |
| `e2e/` | `apps/helpdesk/hd-e2e-tests/` | **2** |
| `docker/` | `apps/helpdesk/hd-docker/` | **2** |
| `realtime/` | `apps/helpdesk/realtime/` **unchanged** (+ README) | 2, **not renamed** |
| `frappe-ui` (gitlink `a3d141c`, URL `https://github.com/frappe/frappe-ui.git`) | `apps/helpdesk/frappe-ui` (same URL, same commit); the entry moves into the **root** `.gitmodules` because Git only reads that file at the superproject root | 3 |
| `.github/ .eslintrc.js .flake8 .gitattributes .gitignore .gitmodules .lintstagedrc .mergify.yml .pre-commit-config.yaml .prettierignore .prettierrc.json .releaserc commitlint.config.mjs crowdin.yml MANIFEST.in package.json playwright.config.ts pyproject.toml yarn.lock AGENTS.md LICENSE README.md screenshot.webp` | `apps/helpdesk/` same names | 3 |

New `docs/` files (written in Part B): `architecture/{rules,code-map}.md`, `upstream.md`, `handoff/README.md`, `reference/*`, READMEs in `apps/helpdesk` and `apps/nxerp_platform`, a README for each README-labelled folder, ADR-007 (monorepo supersedes ADR-001). `architecture/adding-an-app.md` already exists; I will extend it with the two documented placeholders (`apps/hrms/` or an `apps.json` pin of official HRMS, which requires ERPNext; `services/<name>/`). Nothing is created for them.

---

## 5. Who references each Tier 2 folder (FACT, from `git grep` on `8f77254` and on the platform branch)

### `desk/` to `hd-frontend/` (Helpdesk repo)

- `package.json`: scripts `postinstall`, `dev`, `build` run `cd desk && ...`
- `pyproject.toml`: `[tool.bench.assets] build_dir = "./desk"`. **`bench build` reads this**; the baseline build (B3) is the proof test
- `.github/workflows/lint.yml`: 2 steps `cd desk`; `.github/workflows/ui-tests.yml`: path filter `desk/**`
- `.gitignore` (6 lines: `desk/components.d.ts`, `desk/stats.html`, theme `build/` exceptions), `.gitattributes:2`, `.prettierignore:1`, `.pre-commit-config.yaml` (hook entries and `files:` regex)
- `e2e/tests/theme.spec.ts:1`: `import ... "../../desk/src/theme/generated/tokens"`
- `helpdesk/test_utils.py:768`: Python test helper builds `"helpdesk", "..", "desk", "src", "assets", "images"` (a **code** path string; runs in B2)
- `AGENTS.md` (about 25 mentions), comments in `helpdesk/api/onboarding.py`, `test_hd_agent.py`, `test_manager_mentions.py`
- `desk/src/theme/build/sync.mjs` and `desk/src/theme/README.md`: default target is the sibling `../nxerp-platform/nxerp/public/css`. **If this path is not updated, `theme:check` prints "not found, skipped" and silently stops checking** the platform copies
- Platform repo: `.github/workflows/ci.yml` (`helpdesk-src/desk` at lines 132, 134, 137, 142, 501, 578, 592), `tools/theme_build.sh` (lines 7 to 9, 23, 24, 28), comment in `nxerp/hooks.py:34`, docs
- **Not affected** (same depth, so still correct): `@framework/ui link:../../frappe/ui`, `tailwind.config.js` and `tsconfig.json` `../../frappe/ui`, `vite.config.js` `outDir ../helpdesk/public/desk`, `vite-helpers.ts ../frappe-ui`, `src/socket.ts ../../../../sites/common_site_config.json`. The output folder `public/desk` and URLs `/assets/helpdesk/desk/...` are Tier 3 and stay
- Proof test: B3 (frontend build), B4 (theme check and audit), B10 (Playwright discovery), B11 (typecheck), B2 (Helpdesk backend tests, because of `test_utils.py`)

### `e2e/` to `hd-e2e-tests/` (Helpdesk repo)

- `playwright.config.ts`: `import "./e2e/helpers/site"` and `testDir: "./e2e"`
- `e2e/helpers/personas.ts:37`: `e2e/.auth/${key}.json`; `e2e/tests/settings/account.spec.ts:7` and `e2e/tests/tickets/new/portal-new.spec.ts:6`: `e2e/fixtures/pixel.png` (paths relative to the repo root)
- `.gitignore:50` (`e2e/.auth`), `.github/workflows/ui-tests.yml:9` (`e2e/**`)
- Do **not** touch the many `e2e-...@example.com` strings or the `e2e.localhost` site name: they are data, not paths
- Proof test: B10 must print the same 174 tests in 30 files with the same output after normalising the folder name; B11 same 2 errors. **The suite itself cannot run here, so this proof is weaker; I will say so in the report**

### `docker/` to `hd-docker/` (Helpdesk repo)

- Only `AGENTS.md:371` mentions the folder. `README.md:147,150` use raw URLs of the **upstream** repository (`frappe/helpdesk/develop/docker/...`); they point at someone else's repo, so they stay as they are
- No Dockerfile, compose file, workflow or script references it (`build.yml` uses `frappe/frappe_docker`)
- Proof: nothing builds from it. Lowest risk

### `realtime/`: **do not rename**

- Frappe core loads it by convention (finding 2). The two other hits for "realtime" are Python imports of `frappe.realtime` and `helpdesk.overrides.realtime`, not this folder
- Action: keep, add a README explaining why the name is fixed

### Platform folders (my own Tier 2 list; same procedure)

| Folder | Referenced by (file count) |
|---|---|
| `tools/` to `scripts/` | `.github/actions/stack-up`, `license-policy/*`, `workflows/{ci,release,upstream-watch}.yml` (ci.yml alone has 38), `.pre-commit-config.yaml`, `CODEOWNERS`, `nxerp/tests/test_architecture.py`, the tools themselves (about 20), about 25 docs |
| `e2e/` to `browser-tests/` | `.github/actions/stack-up`, `workflows/{ci,deploy-staging}.yml`, `deploy/scripts/smoke.sh`, `CODEOWNERS`, `nxerp/tests/e2e_fixtures.py`, `e2e/run.sh`, `e2e/site.sh`, `e2e/package.json`, about 12 docs |
| `deploy/dev/` | `.github/actions/*`, `ci.yml` (15 hits for `deploy/...`), `.gitignore`, `.dockerignore`, `deploy/README.md`, `compose.yaml` mounts (`../..:/workspace`), `up.sh` (finds `../../../helpdesk`), `e2e/*.sh`, `tools/ci_stack.sh` (10), about 20 docs |
| `deploy/staging-like/`, `deploy/environments/` | `deploy/scripts/*`, `workflows/deploy-*.yml`, `ssh-deploy` action, docs |
| `nxerp/` to `apps/nxerp_platform/nxerp/` | `ci.yml` (3), `.gitignore`, `.dockerignore`, `tools/check_architecture.py` (hard-codes `root/"nxerp"` and `root/"pyproject.toml"`), `nxerp/tests/test_architecture.py`, `CODEOWNERS` (11 lines start with `/nxerp/`: **ownership silently disappears if not updated**), `deploy/docker/Dockerfile` (line 33 copies the **whole repository root** into the image as the `nxerp` app, which is wrong once the root holds two apps; see E3), `install_apps.sh` (lines 58 to 61 treat the build context as the app), about 20 docs |

---

## 6. Part B procedure and the non-rename edits I need approved

Order (each Tier 2 step is its own commit, then the proof set, and any difference means `git revert` of that commit):

1. Clone `NxERP/`, create `develop` from `origin/phase-4/release-readiness`.
2. `git mv` platform files into `apps/nxerp_platform/`, `scripts/`, `deploy/...` (one commit per Tier 2 move).
3. Import the Helpdesk tree of `8f77254` (via `git archive`, so no `node_modules`, `.env`, caches or build output) into `apps/helpdesk/`, then `docker/`, `e2e/`, `desk/` renames, one commit each.
4. Docs, READMEs, `code-map.md`, `rules.md`, `upstream.md`, ADR-007.
5. Verify: rerun B1 to B12, `git diff -M --stat`, import-boundary check, fresh clone into an empty temp folder and run the bootstrap.
6. Secret scan (`gitleaks`, image already local) and a size scan (no file over 50 MB) before every commit; stop and tell you if anything looks like a secret.

### Non-rename edits that the layout requires (NOT path-string only: your decision)

| # | Edit | Why it cannot be a pure rename |
|---|---|---|
| E1 | `deploy/bootstrap/bootstrap.sh`, `up.sh`, `compose` mounts: install `nxerp` from `apps/nxerp_platform` and install Helpdesk as a **real copy** of `apps/helpdesk` into the bench | Today they clone the NxERP repo root and fetch Helpdesk from another repo at a pinned commit |
| E2 | `deploy/apps.json`: the `helpdesk` and `nxerp` entries stop being `url@commit` of other repos (an in-repo commit cannot pin itself). Proposal: `"path": "apps/helpdesk"` / `"apps/nxerp_platform"`; `erpnext`, `payments`, `telephony` unchanged | Your tree says `apps.json` pins "helpdesk, nxerp_platform" |
| E3 | `deploy/docker/install_apps.sh` + `Dockerfile` and `.github/actions/helpdesk-fetch`: same idea for the production image and CI | `bench get-app <repo-url>` cannot install a subfolder |
| E4 | `scripts/check_architecture.py`: rule R4a ("the repo holds no second Frappe app") would fail by design in a monorepo; scope it to `apps/<app>/` and make R3 run over `apps/helpdesk` automatically (today CI runs it **without** `--app-path`, so "no app imports nxerp" is **skipped** in CI) | Required for rule 5 (boundary test in CI that fails on any violation) |
| E5 | Root `.gitmodules` entry for `apps/helpdesk/frappe-ui` | Git reads it only at the root |
| E6 | CI workflows trigger on pull requests to `main` only; PRs into `develop` would run **no CI**. Proposal: add `develop` to the triggers (one line per workflow) | Not a rename. Without it the boundary test never runs on teammates' PRs |
| E7 | Helpdesk's own `.github/workflows/*` stay under `apps/helpdesk/.github/` but **GitHub only runs workflows at the repo root**, so they become inert. I keep them (Tier 3) and document it; porting them is a follow-up | |

If you reply plain `APPROVED`, I apply E1 to E7 in the **minimal** form above, each in its own commit, each proven by the bootstrap run, and I report any I had to leave out. If you would rather keep the old install mechanics and reject the monorepo, say `APPROVED-WITHOUT-E` and I stop before step 2 and report instead.

### Architecture rules and the import-boundary test

- `docs/architecture/rules.md` will carry your five rules.
- Rule 5 **already half-exists**: `tools/check_architecture.py` (rules R1 to R4, run in CI, plus 17 unit tests in `nxerp/tests/test_architecture.py`). Part B extends it (E4) rather than adding a second checker, and wires `--app-path` so it checks Helpdesk in CI.
- Rule 4 (sub-packages): not applied (section 3, point 2).

---

## 7. Decisions for you

Reply `APPROVED` to accept every **recommended** answer, or override any:

| # | Question | Recommended |
|---|---|---|
| D1 | Monorepo and edits E1 to E7 | **Yes**, minimal form |
| D2 | Keep the package name `nxerp` (folder `apps/nxerp_platform/`) | **Yes** |
| D3 | The 14 uncommitted files in `helpdesk/` | **Keep out of `develop`**; preserve as a patch in `_archive/` and, if you want, as a local branch `wip/assignee-follows-team` in `helpdesk/` |
| D4 | `develop` base | `origin/phase-4/release-readiness` (not the empty `main`) |
| D5 | Where to create `NxERP/` | In the workspace as instructed. **Caution:** the workspace is inside OneDrive, which can lock or corrupt `.git` and `node_modules`; a folder outside OneDrive is safer |
| D6 | Docker stacks (`nxerp-dev-*`, `frappe-helpdesk-docker-*`) | I will not move `helpdesk/`, `nxerp-platform/` or `frappe-helpdesk-docker/` while they run; tell me when they are stopped |
| D7 | Rewrite the 16 local-path links in the knowledge map to repo-relative links (path strings only, separate commit) | **Yes** (the repo is public) |
| D8 | Re-create tag `v0.1.0-pre.1` in the new repo | Your call |

---

## 8. Risks

1. **License mix (needs professional review, not a legal conclusion).** `apps/helpdesk/` carries the GNU Affero GPL v3 (`LICENSE`); `nxerp/hooks.py` says `Proprietary` as a placeholder; the repo is public. Putting both in one public repository should be reviewed before the first push.
2. **Install path change (E1 to E3)** is the largest risk; it is why the bootstrap is the final gate. I cannot prove the production Docker image and GitHub Actions pipeline here: CI has never run on GitHub.
3. **Disk.** The C: drive has **7.6 GB free**. A fresh bootstrap pulls and builds several GB of Docker data. It may fail for space; if so I will report that rather than claim the bootstrap passed.
4. **Helpdesk history is not imported** (snapshot only). `docs/upstream.md` records the base commit `58b82a6e2` (upstream `develop`, 2026-10-11), 23 commits and 136 files (+5,375 / -278) on top. The original fork history stays in `helpdesk/` and on the company fork remote.
5. **Weak proof for `e2e/`** (discovery and typecheck only). Stated again in the report.
6. **Silent-skip hazards** found: theme `sync.mjs` path, `CODEOWNERS` paths, CI path filters, `.gitmodules`. Each is on the update list.
7. **Windows quirks.** `core.autocrlf=true` here; shell scripts need LF and the executable bit (an earlier CI failure came from that: commit `63e61fb`). I will set the bit explicitly (`git update-index --chmod=+x`) and check `.gitattributes`.
8. **Live containers** mount the old folders by path; the workspace rename already broke one. Moves wait for D6.
9. **`apps/nxerp_platform/nxerp/nxerp_platform/`** (Frappe module folder) will sit under `apps/nxerp_platform/`: a near-identical name, but Tier 3 (`modules.txt`), so it stays; the README explains it.
10. **Weak demo credentials** exist in `frappe-helpdesk-docker/` (upstream's public defaults). They are not company secrets, but a secret scanner may flag them; I will allow-list them in `.gitleaks.toml` only if you agree.
11. **PR #1** (`codex/nxerp-integration`) on the company repo is untouched, as ADR-001 decided.

### Restoring the dev environment after the baseline

The dev container's Helpdesk checkout is now clean `8f77254`. To get back to what it was (parity + the 14 files), run in the container: `git -C ~/frappe-bench/apps/helpdesk stash pop`, move `/home/frappe/stray-artifacts/desk-src-theme-theme` back if wanted, then `bench build --app helpdesk`. I will do this at the end of Part B unless you tell me not to.

---

## 9. What I will never do

Touch `main`; force-push; delete anything (originals stay; the archive is a move or copy); commit `node_modules`, virtualenvs, bench `sites/`, built assets, logs, `.env`, secrets or files over 50 MB; change logic, dependencies or tool config contents beyond path strings and the listed E-edits.

**Waiting for your reply: `APPROVED` (recommended answers) or your overrides.**
