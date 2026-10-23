# Contributing to NXERP

Thank you for contributing. Please read this document before opening a pull request.

---

## Code of Conduct

All contributors must follow our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Development Environment

Follow the [Quick Start](README.md#quick-start-development) in the README to set up your local bench.

Required tools:
- Python 3.14+
- Node 24 LTS
- Yarn 1.x
- MariaDB 10.6+
- Redis 6+
- Git 2.35+

---

## Daily Workflow (50+ Developer Team)

### 1. Start from `main`

Always branch from the latest `main`:

```bash
git checkout main
git pull origin main
git checkout -b feature/NX-1234-add-ticket-escalation
```

### 2. Branch Naming Convention

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feature/<ticket-id>-<slug>` | `feature/NX-1234-add-ticket-escalation` |
| Bug fix | `fix/<ticket-id>-<slug>` | `fix/NX-5678-sla-timer-reset` |
| Hotfix | `hotfix/<ticket-id>-<slug>` | `hotfix/NX-9999-login-redirect` |
| Release | `release/<version>` | `release/2026.10.1` |
| Chore/Docs | `chore/<slug>` | `chore/update-contributing-guide` |

**Avoid:**
- Long-lived personal branches (`darla-dev`, `my-work`)
- Branches without ticket IDs for non-trivial changes
- Branches starting with `main`, `release`, or `hotfix` unless following the hotfix workflow

### 3. Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer: refs NX-1234]
```

Valid types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`, `revert`

Examples:
```
feat(ticket): add escalation rule for VIP customers

fix(sla): timer resets when ticket is reassigned

docs(branching): update hotfix workflow steps

refs NX-1234
```

- Present tense, imperative mood
- 72 characters max for the subject line
- Reference the ticket in the footer when applicable

### 4. Writing Code

**Python:**
- Follow PEP 8 (enforced by Ruff/flake8)
- Use type annotations on all API methods (required by Frappe)
- Never use `frappe.db.sql()` with string formatting — use parameterized queries
- Never log sensitive data (passwords, tokens, PII)

**JavaScript/TypeScript/Vue:**
- Follow the project's ESLint and Prettier configuration
- Use design tokens from the theme system, never hardcode colours
- Frappe API calls via `frappe.call()` or the Frappe UI composables

**General:**
- No hardcoded credentials, URLs, or environment assumptions
- No `print()` or `console.log()` in production paths
- All new API methods must have `@frappe.whitelist()` and permission checks
- New DocTypes require migration files and schema documentation

### 5. Tests

Run existing tests before opening a PR:

```bash
# Server tests
cd ~/nxerp-bench
bench --site nxerp.localhost run-tests --app helpdesk

# Specific test file
bench --site nxerp.localhost run-tests --module helpdesk.tests.api.test_theme

# Frontend lint
cd apps/helpdesk/desk && yarn lint

# Theme token check
cd apps/helpdesk/desk && yarn theme:check
```

Write tests for:
- All new API methods
- Bug fixes (regression test)
- Custom DocType business logic
- Authentication or permission changes

### 6. Open a Pull Request

Push your branch and open a PR against `main`:

```bash
git push origin feature/NX-1234-add-ticket-escalation
```

Then open a PR via GitHub. The PR template will guide you.

**PR Requirements:**
- Clear title following Conventional Commits format
- Description linking to the ticket (`Closes NX-1234`)
- Self-review checklist completed
- All CI checks passing
- At least **1 reviewer approval** (2 for auth/migrations/infrastructure changes)
- No unresolved review conversations

### 7. Review and Merge

- Respond to all reviewer comments
- Request re-review after addressing feedback
- Squash-merge or rebase-merge only — no merge commits on `main`
- Delete your branch after merge

---

## Hotfix Workflow

For urgent production issues:

```bash
# Branch from main
git checkout main && git pull
git checkout -b hotfix/NX-9999-login-redirect

# Fix, test, commit
git commit -m "fix(auth): correct post-login redirect when helpdesk is installed last"

# Open a PR against main — mark it [HOTFIX]
# After merge, tag main with a patch version
git tag v2026.10.2
git push origin v2026.10.2
```

---

## Database Migrations

- All schema changes go through Frappe DocType or patch files
- Never alter a table directly with raw SQL in production
- Patches go in `helpdesk/patches/` and must be registered in `patches.txt`
- Patches must be idempotent (safe to re-run)
- All patches require a senior review (see CODEOWNERS)
- Test patches on a copy of the production database before merging

---

## Authentication and Security Changes

Any change that affects:
- Login flow, session creation, or logout
- Role or permission logic
- Allowed API endpoints in `auth.py`
- CSRF or CORS configuration
- File upload handling

…requires approval from the **security** code owners (see CODEOWNERS).

---

## Dependency Changes

- Pin all new Python dependencies in `pyproject.toml` with `~=` or `==` constraints
- Run `pip-audit` and verify no high/critical CVEs before adding
- Update `yarn.lock` by running `yarn install` in the `desk/` directory
- Never commit `node_modules/`

---

## Asset Build

The Helpdesk frontend is built with Vite. For production:

```bash
cd apps/helpdesk/desk
yarn install --frozen-lockfile
yarn build

bench --site nxerp.localhost build --app helpdesk
```

Do not commit build artifacts (`helpdesk/public/desk/`). They are generated during deployment.

---

## Getting Help

- Internal Slack: `#nxerp-dev`
- GitHub Discussions: for architecture questions
- GitHub Issues: for confirmed bugs and feature requests

New to the codebase? Read [docs/onboarding.md](docs/onboarding.md).
