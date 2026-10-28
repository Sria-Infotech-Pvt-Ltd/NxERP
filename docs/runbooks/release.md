# Runbook: release

**When to use:** cutting a release candidate or a final release of NXERP. **Status:** the process, the image build and the release
workflow are written and statically checked; **no release has ever been made**: no tag exists, `release.yml` has never run, the image
has never been fully built (only `docker buildx build --check` passed), nothing has been pushed to a registry.

## Versioning

`vMAJOR.MINOR.PATCH` for releases, `vMAJOR.MINOR.PATCH-rc.N` for release candidates. The tag must equal `apps/nxerp_platform/nxerp/__init__.py`
`__version__` (without `v` and `-rc.N`); `release.yml` refuses otherwise. A release pins upstream exactly as `deploy/versions.env` and
`deploy/apps.json` say at that commit (ADR-002), so a tag is reproducible except for Python dependencies below the Frappe layer
(Frappe does not lock them: see `upstream-security-update.md`).

Image tags: `<version>-<12-char git sha>` (immutable record) and `<version>`; `deploy/docker/build.sh` uses the same format locally.

## Checklist

1. `main` is green: `ci-gate` passed on the commit you will tag (the release workflow checks this and refuses otherwise).
2. `docs/PROGRESS.md`/ADRs current; pins and ADR-002 agree (`python3 -I deploy/check_pins.py`).
3. Bump `__version__` in a PR, merge.
4. Preview the notes: `python3 -I tools/changelog.py --version 0.1.0 --to HEAD` (Conventional Commits since the previous stable tag;
   non-conforming commits show under "Unclassified"; fix the PR titles, not history).
5. Tag the **merge commit on `main`** and push the tag (needs write access; do not tag from a branch):
   ```bash
   git switch main && git pull --ff-only
   git tag -s v0.1.0-rc.1 -m "NXERP 0.1.0-rc.1"      # or an unsigned annotated tag: -a
   git push origin v0.1.0-rc.1
   ```
6. Watch **Release** (`.github/workflows/release.yml`): verify -> build/push image with provenance + SBOM -> GitHub release
   (pre-release for `-rc`). Check the image digest in the job summary.
7. `-rc` tags trigger **Deploy staging** (`deploy-staging.yml`). Do the manual acceptance on staging (login as each persona, launcher,
   a customer ticket), the restore drill and the rollback drill the first time.
8. Final tag `v0.1.0` on the same commit (the production workflow requires a successful staging deployment of that commit and a
   published, non-pre-release GitHub release), then **Deploy production** (`deploy.md`).
9. Record: version, image digest, date, who approved, link to the staging evidence.

## Building the image by hand

```bash
deploy/docker/build.sh --dry-run     # prints the exact docker command and tag, builds nothing
deploy/docker/build.sh               # builds and loads it locally; needs ~15+ GB free disk and network; tag <version>-<sha>
GIT_TOKEN=... deploy/docker/build.sh # when an app repository (the Helpdesk fork) is private: BuildKit secret, never in a layer
```

SBOM: `build.sh` writes `dist/sbom-<version>-<sha>.spdx.json` with `syft` or Docker's `docker sbom` plugin when one is installed. **Neither is
installed on the machine used so far, so no SBOM has been generated locally**; in CI the release workflow produces it with
`anchore/sbom-action` and attaches it to the GitHub release, and `docker buildx --push` attaches an SBOM and SLSA provenance to the image.

## What was validated (FACT, 2026-10-28)

- `docker buildx build --check -f deploy/docker/Dockerfile .`: "Check complete, no warnings found" (this resolves the pinned base image
  metadata; it does not run any step).
- `deploy/check_pins.py` (now also checks that the Dockerfile's default build args equal `versions.env`; a drifted copy was tested to fail).
- `deploy/docker/build.sh --dry-run` prints the expected command; `bash -n`/`shellcheck` clean on every script.
- `tools/changelog.py` ran against this repository's history and produced grouped notes.
- `actionlint` 1.7.12 (with shellcheck) reports no problem in any workflow.

**Not validated:** the build itself (`bench init`, app installs at the pinned commits, `bench build`, image size), the SBOM, the
registry push, the GitHub release, `deploy-*.yml`, the tag-protection ruleset.
