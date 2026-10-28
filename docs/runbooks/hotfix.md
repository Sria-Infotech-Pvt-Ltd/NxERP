# Runbook: hotfix

**When to use:** a defect in production that cannot wait for the next planned release and that rolling back would not fix (or the
rollback would lose too much). Security fixes in NXERP code use this path too. Upstream security fixes: `upstream-security-update.md`.
**Status:** the process is written; no hotfix has ever been made, and the release workflow has never run.

## Rules

- Same gates as any change: PR to `main`, `ci-gate` green, review (code owners for sensitive paths). **No direct push, no bypass, even
  for a hotfix.** A hotfix is a small PR with a fast review, not an exception to review.
- Smallest possible change. One defect per hotfix. No unrelated cleanup, no pin bumps (unless the pin bump *is* the fix).
- Release as a new patch version, never by moving a tag.

## Steps

1. **Reproduce and write the failing test first** (in `nxerp/tests/` or the e2e suite). Say in the PR what you ran and saw (FACT).
2. Branch from `main`: `git switch -c fix/<area>-<summary> origin/main`. (Production runs a tag of `main`; if `main` already contains
   unreleased work you do not want to ship, say so and talk to the release manager: the supported answer today is to ship `main`
   after reverting the unwanted commit in the same PR. A long-lived `release/x.y` branch does not exist.)
3. Fix, run the relevant tests locally (`docs/runbooks/deploy.md` has the commands), open the PR with title `fix(scope): ...`.
4. Review and merge (squash). Expedite by pinging the area owner (ownership.md); do not ask anyone to skip CI.
5. Bump `nxerp/__init__.py` `__version__` (patch) in the same PR or a follow-up PR, merge.
6. Tag from `main` after `ci-gate` is green on that commit: `vX.Y.Z+1-rc.1`; staging deploys; verify the defect is fixed there with the
   steps from the report; then tag `vX.Y.Z+1` and run the production deploy (`release.md`, `deploy.md`).
7. Rollback plan stated before you deploy (`rollback.md`). Take a backup first (automatic in `deploy.sh`).
8. Close the loop: link the hotfix PR from the incident/issue, add the regression test to the suite (it already is, from step 1).

## Emergency (production down, no time for a release candidate)

Skipping the `-rc` stage is the only shortcut allowed: tag the final `vX.Y.Z+1` directly. The deploy workflow still requires a
successful staging deployment of that commit, so for a true emergency the production environment reviewers approve running
`scripts/deploy.sh --tag X.Y.Z+1` by hand on the host, and the reason is written in the incident log. Never edit code on the host.

## What was tested

Nothing of this flow has executed (no tag, no remote CI). `tools/check_commits.py` accepts `fix(scope): ...` titles (run locally).
