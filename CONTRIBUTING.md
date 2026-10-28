# Contributing to NXERP

Read [CLAUDE.md](CLAUDE.md) first; it holds the non-negotiable rules.

## Branching

- `main` is protected: no direct pushes, no force-pushes. (Branch protection must be enabled by a repository admin; see docs/PROGRESS.md.)
- Work on short-lived branches off `main`, merged within days:
  `feat/<area>-<summary>`, `fix/<area>-<summary>`, `docs/<summary>`, `chore/<summary>`, `phase-N/<summary>` for planned phase work.
- Rebase on `main` before opening the PR. Do not rewrite history once a PR has reviews.

## Commits

Conventional style, imperative, one logical change each:

```
feat(access): resolve app grants for a user
fix(deploy): fail bootstrap when a pinned commit drifts
docs(adr): accept ADR-003
```

Types: `feat`, `fix`, `docs`, `chore`, `ci`, `test`, `refactor`. No secrets, no `.env`, no customer or personal data.

## Pull requests

- Fill in the PR template; paste evidence of what you ran and saw.
- Required reviews: at least one approval; a code owner for sensitive paths (`apps/nxerp_platform/`, `deploy/`, `.github/`, `docs/adr/`).
- Changes to version pins, access rules, routes or the architecture rules need the matching ADR updated in the same PR.
- CI must be green. CI results from a local run are not CI results: say which you ran.

## Local checks

```bash
pre-commit install            # ruff, shellcheck, gitleaks, file hygiene
pre-commit run --all-files
./deploy/dev/up.sh -d         # dev platform; see deploy/README.md
docker compose -p nxerp-dev exec bench bash -lc 'cd frappe-bench && bench --site nxerp.localhost run-tests --app nxerp'
```

## Adding a new app to NXERP

1. Decide ownership (CODEOWNERS entry) and write or update the ADR if it changes the architecture rules.
2. Add it to `deploy/apps.json` pinned to a commit. Do not vendor it.
3. Register it with the platform through the extension point (once ADR-005's registry exists in Phase 2); never import it from `nxerp` or from another app.
4. Add its roles to the access model, with server-side enforcement and a test that a user without the grant cannot reach it by URL or API.

## Releases and rollback

Releases are tagged from `main`. Rollback = redeploy the previous tag's `deploy/` pins (versions are pinned, so this is deterministic). A pipeline that actually deploys does not exist yet; see docs/PROGRESS.md.
