# Coding standards

Short, enforceable rules for the `nxerp` repo. The project rules in [CLAUDE.md](../../CLAUDE.md) and the process in
[CONTRIBUTING.md](../../CONTRIBUTING.md) come first; this page is the detail. Where a tool enforces a rule it is named, because a
rule nobody checks is not a standard.

## Python (this repo)

- **Frappe conventions, tabs for indentation, double quotes.** The configuration is `pyproject.toml` (`[tool.ruff]`: line length 110, target `py314`; lint set `F, E, W, I, UP, B, RUF`; `[tool.ruff.format]`: tabs) and `.editorconfig`. `W191` (tabs) and `E501` (line length) are deliberately ignored by the linter; the formatter decides wrapping.
- **Run the tools, do not hand-format:** `pre-commit run --all-files`, or directly `ruff check .` and `ruff format --check .`. CI runs the same through pre-commit.
- **Python 3.14 only.** `ruff format` for the `py314` target writes `except A, B:` without parentheses (PEP 758; see `nxerp/registry.py`). That is valid only on 3.14 and only without `as`. Do not "fix" it by hand, and do not run the code on an older interpreter.
- Imports sorted by ruff (`I`). Type hints use the modern forms (`str | None`, `list`, not `Optional`/`List`).
- **No cross-app imports (ADR-005).** `nxerp` never imports `erpnext`, `helpdesk`, `hrms`, `payments`, `telephony` or any app listed in `deploy/apps.json`, and no app imports `nxerp`. A dotted path in a **string** for `frappe.get_attr`, a hook or a registry entry is not an import and is fine. `nxerp` declares no `required_apps`. `python3 -I tools/check_architecture.py` and `nxerp/tests/test_architecture.py` enforce this ([testing.md](testing.md)).
- **Platform code goes in `nxerp/`; an app's code stays in its repo.** Do not park platform code (login, launcher, resolver, registry) inside an app, and do not copy an app's code here.
- **Hyphenated `www` pages need underscore controllers.** Frappe resolves the controller of `www/nxerp/no-access.html` as `no_access.py`. A controller named `no-access.py` is silently never run (this happened in Phase 2 and left a page unguarded). Rule: a page named `a-b` has a controller `a_b.py`, and a test must prove the controller runs (a guard that was never executed is not a guard).
- **Patches are idempotent and listed in `patches.txt`** (`[post_model_sync]` for anything that needs the DocTypes). A patch that runs twice must change nothing the second time. Fixtures and migrations are versioned.
- **Hooks are deliberate.** Adding to `nxerp/hooks.py` needs its own tests and a docs line; `nxerp/tests/test_scaffold.py` pins the set so a new hook is never silent. Hooks only append in Frappe, so never rely on a hook to hide another app's data.
- **Whitelisted methods:** state-changing endpoints use `@frappe.whitelist(methods=["POST"])`; the permission check is in the method body (a whitelist decorator is not a check); no `allow_guest=True` without a review note naming why; accept only the parameters you need (no `**kwargs`, no mass assignment).
- **Translatable strings** use `_()` for anything a user reads. Do not build messages by string concatenation.
- **Frappe `www` pages:** `no_cache = True` for per-user pages; redirect by setting `frappe.local.flags.redirect_location` and raising `frappe.Redirect`, never by building a URL from raw input (use `routing.safe_target`).

## Error handling

- **Fail closed for authorisation, fail open never.** A resolver or gate error denies everyone except `Administrator` (who is never evaluated, so a bug cannot lock the superuser out) and is logged without saying why to the caller (`nxerp.enforcement.auth_hook`).
- **Refuse with Frappe's own exceptions** (`frappe.PermissionError`, `frappe.ValidationError`, `frappe.DoesNotExistError`) via `frappe.throw(_("..."), exc)`. Responses to a refusal carry no traceback and no list of apps or roles the user lacks.
- **No bare `except: pass`.** The one tolerated swallow is the denial logger, marked `# nosec B110` with the reason ("a logging failure must never turn a denial into an error"). If you must catch broadly, log with `exc_info=True` to a named logger and still end up closed.
- **Validate at the boundary, trust inside.** Untrusted input (query parameters, `redirect-to`, JSON arguments) is validated where it enters; do not re-validate in every helper, and do not skip validation because "the frontend does it".
- Tests and fixtures must **surface** exceptions: run them with `python -m`, not `bench execute`, which hides the real error ([testing.md](testing.md)).

## Comments and docstrings

- A comment explains **why** when the reason is not obvious from the code (a Frappe quirk, a security reason, an ADR). It does not restate the line below it.
- Module docstrings say what the module is for, what it deliberately does not do, and name the ADR or doc. Keep them current: a docstring that contradicts the code is a bug.
- No `TODO` without an owner or issue number. No commented-out code. No dates or "added for X" in comments; that is what git history is for.
- Do not mention people or customers. Fake data is `user@example.test`-style only.

## JavaScript, Vue and TypeScript

- **This repo has no Vue or TypeScript.** The only JavaScript here is the browser test suite under `e2e/` (`.mjs`, tabs, no build step) and two scripts under `tools/`.
- The Helpdesk SPA and the palette generator live in the **Helpdesk repo** and follow that repo's tooling: `.prettierrc.json`, `.eslintrc.js`, `commitlint.config.mjs`. Run its own checks there. Colours come from the generated palette tokens only (`yarn theme:audit` fails on a hard-coded colour); never edit the generated CSS under `nxerp/public/css/` by hand (`yarn theme:build` in the Helpdesk repo regenerates it).
- **Server-side first:** the frontend is never the security boundary. Hiding a button, a tile or a route is display; the server must refuse the request ([security-guidelines.md](security-guidelines.md)).

## Shell and YAML

- Shell scripts: `#!/usr/bin/env bash`, `set -euo pipefail` (or `-uo` for harnesses that must continue), LF line endings (`.gitattributes` forces them: CRLF broke `bootstrap.sh` once), tabs. Pre-commit runs `shellcheck` at `--severity=warning`.
- YAML and JSON use two spaces (`.editorconfig`).

## Commits and branches

- Conventional commits, imperative, one logical change each: `feat(access): resolve app grants for a user`, `fix(deploy): ...`, `docs(adr): ...`. Types: `feat`, `fix`, `docs`, `chore`, `ci`, `test`, `refactor`. Subject in the imperative, no trailing period.
- Branches are short-lived: `feat/<area>-<summary>`, `fix/<area>-<summary>`, `docs/<summary>`, `chore/<summary>`, `phase-N/<summary>`. Rebase on `main` before the PR. Never force-push shared history; no direct pushes to `main`.
- No secrets, `.env` files, production config, customer or personal data in any commit. `gitleaks` and `detect-private-key` run in pre-commit; they are a net, not permission.
- A change to a version pin, an access rule, a route or an architecture rule updates the matching ADR **in the same pull request**.

## Pull request expectations

Fill in the template (scope check, evidence, rollback). Evidence is output you actually saw, not "should work". Say which checks you ran locally and which only CI ran; a local run is not a CI result. Sensitive paths (`nxerp/`, `deploy/`, `.github/`, `docs/adr/`) need a code owner's review ([governance/](../governance/ownership.md)).
