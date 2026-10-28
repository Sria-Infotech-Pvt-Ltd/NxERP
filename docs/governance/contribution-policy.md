# Contribution policy

Applies to everyone and every AI assistant changing this repository. It extends [CONTRIBUTING.md](../../CONTRIBUTING.md) and
[CLAUDE.md](../../CLAUDE.md); where they disagree, CLAUDE.md wins. Enforcement points are named, so you can tell what a machine
checks and what a reviewer must.

## Branches

- `main` is protected ([branch-protection.md](branch-protection.md)); nobody pushes to it.
- Short-lived branches off `main`, merged within days: `feat/<area>-<summary>`, `fix/<area>-<summary>`, `docs/<summary>`,
  `chore/<summary>`, `phase-N/<summary>`. Delete after merge (automatic once the repo setting is on).
- Rebase on `main` before opening the PR. Do not rewrite history once a PR has reviews. Never force-push a shared branch.

## Commits and PR titles: Conventional Commits

```
type(scope): imperative summary          feat(access): resolve app grants for a user
type(scope)!: summary                    breaking change; explain it in the body (BREAKING CHANGE: ...)
```

- Types: `feat fix docs chore ci test refactor perf build style revert`. Scope is the area (`access`, `login`, `deploy`, `ci`, `adr`...).
- Subject up to 100 characters, no trailing period. The PR title is what a squash merge keeps, so it is the one that matters.
- **Machine check:** `tools/check_commits.py` (job `lint`) validates the PR title strictly and every commit's format. Run it locally:
  `python3 -I tools/check_commits.py --range origin/main..HEAD --max-length 150` or `... --title "feat(x): y"`.
  FACT (run 2026-10-28 on the 22 local commits): all match the format; nine subjects are 103-128 characters, which is why commits get
  a 150 limit and only the PR title is held to 100. History is not rewritten for this.
- Release notes are generated from these messages (`tools/changelog.py`), so a vague message is a vague changelog.

## Pull requests

- Fill in `.github/PULL_REQUEST_TEMPLATE.md`. **Evidence** means output you saw, labelled FACT / ASSUMPTION / DECISION. Say which
  checks ran locally and which only in CI. A workflow file existing is not a working pipeline.
- Keep them small and single-purpose. Docs-only and code PRs may be combined only when the docs describe that code.
- **Required to merge:** `ci-gate` green, up to date with `main`, conversations resolved, code-owner review for sensitive paths,
  1 approval (2 once the team can support it). Author never approves their own PR; an AI assistant's PR needs a human approval.
- Changes that need an ADR in the same PR: version pins (`deploy/versions.env`, `deploy/apps.json` -> ADR-002), access rules
  (ADR-003), routes (ADR-004), architecture rules (ADR-005), dev/deploy topology (ADR-006).
- Sensitive paths (see `CODEOWNERS`): `nxerp/{enforcement,access,guard,routing}.py`, `nxerp/www/login.*`, `nxerp/patches/`, `deploy/`,
  `.github/`, `docs/governance/`, `e2e/`. Security owners review them. Reviewers check the server-side enforcement, not the UI.

## Review rules

- Reviewers read the diff and the evidence; they run it when the change touches access, routing, patches, migrations or deploy.
- Review for: server-side enforcement (a hidden icon is not security), no app importing another app, idempotent patches listed in
  `patches.txt`, secrets/PII absent, tests that fail without the change, rollback path stated.
- "LGTM" without having read it is not a review. Disagreement goes to the area owner (ownership.md), then to the architecture owner.
- Self-merge is allowed only after the required approvals; nobody bypasses protection (admins included).

## Secrets, data and AI assistants

- Never commit secrets, `.env` files, production config, customer or personal data. Use `user@example.test`-style fake data.
  Machine checks: gitleaks (`.gitleaks.toml`, job `secret-scan`), pre-commit `detect-private-key`, `.gitignore`.
- An AI assistant may draft code and docs under these same rules; it never pushes, tags, merges or changes protection settings on its
  own, and it states what it did not run.

## Releases

Tag `vX.Y.Z` from `main` after `ci-gate` is green on that commit; `-rc.N` tags are release candidates (staging). The tag must equal
`nxerp/__init__.py` `__version__`. Process: [docs/runbooks/release.md](../runbooks/release.md).
