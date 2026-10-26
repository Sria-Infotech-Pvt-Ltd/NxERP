# Helpdesk fork audit (customised Frappe Helpdesk for Sria Infotech / NXERP)

Facts-only audit. Nothing in any repository was modified, committed or fetched by this audit.

## 0. Conventions and scope

- Labels: **FACT** (evidence: `path:line` read, or a command actually run), **ASSUMPTION**, **DECISION** (a choice someone must make; none are made here), **NOT VERIFIED** (could not be checked).
- Naming: NXERP = umbrella platform/brand. ERPNext = ERP app inside it. Helpdesk = separate support app (this repo). Frappe = framework.
- Source A, "WIP" = working tree at `<workspace>/helpdesk` (includes uncommitted work).
- Source B, "HEAD" = clean read-only checkout of commit 1c6981cc5 at `<scratchpad>/src/helpdesk-fork` (`<scratchpad>` = the session scratch directory). Unless marked WIP, `path:line` refers to HEAD.
- Frappe routing/login evidence is from the pinned sibling `<scratchpad>/src/frappe` (v16.53.0, `frappe/__init__.py:58`). Frappe v15 sources are not available locally, so v15 behaviour is NOT VERIFIED throughout.
- The folder named `NXERP CORE` was not read. A sibling `NXERP` path appears only as a string inside a build script (see 3.4); it was not opened.
- No credentials were found in the files read. One hard-coded support mailbox address exists in `helpdesk/www/login.py:17`; it is not reproduced here (shown as `[support email]`).
- Tests: the static audit ran nothing. **Update (runtime, later the same day):** the Helpdesk backend suite was executed on the bootstrapped site: 552 of 559 pass, 7 error with `Throttled`; Playwright e2e not run. See `bootstrap-evidence.md` section 4. The per-suite text below still says NOT YET RUN because it was written before that run.

---

## 1. Version matrix

### 1.1 Fork (HEAD 1c6981cc5) vs upstream

| Item | Fork (branch `feature/nxerp-login-page`) | Upstream `origin/main` (v1.31.0) | Evidence |
|---|---|---|---|
| Helpdesk `__version__` | `"1.22.2"` (develop snapshot string, not a release) | `"1.31.0"` | FACT `helpdesk/__init__.py:1`; `git show origin/main:helpdesk/__init__.py` |
| requires-python | `>=3.14` | `>=3.10` | FACT `pyproject.toml:7`; `git show origin/main:pyproject.toml` |
| Frappe | `>=16.0.0-dev,<18.0.0` | `>=15.123.1,<17.0.0` | FACT `pyproject.toml:19` |
| Telephony app | `>=0.0.1,<1.0.0`; also `required_apps = ["telephony"]` | same range | FACT `pyproject.toml:20`, `helpdesk/hooks.py:9` |
| Build backend | flit_core `>=3.4,<4` | same | FACT `pyproject.toml` `[build-system]` |
| Python dependency | `textblob==0.18.0.post0` | same | FACT `pyproject.toml` |
| Node (CI) | 24 | 24 | FACT `.github/workflows/lint.yml:20`, `server-tests.yml:57`, `ui-tests.yml:63,167`; main workflows grep (`MSYS_NO_PATHCONV=1 git show origin/main:.github/workflows/...`) |
| Python (CI) | 3.14 | server tests 3.12, ui tests 3.12, lint 3.10 | FACT `.github/workflows/server-tests.yml:43`, `ui-tests.yml:58`, `lint.yml:38`; main per git show |
| Frappe branch used by CI | `develop` | `version-15` (ui-tests, build, install.sh) | FACT `ui-tests.yml:21`; main `ui-tests.yml:22`, `build.yml:36` |
| `engines` field | none in `package.json` or `desk/package.json` | not checked in detail | FACT grep for `engines` in both returned nothing |
| frappe-ui | `1.0.0-rc.1` | `1.0.0-rc.1` (same) | FACT `desk/package.json:30`; `git show origin/main:desk/package.json` line 30 |
| `@framework/ui` | `link:../../frappe/ui` (needs Frappe checkout at `apps/frappe/ui`) | same | FACT `desk/package.json:13` |
| Vue | `^3.5.14` | `^3.5.14` | FACT `desk/package.json:36` |
| Vite | `^5.4.21` | `^5.4.21` | FACT `desk/package.json:51` |
| Tailwind | `^3.4.15` | `^3.4.15` | FACT `desk/package.json:48` |
| TypeScript | `^5.0.2` | n/c | FACT `desk/package.json:49` |
| vite-plugin-pwa | `0.17.5` | n/c | FACT `desk/package.json:52` |
| Playwright | `@playwright/test ^1.63.0`, `@types/node ^26.6.3` | same | FACT `package.json:18-19` |
| frappe-ui submodule | gitlink `a3d141c63b09...` (path `frappe-ui`, directory empty in the clean checkout) | n/c | FACT `git ls-tree HEAD frappe-ui`; `.gitmodules:1-3` |
| docker helper | `docker/init.sh` initialises bench with `--version version-15` | n/c | FACT `docker/init.sh:11` |

### 1.2 Pinned sibling sources (for runtime reasoning)

| Component | Version | Requirement | Evidence |
|---|---|---|---|
| Frappe | 16.53.0 | python `>=3.14,<3.15`; node `>=24` | FACT `frappe/pyproject.toml:7`, `frappe/package.json:18-19` |
| ERPNext | 16.52.1 | python `>=3.14`; frappe `>=16.50.0,<17.0.0` | FACT `erpnext/pyproject.toml:7,45`, `erpnext/__init__.py:10` |
| Telephony | 0.0.1 | python `>=3.10`; frappe `>=14.101.0,<=17.0.0-dev` | FACT `telephony/pyproject.toml:7,25`, `telephony/__init__.py:1` |

### 1.3 Consequence

- FACT: the fork is a develop snapshot (merge-base 58b82a6e2, 2026-10-11) that needs Python 3.14 and Frappe 16. It is not compatible with Frappe 15 by declaration (`pyproject.toml:19`).
- FACT: a second company branch, `company/nxerp-stable` (commit 07f84a2c8), is built on upstream v1.30.2 (`git merge-base company/nxerp-stable origin/main` = 78722c2b3; 12 commits ahead of `origin/main`), declares `requires-python >=3.10`, `frappe >=15.116.1,<17.0.0`, `__version__ = "1.30.2"`, and its CI image pins `FRAPPE_BRANCH=v15.122.0` (`git show company/nxerp-stable:.github/workflows/build.yml` line 37).
- FACT: `helpdesk/www/login.py` is byte-identical between `company/nxerp-stable` and HEAD (`diff` reported identical). `www/`, `public/` and `nxerp_branding.py` show no diff either (`git diff --stat company/nxerp-stable HEAD -- helpdesk/www helpdesk/public helpdesk/nxerp_branding.py ...` listed only `hooks.py`, `desk/vite.config.js` and `helpdesk/public/erpnext/customer_list.js`).
- ASSUMPTION (from user project memory, not verified here): the running Docker site is Frappe 15 with an older Helpdesk and does not contain this repo. If true, `nxerp-stable`, not `feature/nxerp-login-page`, is the line that matches that runtime.

---

## 2. Remotes, branches, HEAD, recent commits

