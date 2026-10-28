# Branch protection and repository settings

**Status: ready, not executed.** Nothing here has been applied to GitHub. The account that prepared it has read-only access to
`Sria-Infotech-Pvt-Ltd/NxERP`; applying it needs a repository **admin**. The script was exercised only as a dry run (it prints the
commands and validates the JSON bodies; it sent nothing).

## What `main` must enforce

| Setting | Value | Why |
| --- | --- | --- |
| Pull request required, no direct pushes | on | CLAUDE.md: no direct pushes to `main` |
| Required status check | **`ci-gate`** (the single aggregate job of `.github/workflows/ci.yml`), branch must be up to date (`strict`) | one stable name; the individual jobs can change without touching the protection |
| Required approving reviews | **1** now; **2** once there are at least three reviewers | a second pair of eyes for access/security code; 1 avoids blocking a small team |
| Require review from Code Owners | on | sensitive paths in `CODEOWNERS` need their owners |
| Dismiss stale approvals on new commits; approval of the most recent push | on | a reviewer approves what is merged |
| Require conversation resolution | on | no merging over open review threads |
| Require linear history | on | squash-only (below) keeps `main` a straight line |
| Force pushes, deletions | blocked | never rewrite shared history |
| Include administrators (`enforce_admins`) | on | admins follow the same rules; break-glass is a documented, audited exception (see below) |
| Merge methods | **squash only**; merge commits and rebase merges off | the PR title (checked as a Conventional Commit) becomes the commit |
| Auto-delete head branches | on | short-lived branches |

Optional (flags in the script): secret scanning + push protection, Dependabot alerts/security updates, immutable `v*` release tags
(a tag ruleset), and the `staging` / `production` GitHub Environments (production with required reviewers).

## Caveats (read before relying on this)

- **FACT** The CODEOWNERS teams (`nxerp-platform`, `nxerp-security`, `nxerp-devops`, `nxerp-architecture`, `nxerp-maintainers`) are
  placeholders and are not known to exist. Until they exist, "Require review from Code Owners" blocks nothing useful and may block
  everything. Create the teams (or edit `CODEOWNERS`) **before** turning that setting on.
- **ASSUMPTION (GitHub's documented behaviour, not verified here)** a CODEOWNERS line lists *alternatives*: one approval from any
  listed owner satisfies it. To require "security **and** platform" you need two approvals (`--reviews 2`) and sensitive paths owned
  by the security team.
- `ci-gate` can only be chosen in the UI after it has reported once. Open a PR so CI runs, read the result, fix what fails, then
  apply. Requiring a check that never reports makes every PR unmergeable.
- Private repositories: some features (code scanning/CodeQL, secret scanning, rulesets on some plans) depend on the organisation's
  GitHub plan. The script prints the API's error if a call is refused; it never claims success it did not get.
- **Break-glass:** if `main` must be changed while CI or reviewers are unavailable, an admin temporarily relaxes one setting, makes
  the change, restores it, and records it in the incident log (`docs/runbooks/incident-response.md`). Never leave protection off.

## Apply with the script

```bash
# 1. read what it will do (default: dry run, sends nothing)
docs/governance/apply-branch-protection.sh --reviews 1

# 2. as a repository admin, logged in with `gh auth login`
docs/governance/apply-branch-protection.sh --apply --reviews 1 --with-security --with-tags

# production Environment with required reviewers (logins are examples)
PRODUCTION_REVIEWERS="reviewer-one,reviewer-two" docs/governance/apply-branch-protection.sh --apply --with-environments

# 3. verify (the script prints this too)
gh api repos/Sria-Infotech-Pvt-Ltd/NxERP/branches/main/protection \
  --jq '{checks: .required_status_checks.checks, reviews: .required_pull_request_reviews.required_approving_review_count, admins: .enforce_admins.enabled, linear: .required_linear_history.enabled}'
```

The script is idempotent: `PUT .../protection` and `PATCH repos/...` replace the settings with the stated values.

## The same thing through the web UI (exact click paths)

Menus move around on GitHub; the names below are the ones used at the time of writing and may differ slightly.

**Branch protection (classic rule)** - repository **Settings > Branches > Add branch ruleset / Add classic branch protection rule**
(branch name pattern `main`):

1. Tick **Require a pull request before merging**: set **Required approvals** to 1 (or 2); tick **Dismiss stale pull request approvals
   when new commits are pushed**, **Require review from Code Owners**, **Require approval of the most recent reviewable push**.
2. Tick **Require status checks to pass before merging** and **Require branches to be up to date before merging**; search for and add
   **`ci-gate`** (it appears only after it has run once).
3. Tick **Require conversation resolution before merging**.
4. Tick **Require linear history**.
5. Leave **Allow force pushes** and **Allow deletions** unticked.
6. Tick **Do not allow bypassing the above settings** (this is "include administrators").
7. **Create / Save changes.**

**Merge button and branch clean-up** - **Settings > General > Pull Requests**: tick **Allow squash merging** (default commit message:
*Pull request title and description*), untick **Allow merge commits** and **Allow rebase merging**, tick **Automatically delete head
branches**.

**Security features** - **Settings > Code security**: enable **Dependency graph**, **Dependabot alerts**, **Dependabot security
updates**, **Secret scanning** and **Push protection**; **Code scanning** (CodeQL) needs GitHub Advanced Security on private repos.

**Release tags** - **Settings > Rules > Rulesets > New tag ruleset**: name *release tags are immutable*, enforcement *Active*, target
pattern `v*`, tick **Restrict deletions**, **Restrict updates**, **Block force pushes**.

**Environments** - **Settings > Environments > New environment**: `staging`; `production` with **Required reviewers** (at least two
people or a team), **Prevent self-review**, and **Deployment branches and tags** limited to `main`. Add the secrets and variables
listed in `deploy/environments/README.md`.

**Teams for CODEOWNERS** - organisation **Teams > New team**: create `nxerp-platform`, `nxerp-security`, `nxerp-devops`,
`nxerp-architecture`, `nxerp-maintainers`; give each **Write** access to the repository (Settings > Collaborators and teams).

## Checking that it works (once applied)

1. Open a throwaway PR touching `apps/nxerp_platform/nxerp/access.py`: it must show *Review required from code owners* and block merging until `ci-gate` is
   green.
2. Try `git push origin main` directly: must be rejected. Try a merge commit: the button must not offer it.
3. Record the result in the PR/issue. Do not write "branch protection works" anywhere until step 1 and 2 were seen.
