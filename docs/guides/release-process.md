# Release process (concept)

How a change becomes a release, conceptually. The step-by-step operator procedures are the runbooks, written separately:
[`../runbooks/release.md`](../runbooks/release.md) (cutting a release) and [`../runbooks/deploy.md`](../runbooks/deploy.md) (deploying and rolling back).
Read this page for the model and the rules; read the runbooks to do the work.

**Status, stated plainly (FACT as of 2026-10-28):** no release has ever been cut. The repository has no tags and no changelog, `nxerp/__init__.py` says
`0.0.1`, nothing has been pushed (the remote has only `main`'s initial commit), CI has never run on GitHub, and nothing has been deployed anywhere. Everything
below marked DECISION is a proposal for the owner to ratify; nothing marked so is already in force.

## What a "release" is

NXERP is several repositories pinned together. A **release is a tag on this repository (`main`)** whose `deploy/versions.env` and `deploy/apps.json` fix every component:
Frappe, ERPNext, payments, telephony, the Helpdesk fork commit, and `nxerp` itself (ADR-001, ADR-002). Because every pin is an exact commit or digest, checking out a tag and building
reproduces the same product. The Helpdesk fork is released by pinning a commit that exists on a remote, so **push the fork commit before the NXERP release that pins it**.

## Versioning (DECISION, proposed)

- **Semantic versioning for the platform release:** `vMAJOR.MINOR.PATCH`.
  - MAJOR: a change that needs operator action or breaks a contract (a Frappe major upgrade, a changed grant model, a removed route).
  - MINOR: new capability or a registered app, backward compatible; a pin bump of a minor upstream version.
  - PATCH: fixes and upstream security patches with no behaviour change.
- The `nxerp` app version in `nxerp/__init__.py` is bumped to match the release in the release PR. Upstream versions are recorded in the release notes, not invented: they come from the pins.
- A change to a version pin, an access rule, a route or an architecture rule carries its ADR (or amendment) in the same PR, so the release notes can cite it.
- A Frappe major upgrade (for example 17) is a new ADR and never a patch release (ADR-002).

## The path of a change

1. **Branch and PR.** Short-lived branch off `main`; conventional commits; a PR with evidence; required reviews (a code owner on sensitive paths); CI green. No direct pushes to `main`. Details: [CONTRIBUTING.md](../../CONTRIBUTING.md), [coding-standards.md](coding-standards.md).
2. **Merge to `main`.** `main` is always releasable: it must pass the static checks and the test layers ([testing.md](testing.md)).
3. **Release candidate.** When a set of changes is to ship, cut `vX.Y.Z-rc.N` from `main`. The RC is built from empty volumes and put through the full test layers (python suites, persona matrix, HTTP tests, the Helpdesk regression suite, the browser suite on a fresh site) and the acceptance checklist. Findings are fixed on `main` and a new RC is cut. An RC is never edited in place.
4. **Staging verification.** The RC is deployed to a staging-like environment that mirrors production's shape ([deploy runbook](../runbooks/deploy.md)). Verify there, not on a developer machine: sign-in, landing for every persona, a denied URL and API, migration on a copy of realistic (anonymised) data, backup and restore, rollback.
5. **Release.** The same commit as the last good RC is tagged `vX.Y.Z` (no new code between the RC and the release), the changelog entry is finalised, and the release is deployed by the runbook with a pre-deploy backup.
6. **After release.** Watch the denial log and error logs for the agreed period; record the outcome; open follow-ups for anything deferred.

## Changelog (DECISION, proposed)

A `CHANGELOG.md` at the repository root, one section per release, newest first, written for operators and owners: *Added / Changed / Fixed / Security / Upgrade notes*, each line linking its PR and, where it applies, its ADR.
It also lists the exact pins (copy of `deploy/versions.env` and `deploy/apps.json`) and anything **not verified** in that release. It does not exist yet; the first release PR creates it.

## Rollback

- The pins make **code** rollback deterministic: redeploy the previous tag's `deploy/` pins (CONTRIBUTING.md).
- **Data** is different. Migrations (patches, DocType changes) move forward and are not automatically reversible. ASSUMPTION: rolling back code across a migration needs the pre-deploy backup restored. So every deploy takes a verified backup first, and patches are idempotent (a patch run twice changes nothing).
- The platform has an **operational kill-switch for the login page only** (`nxerp_stock_login`, [`../runbooks/login-recovery.md`](../runbooks/login-recovery.md)). It is not a rollback of the access layer; never "uninstall `nxerp`" to recover, because that removes the access roles and leaves apps reachable by any Frappe role.

## Hotfixes and upstream security releases

- **Hotfix:** branch from the release tag, fix, PR to `main` first (so the fix is never lost), cherry-pick to a `release/X.Y` line only if one exists, cut `vX.Y.(Z+1)-rc.1`, verify, release. A hotfix still carries its test.
- **Upstream security fix** (Frappe, ERPNext, Helpdesk): bump the pin, update ADR-002, rebuild from scratch, run all layers, release as a PATCH or MINOR. ADR-002 sets the review rhythm (weekly check, monthly batches); the owner sets the maximum time to apply a critical fix.

## Release checklist (copy into the release PR)

- [ ] `main` is green: static checks, all test layers, Helpdesk regression, browser suite; each result linked, and anything not run is listed as not run.
- [ ] `python -I deploy/check_pins.py` and `python -I tools/check_architecture.py --app-path helpdesk=<path>` pass.
- [ ] All pins are exact commits that exist on a remote; the Helpdesk fork commit is pushed.
- [ ] ADRs and docs match the code ([`../README.md`](../README.md)); `docs/PROGRESS.md` is current.
- [ ] `nxerp/__init__.py` version bumped; `CHANGELOG.md` section written, including upgrade notes and what is not verified.
- [ ] A fresh build from empty volumes works and the RC passed staging verification.
- [ ] A backup and a restore were rehearsed; the previous tag is known and its pins redeployable.
- [ ] Owners and approvers named in [`../governance/ownership.md`](../governance/ownership.md) have signed off; open items for the owner ([`../governance/owner-action-list.md`](../governance/owner-action-list.md)) that block the release are resolved.
- [ ] Tag created by an authorised person from the reviewed commit; the tag is verified on the remote (`git ls-remote --tags`), not assumed.
