# Git Branching Strategy

## Overview

NXERP uses a **trunk-based, pull-request workflow** with `main` as the single source of truth for production code.

For a team of 50+ developers:
- Short-lived feature branches (target: < 3 days)
- All changes merge to `main` via pull request
- `main` is always deployable
- Releases are tagged commits on `main`

---

## Branch Categories

| Branch Pattern | Purpose | Created From | Merges To | Lifetime |
|---------------|---------|-------------|----------|---------|
| `main` | Production-ready code | — | — | Permanent, protected |
| `feature/<id>-<slug>` | New functionality | `main` | `main` | Short (< 5 days) |
| `fix/<id>-<slug>` | Bug fixes | `main` | `main` | Short (< 3 days) |
| `hotfix/<id>-<slug>` | Urgent production fixes | `main` | `main` | Hours |
| `release/<version>` | Release stabilization | `main` | `main` | Days (when used) |
| `chore/<slug>` | Maintenance, tooling, docs | `main` | `main` | Short |

### Branch Naming Rules

- Use your ticket/issue ID as the prefix: `feature/NX-1234-add-escalation`
- Use lowercase with hyphens; no underscores, no spaces
- Keep the slug short but meaningful (3–5 words)
- Do not use personal names as branch prefixes (`darla-dev`)

---

## Protected Branch Rules for `main`

Configure these in **GitHub → Settings → Branches → Branch protection rules** for `main`:

| Rule | Setting |
|------|---------|
| Require a pull request before merging | ✅ Enabled |
| Require approvals | 1 (2 for auth/migrations) |
| Dismiss stale reviews on new push | ✅ Enabled |
| Require review from Code Owners | ✅ Enabled |
| Require status checks to pass | ✅ CI: `python-lint`, `frontend-lint`, `server-tests` |
| Require branches up to date before merging | ✅ Enabled |
| Do not allow bypassing the above settings | ✅ Enabled |
| Restrict direct pushes to `main` | ✅ No direct pushes |
| Restrict force pushes | ✅ No force pushes |
| Restrict deletions | ✅ Cannot delete `main` |
| Require conversation resolution before merging | ✅ Enabled |
| Require signed commits | Optional (enable when GPG key distribution is complete) |

---

## Daily Developer Workflow

### Starting a Feature

```bash
# Always start from the latest main
git checkout main
git pull origin main

# Create your branch
git checkout -b feature/NX-1234-add-ticket-escalation

# Work on your change...
```

### Committing

```bash
# Stage only related changes
git add apps/helpdesk/helpdesk/api/ticket.py
git add apps/helpdesk/helpdesk/tests/api/test_ticket.py

# Commit with Conventional Commits format
git commit -m "feat(ticket): add escalation rule for VIP customers

Closes NX-1234"
```

### Keeping Your Branch Updated

Rebase onto `main` regularly to avoid drift:

```bash
git fetch origin
git rebase origin/main
```

If there are conflicts, resolve them carefully — do not discard the intent of either change.

### Pushing and Opening a PR

```bash
git push origin feature/NX-1234-add-ticket-escalation
```

Then open a Pull Request on GitHub:
- Target branch: `main`
- Fill in the PR template completely
- Link your ticket: `Closes NX-1234`
- Add relevant reviewers (CODEOWNERS will be added automatically for protected paths)

### During Review

- Respond to all comments
- Push additional commits to the same branch (do not force-push during review)
- Request re-review after addressing feedback
- Do not merge your own PR

### Merging

- Use **Squash and merge** for feature/fix branches (keeps `main` history clean)
- Use **Rebase and merge** for chore/docs with clean atomic commits
- **Never** use "Create a merge commit" on `main`
- Delete your branch after merging (GitHub can do this automatically)

---

## Hotfix Workflow

Use when a confirmed production bug requires an immediate fix.

```bash
# 1. Branch from main (which is production)
git checkout main
git pull origin main
git checkout -b hotfix/NX-9999-login-redirect-loop

# 2. Fix the bug
# ... make changes ...

# 3. Commit
git commit -m "fix(auth): correct post-login redirect when nxerp is last installed app

Refs NX-9999"

# 4. Open a PR against main — mark the title with [HOTFIX]
# Get emergency approval from a senior engineer
git push origin hotfix/NX-9999-login-redirect-loop

# 5. After merge, create a patch version tag
git checkout main
git pull origin main
git tag v2026.10.2
git push origin v2026.10.2
```

Do not bypass CI checks even for hotfixes. If a check fails unexpectedly, fix the check or get an exception approved.

---

## Release Workflow

NXERP uses **calendar versioning**: `vYYYY.MM.PATCH`

```bash
# Example: first release in October 2026
git checkout main
git pull origin main
git tag v2026.10.1
git push origin v2026.10.1
```

The `release.yml` workflow creates a GitHub Release automatically.

### When to use a `release/` branch

Only create a stabilization branch when:
- Multiple features are being held back while only one set is released
- A formal UAT sign-off process requires a frozen codebase

In all other cases, tag directly on `main`.

---

## Commit Message Reference

```
<type>(<scope>): <description>

[optional body — wrap at 72 chars]

[optional footer]
  Closes NX-1234
  Breaking change: <describe impact>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`, `revert`

**Scopes (examples):** `ticket`, `sla`, `auth`, `branding`, `helpdesk`, `erpnext`, `ci`, `deps`

**Rules:**
- Subject line ≤ 72 characters, no period at end
- Imperative mood: "add", "fix", "update" not "added", "fixed"
- Reference tickets in footer, not subject line

---

## Anti-Patterns to Avoid

| Anti-Pattern | Problem | Alternative |
|-------------|---------|------------|
| Long-lived personal branches | Accumulate conflicts, invisible to team | Short branches, PR within 3 days |
| Committing directly to `main` | Bypasses review and CI | Always use a PR |
| `WIP` commits in PR | Pollutes history | Squash locally before pushing |
| Force-pushing reviewed PRs | Discards reviewer context | Add new commits |
| Merge commits on `main` | Clutters history | Squash or rebase merge |
| "Fix CI" commit loop | Wastes CI resources | Test locally before pushing |