| Item | Value | Evidence |
|---|---|---|
| `origin` | `https://github.com/frappe/helpdesk.git` (this IS upstream) | FACT `git remote -v` |
| `company` | `https://github.com/Sriainfotech/Frappe-Help-Desk.git` | FACT `git remote -v` |
| `upstream` remote | does not exist; not added (the request to add it is moot because `origin` already is upstream) | FACT `git remote -v` shows only `company`, `origin` |
| Current branch | `feature/nxerp-login-page`; HEAD `1c6981cc515af58b8cdfbad7a7525b33236e399b` | FACT `git rev-parse HEAD` |
| Merge-base with `origin/develop` | `58b82a6e20f11f2527540f3e41d9f5e4e15669fb` (2026-10-11) | FACT `git merge-base` |
| Ahead / behind `origin/develop` | 10 ahead, 12 behind | FACT `git rev-list --left-right --count origin/develop...HEAD` printed `12 10` |
| `origin/develop` tip | `12d2dad2b` (2026-10-16) | FACT `git log -1 origin/develop` |
| Local `develop` | `58b82a6e2`, identical to `company/develop` | FACT `git rev-parse` per branch |
| `company/feature/nxerp-login-page` | `1c6981cc5`, equals local HEAD | FACT `git rev-parse` |
| `company/nxerp-stable` | `07f84a2c8`; v1.30.2 + 12 commits (login, branding, CI image) | FACT see 1.3 |
| Working tree | 43 modified tracked files, 8 untracked entries (20 files with `--untracked-files=all`) | FACT `git status --short` |
| Local tags | v1.31.0 etc. exist locally | FACT `git tag -l 'v1.3*'` |

### 2.1 The 10 committed NXERP commits (all dated 2026-10-16, authors omitted)

| Commit | Subject |
|---|---|
| ff9b8745a | feat: NXERP-branded login page |
| 582baf437 | style: minimal, high-end redesign of the NXERP login screens |
| bcfef9251 | feat: match the approved NXERP login design exactly |
| 2cc02f565 | feat: fluid, polished login layout; NXERP logo across the site |
| 428621d58 | fix: rename logo files so browsers fetch the new logo instead of a cached copy |
| cabffa926 | style: match the target hero edge/art exactly; highlight the card; crisper controls |
| c9b3d9b54 | feat: hide the Microsoft sign-in button; refit the login card; set support address |
| 0df99bd19 | feat: remove email-link sign-in; support link opens Gmail compose; hover/interaction polish |
| f7554abfe | feat: replace Frappe branding with NXERP across the app |
| 1c6981cc5 | fix: load the default logo as a runtime URL so the frontend build does not try to bundle it |

### 2.2 The 12 upstream commits the branch is behind

FACT: `git rev-list --count HEAD..origin/develop` = 12 (listing not expanded). They are not merged; any rebase may touch `desk/src/components/layouts/Sidebar.vue`, `hooks.py` or `vite.config.js` (files also changed by the fork). NOT VERIFIED that conflicts occur.

---

## 3. Custom changes vs upstream

### 3.1 Committed diff (`58b82a6e2..HEAD`): 64 files, +831 / -64

FACT: `git diff --stat 58b82a6e2..HEAD` last line: `64 files changed, 831 insertions(+), 64 deletions(-)`. 44 of the 64 files are binaries (`git diff --stat` rows marked `Bin`: images, icons, splash screens, a font); the other 20 are text (`favicon.svg` is text but wraps an embedded PNG).

#### Non-binary changed files (every one)

| File | Category | Purpose |
|---|---|---|
| `helpdesk/hooks.py` (+10/-3) | hooks | `app_title` "Helpdesk" -> "NXERP" (line 2); apps-screen entry title/logo -> NXERP mark (lines 12-20); adds `app_logo_url` (23) and `website_context` favicon/splash (24-27) |
| `helpdesk/nxerp_branding.py` (new, 51 lines) | branding | Manual helper `apply_branding()` writing brand name/logo/favicon into HD Settings, Website Settings, Navbar Settings, System Settings; `brand_help_menu()` hides "About"/"Frappe Support" Help items and adds "IT Support" |
| `helpdesk/www/login.py` (new, 81 lines) | login | Wraps Frappe's login context, layers NXERP branding, turns off social-login UI and email-link login |
| `helpdesk/www/login.html` (new, 267 lines) | login | Jinja template extending `frappe/www/login.html` with NXERP layout and cosmetic JS |
| `helpdesk/public/nxerp_login/css/nxerp-login.css` (new, 377 lines) | login | Styles for the NXERP login layout |
| `helpdesk/setup/welcome_ticket.py` | branding | Sample-ticket text: "Frappe Helpdesk" -> "NXERP"; removes support.frappe.io link; "Team Frappe" -> "Team NXERP" |
| `helpdesk/templates/emails/macros.html` | branding | Email signature "Team Frappe" -> "Team NXERP" (line 26) |
| `desk/index.html` | branding | `<title>` and apple-mobile-web-app-title -> NXERP |
| `desk/vite.config.js` | branding | PWA manifest name/short_name -> NXERP, new description (lines ~58-64) |
| `desk/src/assets/logos/HDLogo.vue` | branding | Inline Frappe SVG replaced by `<img>` of `/assets/helpdesk/nxerp_login/images/nxerp-mark.png` (runtime URL, so Vite does not bundle it) |
| `desk/src/assets/images/frappe-mail.svg` | branding | Frappe Mail icon redrawn as a generic mail glyph |
| `desk/src/components/icons/FrappeCloudIcon.vue` | branding | Cloud icon redrawn; formatting also changed |
| `desk/src/components/layouts/Sidebar.vue` | branding | HelpModal title -> "NXERP" (line 51); "Login to Frappe Cloud" -> "Open hosting dashboard"; mobile title -> "NXERP Mobile" (line 426) |
| `desk/src/components/Settings/EmailProviderIcon.vue` | branding | Display label "Frappe Mail" -> "NXERP Mail" (line 32); stored service id unchanged |
| `desk/src/components/Settings/emailConfig.ts` | branding | Label "Frappe Mail site" -> "Mail server URL"; placeholder `frappemail.com` -> `mail.example.com`; help text -> "NXERP Mail" (line 244) |
| `desk/src/components/customer/NewCustomerDialog.vue` | branding | Placeholder `frappe.io` -> `example.com` |
| `desk/src/composables/customer.ts` | branding | Placeholder `frappe.io` -> `example.com` |
| `desk/src/composables/fc.ts` | branding | Dialog wording "Login to Frappe Cloud" -> "Open the hosting dashboard" (endpoint `frappecloud.com` unchanged, line 5) |
| `desk/src/pages/PersonaForm.vue` | branding | Onboarding questions: "Frappe Helpdesk" -> "NXERP"; "Frappe Discuss" -> "Community forum"; partner wording (lines 164-245) |

Binary/asset changes (FACT, `git diff --stat`): `desk/public/desk.png`, `desk/public/favicon.svg` (now an SVG wrapping an embedded base64 PNG; non-text but listed because it is text-encoded), `desk/public/manifest/*` (apple-icon, 34 apple-splash JPGs, 2 maskable icons), and new `helpdesk/public/nxerp_login/{fonts/yellowtail.woff2, images/hero-art.webp, nxerp-favicon.png, nxerp-mark.png, nxerp-wordmark.png, nxerp-wordmark-light.png}`.

#### Category summary

| Category | Files | Notes |
|---|---|---|
| Login | `www/login.py`, `www/login.html`, `public/nxerp_login/css/nxerp-login.css` | Section 4 |
| Branding (python/hooks) | `hooks.py`, `nxerp_branding.py`, `setup/welcome_ticket.py`, `templates/emails/macros.html` | Section 5 |
| Branding (frontend) | `desk/index.html`, `vite.config.js`, `HDLogo.vue`, `Sidebar.vue`, `PersonaForm.vue`, email-provider files, icons, 2 placeholders | Section 5 |
| Assets | favicon, manifest icons/splashes, hero art, logos, font | 44 binaries |
| Other | none | FACT: no ticket, assignee, team, comment, notification or permission code changed in the committed diff |

FACT: the committed diff touches no `.github/` workflow, no doctype, no patch, no API module and no test.

### 3.2 Uncommitted work (WIP) is a separate theme/palette system

FACT: `git diff --stat` = 43 files, +467 / -265. Untracked: see list. Nothing here is committed.

