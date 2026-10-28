# Runbook: upstream security update (Frappe, ERPNext, Helpdesk, Python/JS dependencies)

**When to use:** `upstream-watch` opens/updates an issue, GitHub Dependabot or an advisory email arrives, or the weekly review (ADR-002)
finds a newer upstream release. **Status:** `tools/upstream_watch.py` was run locally and produced a real report (below); the scheduled
workflow has never run; no upstream update has been applied through this process yet.

## 0. Triage (same day)

1. Read the advisory/release notes. Is the pinned version affected? `upstream-watch` already compares the advisory's `patched_versions`
   with the pin (`python3 -I tools/upstream_watch.py --days 30`). Do not guess: "pin vs fix UNKNOWN" means read it yourself.
2. Is the vulnerable code reachable in NXERP (customer portal, login, API, guest routes)? Security lead decides severity; record it.
3. SLA (ASSUMPTION from ADR-002, owner to confirm): critical within 7 days, others in the monthly batch.

## 1. Change the pin (one PR)

```bash
# Frappe: deploy/versions.env  FRAPPE_REF and FRAPPE_COMMIT (40-char sha of the tag)
git ls-remote https://github.com/frappe/frappe.git "refs/tags/v16.54.0" "refs/tags/v16.54.0^{}"   # the ^{} line is the commit for annotated tags
# ERPNext / payments / telephony / Helpdesk fork: deploy/apps.json  "branch" (tag or branch) and "commit"
```

Then, in the same PR: update the matrix in `docs/adr/ADR-002-version-matrix.md`; `python3 -I deploy/check_pins.py`; read the upstream
diff/release notes for DocType permission, auth and routing changes (these can interact with the access layer).
**Helpdesk** is a fork: rebase the company commits onto the new upstream release in the fork repo first, push, then pin the new commit.

## 2. Prove it

- CI (`ci-gate`) runs the nxerp tests, the persona matrix, the ERPNext smoke, Helpdesk's suite and the browser suite on a stack built
  from the new pins (a pin change invalidates the stack cache, so the first run builds from scratch).
- `fresh-install-migrate` proves install from nothing; `docker-build` proves the image builds.
- Rehearse the migration on a restored production backup on the staging-like stack (`migration-planning.md`).

## 3. Ship

Merge, release candidate, staging, production (`release.md`, `deploy.md`). A security update is a normal release with a short window;
use `hotfix.md` only if NXERP's own code is the fix.

## Python and JavaScript dependencies

`dependency-audit` runs `pip-audit` on Frappe's resolved dependency set and `npm audit`/`yarn audit` on the browser tests and the
Helpdesk SPA. FACT (local run 2026-10-28): Frappe v16.53.0 resolves to packages with 59 known advisories in 5 packages (pillow, pypdf,
gitpython, filelock, pdfkit), because **Frappe does not lock its Python dependencies**: a fresh `bench init` installs the newest versions
that satisfy Frappe's ranges, so image builds are not reproducible below the Frappe layer. The fix options (owner decision): a pip
constraints file for the image build generated from an audited resolution; waiting for Frappe to bump its ranges; or accepting specific
advisories with a dated reason. Until decided the audit job reports without failing (`AUDIT_ENFORCE` repository variable).

## What was run (FACT)

`python3 -I tools/upstream_watch.py --days 30` on 2026-10-28 reported: Frappe pinned `v16.53.0`, upstream latest `v16.54.0` (newer release
available); ERPNext `v16.52.1` current; Helpdesk upstream base `v1.31.0` current; payments/telephony branches unmoved; five published
`frappe/frappe` advisories in the window, all with `patched_versions` at or below `16.35.0`, i.e. fixed at or below the pinned
`v16.53.0`. (That is GitHub's metadata, not an independent code check.) Whether to take `v16.54.0` has not been decided; nothing was changed.