| Group | Files (WIP) | What it is |
|---|---|---|
| Theme source of truth | untracked `desk/src/theme/` (README.md, `tokens/{palette,semantic,contrast,frappe-ui.lock,audit-allow}.json`, `build/*.mjs`, `generated/*`, `runtime/{useAppTheme,useChartTheme}.ts`, empty `overrides/`) | Palette-as-data (paper/sand/taupe/amber/umber/charcoal per README) generated into Tailwind theme, CSS, email tokens (`desk/src/theme/README.md:1-5`) |
| Build/CI wiring | modified `desk/package.json` (scripts `theme:build`, `theme:check`, `theme:audit`), `.github/workflows/lint.yml` (new job `theme-tokens`), `.pre-commit-config.yaml` (local hook `theme-audit`), untracked `.prettierignore` | Gate that generated files are fresh, contrast passes, no hard-coded colours |
| Tailwind/CSS | modified `desk/tailwind.config.js`, `desk/src/index.css`, `desk/src/App.vue`, `desk/src/main.js` (icon class `text-ink-blue-5` -> `text-ink-accent-5`) | Applies generated theme as `theme.extend` plus a first-listed plugin |
| Component recolouring | 25+ modified Vue/TS files (BarChartCard, LineChartCard, ThemeSwitcher, TicketStats, ChartItem, RecentFeedback, ticketStatus store, tiptap-extensions, call-logs utils, etc.) | Replace hex/blue classes with theme tokens; e.g. `AgentTicketsCard.vue` swaps hard-coded chart colours for `useChartTheme()` (diff verified) |
| Boot/theme persistence | modified `helpdesk/www/helpdesk/index.py` (adds `desk_theme` to boot, +3 lines), modified `desk/index.html` (pre-paint theme script reading `boot.desk_theme`), untracked `helpdesk/api/theme.py` (`set_desk_theme`, POST, writes `User.desk_theme`), untracked `helpdesk/tests/api/test_theme.py` (3 tests), untracked `e2e/tests/theme.spec.ts` (3 tests) | Server-side persisted Light/Dark/Automatic choice shared with Frappe Desk |
| Login theming | modified `helpdesk/www/login.html` (theme toggle, pre-paint script, links `nxerp-theme.css`), `helpdesk/www/login.py` (adds `context.nx_theme_version`; remaining diff is black-style re-wrapping), `helpdesk/public/nxerp_login/css/nxerp-login.css` (+300/-~100 lines); untracked `nxerp-theme.css`, `fonts/manrope-latin.woff2`, `fonts/space-grotesk-latin.woff2` | Light/dark login with `meta theme-color` changed `#081830` -> `#fcfcfb` |
| Docs | modified `AGENTS.md` | NOT VERIFIED what changed (diff 4 lines, not read) |

FACT `desk/src/theme/build/sync.mjs:13`: the sync step writes generated CSS to `path.resolve(REPO, "../NXERP/nxerp/nxerp/public/css")`, i.e. a directory outside this repo. That directory was not opened.

FACT: `desk/src/theme/runtime/useAppTheme.ts:21` calls `helpdesk.api.theme.set_desk_theme`.

### 3.3 Risk: committed branch and WIP are inconsistent

- FACT: committed `helpdesk/www/login.html` (HEAD) links only `nxerp-login.css`. The WIP `login.html` also links `nxerp-theme.css`, which is untracked. Committing `login.html` without `nxerp-theme.css` and the two untracked fonts would yield a 404 stylesheet.
- FACT: WIP `desk/tailwind.config.js` imports `./src/theme/generated/tailwind-theme.mjs`, which is untracked. A checkout of HEAD plus only the tracked modifications would fail to build.
- FACT: WIP `lint.yml` and `.pre-commit-config.yaml` run `node desk/src/theme/build/audit-hardcoded.mjs`; the script exists only in the untracked `desk/src/theme/`.
- FACT: WIP `desk/package.json` script `theme:check` needs generated files that are untracked.
- FACT: the HEAD tree contains no theme code, so any code reading HEAD (e.g. the clean checkout) sees the old hex-colour UI. Any evidence in this audit labelled HEAD does not reflect the theme work.
- ASSUMPTION: the WIP will be committed as one change later; if only a subset is committed the build or login page breaks.
- FACT: WIP line-ending warnings (LF -> CRLF) appear for 8 files (`git diff --stat` output), so a Windows commit may produce whole-file diffs. NOT VERIFIED whether `.gitattributes` exists.

### 3.4 Risk: the branch targets Frappe 16; the NXERP login code was written against a different login template

- FACT: Frappe 16.53.0 `frappe/www/login.html` contains no `.btn-login` main submit class (submit button is `<button class="es-button w-full" data-variant="solid" type="submit">`, lines ~43-46), no `forgot-password-message` and no `login-divider` (grep counts 0; `grep -n "btn-login\b"` returned no match). `login_with_frappe_cloud_url` is referenced nowhere in Frappe 16.53.0 (grep returned nothing).
- FACT: committed `www/login.html` JS and `nxerp-login.css` select `section.for-login .btn-login` (login.html:128,179), `.forgot-password-message` (login.html:131,136; css:200-208), `.login-divider` (login.html:159; css:256-260). On Frappe 16.53.0 these selectors do not match, so steps 2, 3 (keep me signed in), 5b and part of the CSS silently no-op (every JS step is wrapped in `try/catch`, login.html:106-263).
- FACT: `login.py:42` sets `context.login_with_frappe_cloud_url = None`, which has no effect on Frappe 16.53.0.
- FACT: the e2e login test expects a button named "Continue" (`e2e/tests/auth.spec.ts:13`), matching Frappe 16's stock button text.
- NOT VERIFIED: the Frappe 15.122 template (what `nxerp-stable` runs) structure. The selectors above are consistent with a v15-era template but this was not checked because no v15 source is available.

---

## 4. Login implementation

### 4.1 Where it lives

| Piece | Path | Role |
|---|---|---|
| Page controller | `helpdesk/www/login.py` | `get_context(context)` at line 22 |
| Template | `helpdesk/www/login.html` | `{% extends "frappe/www/login.html" %}` (line 9); overrides blocks `navbar`, `footer` (empty), `head_include`, `page_content`, `script` |
| Styles | `helpdesk/public/nxerp_login/css/nxerp-login.css` | served as `/assets/helpdesk/nxerp_login/css/nxerp-login.css?v=<mtime>` (login.html:18, login.py:45,58-63) |
| Images/fonts | `helpdesk/public/nxerp_login/{images,fonts}/` | wordmark, light wordmark, mark, favicon, hero art, Yellowtail font |
| Hooks | `helpdesk/hooks.py:2,12-27` | `app_title`, apps screen entry, `app_logo_url`, `website_context` favicon/splash |
| Branding helper | `helpdesk/nxerp_branding.py` | manual site-settings writer (4.5) |

FACT: no `website_route_rules`, `website_redirects`, `page_renderer` or `website_path_resolver` hook refers to login. The only route rule is `/helpdesk/<path:app_path>` -> `helpdesk` (`hooks.py:57-62`).

### 4.2 How it is served and how Frappe's own `/login` is overridden

FACT, evidence from the Frappe 16.53.0 sibling:

1. Request path `login` goes through `PathResolver.resolve()` (`frappe/website/path_resolver.py:37-85`). Only `desk` is hard-coded (line 44). Redirect hooks and website route rules are applied first (lines 51-64), then renderers are tried in order: custom (`page_renderer` hook), `StaticPage`, `WebFormPage`, `DocumentPage`, `TemplatePage`, `PrintPage`, `ListPage` (lines 69-78).
2. `TemplatePage.set_template_path()` searches `www` and `templates/pages` in every installed app, iterating `reversed(frappe.get_installed_apps())` and stopping at the first match (`frappe/website/page_renderers/template_page.py:50-66`). Probe order per app is `login`, `login.html`, `login.md`, `login/index.html`, `login/index.md` (`template_page.py:70-74`).
3. Therefore, the app installed LAST wins for the same www route. Helpdesk (installed after Frappe) shadows `frappe/www/login.html` and `frappe/www/login.py` with `helpdesk/www/login.*`. The page module is resolved as `<app>.www.login` (`template_page.py:129-145`), so `helpdesk.www.login.get_context` runs instead of `frappe.www.login.get_context`.
4. Consequence: any app installed after Helpdesk that ships `www/login.html` would shadow Helpdesk's page. FACT that ERPNext 16.52.1 and Telephony ship no `www/login*` file (`find` returned nothing). Whether a future NXERP-level app ships one is NOT VERIFIED.
5. The Jinja `extends "frappe/www/login.html"` resolves through the prefix loader keyed by app name (`frappe/utils/jinja.py:186-203`), so it reaches Frappe's own template even though a same-named route exists in Helpdesk.
6. `/api/method/login`, `login_via_token`, `send_login_link`, OAuth callbacks etc. are untouched; they remain Frappe's. Helpdesk's `auth_hooks` (`hooks.py:169`, `helpdesk/auth.py:72-105`) only act when site config `block_endpoints` is set and lists many login endpoints in `ALLOWED_PATHS` (`auth.py:5-65`).

### 4.3 What `login.py` does (read line by line)

| Lines | Behaviour |
|---|---|
| 7, 26 | Calls Frappe's `get_context` (`frappe.www.login`) first and keeps its result (`frappe_login_context(context) or context`). All authentication, `redirect-to` handling, 2FA flags, signup flags and social-login discovery stay Frappe's code. |
| 28-30 | If `app_name` is empty or equals `frappe`/`helpdesk`/`erpnext` (case-insensitive), sets `app_name = "NXERP"` |
| 32-35 | Replaces logo with `nxerp-wordmark.png` when logo empty, from `/assets/frappe/`, or already contains "nxerp"; always sets `favicon` |
| 37-39 | Fills the login-name placeholder `Enter your <label>` |
| 42 | `login_with_frappe_cloud_url = None` (no effect on Frappe 16.53.0, see 3.4) |
| 44-49 | Adds `nx_year`, CSS cache-buster from file mtime, language code/name, support URL, `nx_show_social` |
| 51 | Forces `login_with_email_link = 0`, so the stock "Login with Email Link" option is not offered. The backend endpoint `frappe.www.login.send_login_link` is NOT disabled (it remains whitelisted in Frappe). |
| 52-54 | With `SHOW_SOCIAL_LOGIN = False` (line 16), forces `social_login=False`, `provider_logins=[]`. Social login still works in the backend; only the buttons disappear. |
| 74-81 | `_support_url()`: site config `nxerp_support_url` if it starts with `mailto:`, `https://`, `http://` or `/`; otherwise a Gmail compose URL to the hard-coded `[support email]` (line 17) |

- Redirect logic: none of its own. FACT: when the user is already logged in, `frappe_login_context` raises `frappe.Redirect` (Frappe `frappe/www/login.py:32-41`) and NXERP's `get_context` does not catch it, so the redirect propagates. Target is the sanitised `redirect-to` param, else `get_default_path()` or `/desk` (Website Users: `get_default_path() or get_home_page()`).
- Sign-up: not disabled by NXERP. FACT: the stock template shows a "Sign up" link when Website Settings `disable_signup` is 0 (`frappe/www/login.html:113-116,129-132,206-209`); `login.py` does not alter `disable_signup`. The WIP CSS and committed CSS style a `.sign-up-message` class (css:276-279) that was not confirmed to exist in the 16.53.0 template. NOT VERIFIED at runtime.
- Forgot password: stock flow (`for-forgot` section, `frappe/www/login.html:153`).
- Social login: see above. Email link: see above.

### 4.4 What `login.html` adds

- FACT: Hero panel (marketing copy in English wrapped in `_()`), card containing `{{ super() }}` (Frappe's full login sections), "Need help? Contact IT Support" link, language picker using `frappe.translate.get_all_languages` and a `preferred_language` cookie (login.html:224-263), "Keep me signed in" checkbox stored only in `localStorage` key `nxerp_keep_signed_in` (login.html:134-151; it has no server-side effect, FACT: nothing reads that key).
- FACT: replaces headings "Welcome Back" etc. by DOM text edits. If selectors do not match nothing changes (see 3.4).
- FACT: `Verifying...` and `Sign In` strings in the JS are used to detect button state (login.html:181); Frappe 16's button text is "Continue".
- ASSUMPTION: the "Keep me signed in" checkbox may mislead users because it does not change session duration.

### 4.5 `helpdesk/nxerp_branding.py`

- FACT: defines `apply_branding()` and `brand_help_menu()`; run manually via `bench --site <site> execute helpdesk.nxerp_branding.apply_branding` (docstring, lines 12-16).
- FACT: it writes `HD Settings.{brand_name,brand_logo,favicon}`, `Website Settings.{app_name,app_logo,favicon,splash_image}`, `Navbar Settings.app_logo`, `System Settings.app_name` using `frappe.db.set_single_value`, prints old -> new values, then calls `brand_help_menu()` (hides help items labelled "About" and "Frappe Support", appends "IT Support" route item) and `frappe.clear_cache()`.
- FACT: nothing in the repo calls it (`grep -rn "apply_branding\|nxerp_branding"` outside the file returned nothing): not in `after_install`, patches, or docs.
- FACT: it changes site-wide `System Settings.app_name` and Website Settings, i.e. it brands the whole Frappe site "NXERP", not only Helpdesk. DECISION needed (section 11) whether Helpdesk should be allowed to do that when NXERP is the umbrella.
- FACT: `brand_help_menu` imports `_support_url` from `helpdesk.www.login` (line 38), coupling the helper to the login module.

---

## 5. Branding map

Counts: `git grep -Iic` on HEAD, `.po/.pot/.lock/.csv` excluded; "matches" = matching lines.

### 5.1 "NXERP" (case-insensitive) in HEAD

| Directory | Files | Lines |
|---|---|---|
| `helpdesk/www/` (login.py 10, login.html 6) | 2 | 16 |
| `desk/src/` (PersonaForm 5, HDLogo 2, Sidebar 2, emailConfig 1, EmailProviderIcon 1) | 5 | 11 |
| `helpdesk/nxerp_branding.py` | 1 | 7 |
| `helpdesk/hooks.py` | 1 | 6 |
| `helpdesk/public/` (nxerp-login.css) | 1 | 3 |
| `helpdesk/setup/` (welcome_ticket.py) | 1 | 3 |
| `desk/vite.config.js` | 1 | 3 |
| `desk/index.html` | 1 | 2 |
| `helpdesk/templates/` (emails/macros.html) | 1 | 1 |
| Tests, e2e, `.github`, patches, README, docs | 0 | 0 |
| Total | 14 files | 52 lines |

FACT: no test and no patch references NXERP. FACT: `locale/*.po` files were excluded from counts; 33 `.po/.pot` files in HEAD still contain "Frappe Helpdesk" (`git grep -l` count) because translations were not regenerated.

### 5.2 Main NXERP spots

| Surface | Where | Value | Evidence |
|---|---|---|---|
| Desk apps screen | `hooks.py:12-20` | title "NXERP", logo `nxerp-mark.png`, route `/helpdesk` | FACT |
| App title | `hooks.py:2` | `app_title = "NXERP"` | FACT |
| Logo/favicon/splash | `hooks.py:23-27` | NXERP wordmark/favicon | FACT |
| SPA title/PWA | `desk/index.html` title and apple title; `desk/vite.config.js` manifest name/short_name/description ("NXERP - Smarter Systems for a Brighter Tomorrow") | NXERP | FACT |
| Sidebar help modal / mobile | `Sidebar.vue:51,426` | "NXERP", "NXERP Mobile" | FACT |
| Sidebar logo | `HDLogo.vue:2,7` | NXERP mark | FACT |
| Onboarding wizard | `PersonaForm.vue:164,210,218,233,245` | "NXERP" wording | FACT |
| Email provider labels | `EmailProviderIcon.vue:32`, `emailConfig.ts:244` | "NXERP Mail" | FACT |
| Welcome ticket / emails | `welcome_ticket.py:12,46,49`, `templates/emails/macros.html:26` | "Team NXERP", "NXERP IT support team" | FACT |
| Login | `www/login.py:9-13`, `www/login.html` | brand constant, logos | FACT |
| Site settings (DB, manual) | `nxerp_branding.py` | HD Settings, Website Settings, Navbar Settings, System Settings | FACT (script exists), NOT VERIFIED (never run here) |

### 5.3 Where upstream Frappe/Helpdesk branding still remains (HEAD)

| Pattern | Directory: files/lines | Notes |
|---|---|---|
| "Frappe Helpdesk" | `.github` 2f/9, `AGENTS.md` 1f/3, `README.md` 1f/7, `helpdesk/config` 1f/1, `helpdesk/helpdesk` 1f/1 | workflow titles, docs, a doctype/module config |
| "Frappe Cloud" | `README.md` 2 | |
| `frappe.io` | `desk/src` 16f/19 (mostly `docs.frappe.io/helpdesk/...` help links in Settings pages, Sidebar.vue:53,172, MobileSidebar.vue:124), `README.md` 11, `.github` 7, `helpdesk/overrides` 6, `helpdesk/helpdesk` 2, `hooks.py:7` (`app_email`), `pyproject.toml` 2 (authors/urls), `helpdesk/setup` 1 (welcome_ticket doc link line 41) | user-visible docs links still point to Frappe docs |
| "Frappe Technologies" | `helpdesk/helpdesk` 99f (licence headers), `hooks.py:3` (`app_publisher`), `pyproject.toml`, several modules | copyright/publisher |
| "Frappe Mail" | `desk/src` 4f/8 (service id `"Frappe Mail"` in `emailConfig.ts:241,269,288`, EmailAdd, EmailEdit), `helpdesk/api` 2, `helpdesk/overrides` 3, e2e 1 | stored service id deliberately unchanged |
| `frappecloud` / Frappe Cloud integration | `desk/src/composables/fc.ts:5,9`, `helpdesk/www/helpdesk/index.py:3` (`is_fc_site`), `.github` 1, README 2 | integration code, user-facing text partly reworded |
| Word "Helpdesk" | `desk/src` 14 lines (e.g. `UserMenu.vue:24` and `Preferences.vue:29` fall back to "Helpdesk" when `brandName` is empty; `TicketCustomer.vue:416`, `MobileTicketAgent.vue:572` set `document.title = "Helpdesk"`), `helpdesk/setup` 5 (welcome ticket subject "Welcome to Helpdesk" `welcome_ticket.py:78`; folder "Helpdesk" `file.py:6`), `helpdesk/api` 2 (`onboarding.py:28,41` match that subject), `helpdesk/helpdesk` 53, `e2e` 5 | Some are code identifiers, others user-visible |
| Doctype module name | `hd_settings.json:570` `"module": "Helpdesk"` | |
| Locale | 33 `.po/.pot` with "Frappe Helpdesk" | |
| Upstream `app_email` | `hooks.py:7` upstream company address | |
| Docs/screenshots | `desk/public/{article,article-2,ticketActivity,timers}.png`, `screenshot.webp` | not inspected; NOT VERIFIED whether they show Frappe branding |

FACT: `desk/src/components/UserMenu.vue:24` shows `config.brandName || "Helpdesk"`. Therefore after `apply_branding()` (brand_name = NXERP) the user-menu button reads "NXERP ..." and the e2e selector `/^Helpdesk /` in `e2e/tests/auth.spec.ts:17` would no longer match. Not run; derivation from code.

FACT: upstream strings reworded in the commit: "Login to Frappe Cloud", "Frappe Discuss", "A Frappe partner or consultant", "frappe.io" placeholders (diff in 3.1).

---

## 6. `/helpdesk` route table

### 6.1 Server side

| URL | Handler | Evidence | Who can reach it |
|---|---|---|---|
| `/helpdesk` and `/helpdesk/<any>` | `website_route_rules` maps `/helpdesk/<path:app_path>` -> route `helpdesk` (`hooks.py:57-62`); `helpdesk` resolves to `helpdesk/www/helpdesk/index.html` + `index.py` | FACT | Everyone including Guest: the server renders the SPA shell; no server redirect for guests (`index.py:13-20`, no `frappe.Redirect`) |
| (build artefact) `helpdesk/www/helpdesk/index.html` | produced by `vite build` (`pyproject.toml:25`, `desk/vite.config.js` `indexHtmlPath`); gitignored (`.gitignore:43`); also `helpdesk/public/desk` gitignored (`.gitignore:40`) | FACT | FACT: neither exists in the WIP tree or HEAD checkout (`ls`), so `/helpdesk` cannot render until `bench build --app helpdesk` runs |
| `helpdesk.www.helpdesk.index.get_context_for_dev` | `@frappe.whitelist(methods=["POST"], allow_guest=True)`, throws unless `developer_mode` (`index.py:23-27`) | FACT | Guests, only in developer mode |
| `/login` | `helpdesk/www/login.*` (section 4) | FACT | Everyone; logged-in users are redirected away |
| `/desk` | hard-coded to the Frappe Desk template (`path_resolver.py:44`) | FACT | Desk-access users |
| `/apps` | Frappe app launcher when more than one app is on the apps screen (`frappe/apps.py:106-110`) | FACT | Logged-in users |

Boot data injected into the SPA shell (`index.py:30-54`): `default_route "/helpdesk"`, site name, csrf token, `session_user`, `agent` (HD Agent name or None), date/time formats, timezone, `lang`, `dir`, installed `apps`, telemetry. WIP adds `desk_theme`.

### 6.2 API entry points that gate the SPA

| Endpoint | Guard | Evidence |
|---|---|---|
| `helpdesk.api.auth.get_user` | `@frappe.whitelist()` (login required); returns `has_desk_access, is_admin, is_agent, has_agent_record, is_manager, user_teams, availability, persona_captured...` | FACT `helpdesk/api/auth.py:7-78` |
| `helpdesk.api.config.get_config` | `allow_guest=True` (brand name/logo, restriction flags) | FACT `helpdesk/api/config.py:4` |
| `helpdesk.api.permission.has_app_permission` | apps-screen visibility: Administrator or roles Agent/Agent Manager/System Manager/HD Customer/HD Customer Manager | FACT `helpdesk/api/permission.py:3-17`, `hooks.py:18` |
| `helpdesk.auth.authenticate` | only when site config `block_endpoints` is truthy; blocks non-System-User calls to `/api/` paths except allow-lists, `/helpdesk*`, `/api/method/helpdesk.*`, telephony | FACT `helpdesk/auth.py:72-105` |

### 6.3 Frontend router (`desk/src/router/index.ts`, base `/helpdesk/`, line 225)

| SPA path | Name | Component | Meta | Reachable by |
|---|---|---|---|---|
| `/onboarding` | Persona | `PersonaForm.vue` | `beforeEnter` = `canViewPersona` (line 211) | logged-in, desk access, admin, persona not captured (`persona.ts:33-40`) |
| `/` (redirect `""` -> `/home`) | PortalRoot | `roots/PortalRoot.vue` picks AgentRoot or CustomerPortalRoot | | see 7 |
| `/home` | Home | `pages/home/Home.vue` | none | desk-access users; customers bounced to `TicketsCustomer` (guard line 251) |
| `/tickets` | TicketsAgent | `ticket/Tickets.vue` | none | agents/admins (customers bounced) |
| `/tickets/:ticketId` | TicketAgent (mobile variant `MobileTicketAgent`) | | non-agents redirected to `TicketCustomer` (line 245) | agents |
| `/tickets/new/:templateId?` | TicketAgentNew | `TicketNew.vue` | onSuccessRoute | agents |
| `/notifications`, `/kb`, `/kb/articles/:articleId`, `/articles/new/:id`, `/search`, `/customers[/:id]`, `/contacts[/:id]`, `/dashboard`, `/call-logs` | various | agent pages | `/search` has `auth: true` | desk-access users |
| `/agents`, `/teams`, `/teams/:teamId` | redirect to `/tickets` | | | |
| `/my-tickets`, `/my-tickets/:ticketId`, `/my-tickets/new` | TicketsCustomer, TicketCustomer, TicketNew | | `public: true, auth: true` | any logged-in user (customers, agents) |
| `/kb-public`, `/kb-public/:categoryId`, `/kb-public/articles/:articleId` | Customer KB | | `public: true, auth: true` | any logged-in user |
| `/:pathMatch(.*)*` | Invalid Page | | | any logged-in user |

FACT: `meta.public` means "customer-portal chrome", not "anonymous": every public route also has `auth: true`, and `beforeEach` sends non-logged-in visitors to login regardless (`index.ts:239-244`). FACT: `meta.auth`, `meta.agent`, `meta.admin` are declared (lines 13-19) but only `public` is read in `beforeEach`; `agent`/`admin` meta are not used in this file.

FACT: `website_redirects`, `page_renderer` and `website_path_resolver` are not defined in `hooks.py` (`grep -n` returned no match); `hooks.py:57-62` is the only route rule.

---

## 7. Agent vs customer vs admin

### 7.1 Server functions (HEAD)

`helpdesk/utils.py:35-43`:
```python
def is_admin(user: str = None) -> bool:
    user = user or frappe.session.user
    return user == "Administrator"
```
`helpdesk/utils.py:46-61`:
```python
def is_agent(user: str | None = None) -> bool:
    user = user or frappe.session.user
    if is_admin(user):
        return True
    # a deactivated agent keeps their roles; the record decides when there is one
    active = frappe.db.get_value("HD Agent", user, "is_active")
    if active is not None:
        return bool(active)
    roles = frappe.get_roles(user)
    return "Agent Manager" in roles or "Agent" in roles
```
`helpdesk/utils.py:64-75`: `get_agent_name` returns the user when an HD Agent doc named after the user exists, else None.
`helpdesk/utils.py:181-195` `agent_only` decorator (raises PermissionError when `not is_agent()`). `helpdesk/utils.py:198-206` `is_agent_manager`: roles intersect `{"Administrator", "System Manager", "Agent Manager"}`; `agent_manager_only` at 209.
`helpdesk/api/auth.py:27-33,49`:
```python
roles = frappe.get_roles(current_user)
is_admin = "System Manager" in roles or "Administrator" in roles
is_agent = _is_agent()
agent_name = get_agent_name()
has_agent_record = bool(agent_name)
has_desk_access = is_agent or is_admin
...
is_manager = ("Agent Manager") in frappe.get_roles(current_user)
```
FACT: two different "admin" definitions exist: `utils.is_admin` = user is literally `Administrator`; `api.auth.get_user.is_admin` = holds role System Manager or Administrator. FACT: `is_manager` in `get_user` is only the "Agent Manager" role (System Manager alone is not a manager there), while `is_agent_manager` includes System Manager.

`HD Agent` (`helpdesk/helpdesk/doctype/hd_agent/hd_agent.py`): `before_save` sets `name = user` and calls `set_user_roles` which appends role "Agent" (lines 44-48, 102-106); `has_permission` lets only the agent or a manager write/delete their record (109-120). Roles in play: `Agent`, `Agent Manager`, `System Manager`, `Administrator`, `HD Customer`, `HD Customer Manager` (`hooks.py:65-80`, `permission.py:3-9`). Customer roles are created with `desk_access = 0` and `home_page = "/helpdesk"` (`setup/install.py:216-230`); Portal Settings `default_role = HD Customer`, `default_portal_home = /helpdesk` on fresh install (`install.py:232-250`).

### 7.2 Frontend

- `desk/src/stores/auth.ts:15-62`: `isAdmin`, `isAgent`, `hasAgentRecord`, `isManager`, `hasDeskAccess` are computed from `helpdesk.api.auth.get_user`; `isLoggedIn` comes from the `user_id` cookie (lines 64-73), treating `Guest` as logged out.
- `desk/src/roots/PortalRoot.vue:18-25`: `hasDeskAccess && isAgent` -> `AgentRoot`, else `CustomerPortalRoot`. Comment: the chrome follows the session, not the URL.
- Router guard (`desk/src/router/index.ts:229-256`): `isCustomerPortal = to.meta.public`; fetch user info; `personaInterrupt`; not logged in -> hard redirect to login; `TicketAgent` for non-agent -> `TicketCustomer`; non-public route without desk access -> `TicketsCustomer`.
- Persona onboarding gate: `desk/src/persona.ts:33-52` (admin only, only if telemetry enabled and not captured).

### 7.3 Behaviour by actor (derived from the code above; NOT exercised at runtime)

| Actor | Server shell `/helpdesk` | SPA behaviour |
|---|---|---|
| Guest | Shell renders (no server redirect) | `isLoggedIn` false -> `window.location.href` to login with `redirect-to` (section 8). `get_user` is not called (`index.ts:232` only inits when logged in). |
| Customer (Website User, role HD Customer / HD Customer Manager, no agent record) | Shell renders | `is_agent` false (no HD Agent doc and no Agent role), `has_desk_access` false unless also System Manager -> `CustomerPortalRoot`; non-public routes redirect to `TicketsCustomer` (`/my-tickets`). e2e expects this (`auth.spec.ts:39-45`). |
| Agent (HD Agent active, or role Agent/Agent Manager with no HD Agent doc) | Shell renders | `AgentRoot`; full agent routes; can still open `/my-tickets` pages with agent chrome. |
| Agent Manager | same as agent | `is_manager` true; `is_agent_manager` true for server checks |
| Deactivated agent (HD Agent `is_active=0`) | same | `is_agent` false even if roles remain (utils.py:56-59); has_desk_access false unless System Manager |
| System Manager without HD Agent doc/role | same | `is_admin` true, `is_agent` false, `has_desk_access` true; `PortalRoot` requires `isAgent` too, so the customer shell is used even though desk access is true. NOT VERIFIED visually. |
| Administrator | same | `is_agent()` always true (utils.py:54-55) |

---

## 8. Guest redirects

FACT chain for an anonymous visit to `/helpdesk/tickets/42`:
1. Server returns the SPA shell (no redirect; `index.py:13-20`).
2. Router `beforeEach` (`desk/src/router/index.ts:239-244`): `isLoggedIn` false (cookie `user_id` absent or `Guest`, `auth.ts:64-73`), builds `redirectURL = to.fullPath !== "/" ? to.fullPath : ""`, then does a full page navigation:
```ts
window.location.href =
  LOGIN_PAGE +
  (redirectURL ? `?redirect-to=/helpdesk${redirectURL}` : "/helpdesk");
```
with `LOGIN_PAGE = "/login"` (line 9). e2e asserts `/login?redirect-to=/helpdesk/tickets` (`auth.spec.ts:9`).
3. On `/login` (Frappe's `get_context`, via NXERP wrapper) the param is read as `redirect-to` and passed through `sanitize_redirect` (`frappe/www/login.py:29-30,206-226`): same-host URLs and relative paths are kept; a foreign host is replaced by `/desk`.
4. After successful sign-in the client JS uses `frappe.utils.sanitise_redirect(frappe.utils.get_url_arg("redirect-to")) || data.home_page` (`frappe/templates/includes/login/login.js:327` area); `sanitise_redirect` returns "" for a different origin (`frappe/public/js/frappe/utils/common.js:327-346`).
5. Logout: `window.location.href = LOGIN_PAGE` (`auth.ts:80`). A failed `users` fetch with `AuthenticationError` also goes to `/login` (`stores/user.ts:23-26`).

Observations (FACT about code, runtime NOT VERIFIED):
- FACT: when the Guest lands on the root `/helpdesk` (SPA `fullPath` "/"), the ternary yields `"/login" + "/helpdesk"` = `/login/helpdesk`, not `/login?redirect-to=/helpdesk`. This looks like an upstream bug (file unchanged in the fork's diff). What `/login/helpdesk` resolves to was not verified.
- FACT: `redirect-to=/helpdesk${redirectURL}` is not URL-encoded; a `fullPath` containing `?a=b&c=d` would be split at `&`. Minor.
- Open-redirect note (not fixed): the SPA only builds same-origin paths; Frappe sanitises both server and client. No open redirect found in the code paths read. Server-side `sanitize_redirect` keeps `scheme`/`netloc` from the request; protocol-relative URLs (`//host`) have a netloc and are handled. Not fuzzed.
- FACT: `helpdesk/www/login.py` adds no redirect logic of its own.
- FACT: logged-in users hitting `/login` are redirected using `get_default_path()` (`frappe/apps.py:92-110`): with one non-frappe app on the apps screen the route of that app; more than one app (e.g. Helpdesk + ERPNext) -> `/apps` or `/desk`. So a Helpdesk user may land on `/apps` instead of `/helpdesk` unless `redirect-to` or a default app is set. Roles HD Customer have `home_page /helpdesk` (install.py:224). Website Users use `get_default_path() or "/" + get_home_page()` after login (`frappe/auth.py:197-200`). System Users get `get_home_page() or "/desk"` (`frappe/auth.py:205`). Runtime NOT VERIFIED.

---

## 9. Tests (static inventory; see bootstrap-evidence.md section 4 for the run: 552/559 backend pass)

### 9.1 Inventory (HEAD)

| Suite | Location | Count | Runner |
|---|---|---|---|
| Python unit/integration (Frappe test runner) | 54 files named `test_*.py` or under `helpdesk/tests/`; 38 define at least one `def test_`; 559 `def test_` functions | `bench --site test_site run-tests --app helpdesk --coverage` (`.github/workflows/server-tests.yml`, run step) |
| Biggest files | `hd_ticket/test_hd_ticket.py` 129, `integrations/erpnext/test_erpnext_integration.py` 45, `hd_saved_reply/test_hd_saved_reply.py` 32, `tests/test_core_comments.py` 28, `hd_customer/test_hd_customer.py` 27, `hd_agent_status` 23, `hd_agent` 22 | |
| API tests | `helpdesk/tests/api/**` (agent_home, settings, article, assignment_rule, banners, contact, customer_portal_notice, dashboard, doc_fields, doc_filters, doc_list, onboarding, permission, tags, ticket_analytics, ticket_stats) | |
| Base classes | `IntegrationTestCase` 29 files, `FrappeTestCase` 18 files, `UnitTestCase` 2 files | FACT `git grep -l`; Frappe 16.53.0 flags `FrappeTestCase` as deprecated (`frappe/tests/test_test_utils.py:43-56`) |
| Playwright e2e | `e2e/tests/**` 28 `*.spec.ts` files, 145 `test(` calls (heuristic count) + `e2e/global.setup.ts`, 12 helpers; config `playwright.config.ts` (1 worker, Chromium, base URL `BASE_URL` or `http://localhost:8000`) | `yarn test:e2e` (`package.json:7`); CI `.github/workflows/ui-tests.yml` runs `npx playwright test --shard=N/2` |
| Vitest/Jest (frontend unit) | none: no vitest/jest in `desk/package.json` or `package.json`; no `*.test.*`/`*.spec.*` under `desk/` | FACT grep |
| Login/branding tests | none (no test references the NXERP login, `login.py` or `nxerp_branding`) | FACT |

### 9.2 CI workflows

| Workflow | Trigger | What it does | Note |
|---|---|---|---|
| `server-tests.yml` | PRs to main/main-hotfix/develop (paths-ignore js/css/md/html/csv) | MariaDB 10.6, Python 3.14, Node 24, `install.sh` (frappe `develop`, erpnext develop, telephony, helpdesk), `bench ... run-tests --app helpdesk --coverage`, upload to Codecov | needs Frappe 16 |
| `ui-tests.yml` | PRs to develop touching `desk/**`, `e2e/**`, etc.; manual | bench with `FRAPPE_BRANCH=develop`, `bench build --apps frappe,helpdesk`, 2 Playwright shards, merges reports | |
| `lint.yml` | PRs | commitlint, pre-commit (black 25.11.0, flake8 7.3.0 strict, prettier 2.6.2, isort 5.12.0), Semgrep rules; WIP adds `theme-tokens` job | |
| `build.yml` | push main / tags / manual | builds a container from `frappe/frappe_docker`, `FRAPPE_BRANCH=version-15`, apps telephony develop + helpdesk main, verifies apps, pushes to ghcr.io. It builds upstream `frappe/helpdesk` `main`, not this fork | FACT `build.yml` lines (`apps.json` echo) |
| `assets.yml` | push develop/main | prebuilds assets via `frappe/pilot` reusable workflow | |
| `release.yml`, `on_release.yml`, `generate-pot-file.yml` | release / manual | semantic release, release notes, POT generation (python 3.14 / node 24) | |

### 9.3 Static checks that ran

- FACT: `python -I` with `ast.parse` over all 291 tracked `*.py` in the clean checkout: 0 syntax errors. Python 3.14.3 is installed here; Node v24.18.0 is installed here (`python --version`, `node --version`).
- FACT: `ruff` and `black` are not installed here (`command not found`). `.flake8` and `.pre-commit-config.yaml` are present in the repo.
- No Frappe site, bench, MariaDB or Redis was available, so no Frappe test, e2e test or build was run. Status of every suite: **NOT YET RUN**.

### 9.4 Gaps relevant to the fork

- FACT: existing e2e login test (`auth.spec.ts:7-23`) depends on text "Continue" and a user-menu button matching `/^Helpdesk /`; both are affected by NXERP branding choices (sections 3.4, 5.3).
- FACT: no test covers the login page customisation, `apply_branding`, or the committed branding strings. The WIP adds 3 python tests (`helpdesk/tests/api/test_theme.py`) and 3 e2e tests (`e2e/tests/theme.spec.ts`).

---

## 10. Historical enhancements (a)-(f)

Method: read HEAD code for each; searched `git log --all -S` and `--grep`. Status describes code completeness only; none was exercised at runtime. WIP (uncommitted) touches none of these (no theme file edits assignment, team, unseen or mention logic; the only related WIP edit is chart colouring in `AgentTicketsCard.vue`).

| # | Requirement | Status | Evidence / reasoning |
|---|---|---|---|
| a | Per-agent badge with count of unseen tickets assigned to them | ABSENT | FACT: no code computes or displays such a count. `grep -i unseen\|unread\|badge` over `helpdesk/` and `desk/src/` found only: (1) the notification-bell badge `notificationStore.unread` (`desk/src/components/layouts/AppSidebar.vue:234,242`, `stores/notification.ts:19`) which counts unread Notification Log rows, not unseen assigned tickets; (2) per-row bold subject for tickets the user has not opened (`desk/src/pages/ticket/Tickets.vue:176-181`, using Frappe `_seen`, `hd_ticket.json:633` `track_seen`, `mark_seen` at `hd_ticket.py:936-941`). No API like `unseen_count` exists; `git log --all -S"unseen_count"` and `-S"unseen_tickets"` returned nothing. Closest building blocks: `_seen` (per ticket) and `_assign`. |
| b | Team shown above Assignee in ticket overview/sidebar | ABSENT on desktop, PRESENT in mobile header | FACT: desktop `desk/src/components/ticket-agent/TicketDetailsTab.vue:33-41` renders "Assignee" first, then the core fields in `CORE_FIELDS = ["priority","ticket_type","customer","agent_group"]` (line 188), so Team (agent_group) is last, below Assignee. FACT: mobile header `desk/src/pages/ticket/MobileTicketAgent.vue:41-75` renders the Team picker before `AssignTo` (upstream commit 2423771f3 is on another branch, not in HEAD ancestry; the code is nevertheless in HEAD). Not an NXERP change. |
| c | Assignee dropdown filtered by selected Team | PARTIAL | FACT: `desk/src/components/ticket-agent/AssignTo.vue:292-340` filters agents to team members (`teamMembers` from `helpdesk...hd_team.get_team_members`, hd_team.py:120-121) only when `configStore.teamRestrictionApplied && configStore.assignWithinTeam && ticketTeam` (lines 293-298). Both flags are HD Settings checkboxes: `restrict_tickets_by_agent_group` and `assign_within_team` (default `"0"`, `depends_on restrict_tickets_by_agent_group`, `hd_settings.json:390-396`). Upstream feature (commits 3eedfe890 2025-07-30, 4d2424d32 2026-09-29, both ancestors of HEAD). So the logic is complete but is opt-in and default off. Server side does not enforce it for `assign_agent` (`hd_ticket.py:479-483`): NOT VERIFIED whether another path enforces it. |
| d | Assignee reset/refresh when Team changes | PARTIAL | FACT UI: after `agent_group` is saved, `assignees.value.reload()` runs (`TicketDetailsTab.vue:355-364`) and `AssignTo.vue:322-331` re-fetches team members when `ticketTeam` changes; it does not clear the displayed assignee by itself. FACT server: `HDTicket.on_update` calls `remove_assignment_if_not_in_team` (`hd_ticket.py:247,422-442`): when `agent_group` changed on an Open ticket, the current assignee is not a member of the new team AND the new team has an enabled Assignment Rule with users (`users_present_in_team_assignment_rule`, 453-472), all assignments are cleared (`clear_all_assignments`). Conditional: no clearing if the team has no rule, or the ticket is not Open, or `_assign` is empty. |
| e | Same behaviour on ticket create AND edit | ABSENT for create (agent UI) | FACT: agent create page `desk/src/pages/ticket/TicketNew.vue` contains no `AssignTo`, no `agent_group` and no assignment code (grep returned nothing); it renders template fields (`visibleFields`, lines 23-35) plus subject/description. Whether Team can appear on create through a ticket template field is NOT VERIFIED. Team and Assignee behaviour is implemented on edit only (TicketDetailsTab/AssignTo/MobileTicketAgent). Server-side `remove_assignment_if_not_in_team` returns immediately for new docs (`hd_ticket.py:426-427`). |
| f | Comments and @mentions used for manager notification | PARTIAL (mechanism exists; no manager-specific targeting) | FACT: internal comments are agent-only (`helpdesk/extends/comment.py:15-22` before_insert, 74-91 read gate). The editor offers an `@` list of every active HD Agent (`desk/src/stores/agent.ts:6-20`, `CommentTextEditor.vue:136,170`), not only managers. Frappe core turns mentions into Notification Log rows (`frappe/core/doctype/comment/comment.py:7,60` calls `notify_mentions`; Helpdesk docstring `helpdesk/notifications.py:1-7`: "Mentions and assignments are created by core itself"). Helpdesk adds `Notification Log.link` for tickets (`extends/notification_log.py:4-6`) and deep-links the comment (`stores/notification.ts:28-42`). Test: `helpdesk/tests/test_core_comments.py:118` (mention notification). There is no code that notifies "Agent Manager" role members automatically; `grep "Agent Manager"` in `notifications.py`, `extends/`, and `hd_ticket.py` returned no notification logic. Reopen notifications go to assigned agents only (`notifications.py:113-136`). |

Historical search facts:
- FACT: `git log --all -S"unseen"` hits only upstream commits (e6dea3be6, e02179371, 993eba6a4, 1654d26f8, 79feeb15a); none implement an assigned-unseen badge.
- FACT: no branch of the `company` remote contains such work: `company/develop` equals upstream snapshot, `company/feature/nxerp-login-page` equals HEAD, `company/nxerp-stable` differs from upstream only by login/branding/CI commits (2.x, 1.3).
- ASSUMPTION: enhancements (a)-(f) were requested/planned in conversations earlier than these commits; no trace of them exists in any local or `company` ref searched, except upstream-native items (c), (d), (f).

---

## 11. Open questions and risks

### Risks (FACT-based)

1. Version mismatch. HEAD needs Python 3.14 and Frappe 16 (`pyproject.toml:7,19`). If the live site is Frappe 15 (ASSUMPTION from project memory), HEAD cannot be installed on it; `company/nxerp-stable` (v1.30.2, Frappe 15.122 image pin) is the compatible line. They share identical login code but differ in everything else.
2. The login customisation selects classes (`.btn-login`, `.forgot-password-message`, `.login-divider`) absent from Frappe 16.53.0's template. On Frappe 16, part of the NXERP layout/JS silently does nothing (3.4).
3. WIP/commit inconsistency: committed files do not reference WIP assets, but WIP edits to tracked files do reference untracked files (3.3). A partial commit breaks the login page or the desk build.
4. Branding identity. FACT: Helpdesk's `app_title`, apps-screen title, PWA name, sidebar title and onboarding text are all set to "NXERP" (`hooks.py:2,12-20`, `vite.config.js`, `Sidebar.vue:51`). Per the stated naming rule, Helpdesk should not be called NXERP. DECISION needed.
5. `apply_branding()` rewrites site-wide `System Settings.app_name` and Website Settings, not only Helpdesk settings (4.5); it is not wired to any installer so state of a site is whatever was last run by hand. It also hides standard Help menu entries.
6. Hard-coded support mailbox in `login.py:17` (a personal-style mailbox address; value not reproduced here). Override via `nxerp_support_url` site config exists.
7. Frontend not built in the working tree: `helpdesk/www/helpdesk/index.html` and `helpdesk/public/desk` are absent (gitignored build outputs) so `/helpdesk` will not serve until `bench build`.
8. Guest at `/helpdesk` root is sent to `/login/helpdesk` by the router code (8); behaviour not verified.
9. `sync.mjs:13` writes to a path outside the repo (`../NXERP/nxerp/nxerp/public/css`). Running `yarn theme:build` could create or modify files in another repository.
10. "Keep me signed in" checkbox has no server effect (4.4).
11. Social login and email-link login are hidden in UI only; backend endpoints remain active (4.3). Self sign-up depends on Website Settings.
12. Upstream documentation links, licence headers, `app_publisher`/`app_email`, 33 translation files and the doc screenshots still carry Frappe branding (5.3). Some are legal (licence headers) and should arguably stay.
13. Two "admin" notions (`utils.is_admin` vs `api.auth.get_user`) and manager notions (7.1). A System Manager without agent record gets desk access but the customer shell (PortalRoot requires `isAgent`).
14. Frappe 16.53.0 marks `FrappeTestCase` deprecated; 18 files (including WIP `test_theme.py`) use it.
15. Features (a), (b desktop), (e create) are not present; (c), (d), (f) exist only as upstream opt-in/conditional behaviours.
16. Test status unknown: **NOT YET RUN**; the existing e2e login test text ("Continue", "Helpdesk" menu name) may disagree with branding and the NXERP login.

### Questions / DECISIONS needed (none decided here)

- Which base line is the target: `nxerp-stable` (v1.30.2, Frappe 15) or `develop` (Frappe 16, Python 3.14)? What Frappe/Python version does the production NXERP stack run?
- Should Helpdesk carry the NXERP brand, or stay "Helpdesk" under NXERP umbrella? Who owns site-wide `System Settings.app_name`?
- Should `/login` for the whole site be overridden by Helpdesk's www page (load-order dependent), or should NXERP own `/login` in a platform-level app installed last?
- Should the theme sync script write into the NXERP repo, and is the theme meant for Helpdesk only?
- Which of (a)-(f) are still required, and are they to be built on upstream's existing team-restriction settings (default off)?
- Where does a Helpdesk user land after login when ERPNext is also installed (`/apps` vs `/helpdesk`)?
- Is the e2e suite to be adapted to NXERP branding?

### Could not verify (summary)

- Frappe 15 template structure and behaviour (no v15 source locally); behaviour of `/login/helpdesk`.
- Any runtime behaviour: login page rendering, route resolution, role handling, notifications, assignment clearing.
- Contents of 12 upstream commits behind `origin/develop`; conflict likelihood.
- What the WIP `AGENTS.md` change is; whether `.gitattributes` exists.
- Whether ticket templates can expose Team on create.
- Whether images/screenshots in `desk/public/` and `screenshot.webp` show Frappe branding.
- The directory `../NXERP/nxerp/nxerp/public/css` targeted by `sync.mjs` (not opened).
