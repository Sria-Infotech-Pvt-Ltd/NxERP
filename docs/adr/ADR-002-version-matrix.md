# ADR-002: Version matrix and upstream update policy

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

The platform must be reproducible and take upstream security fixes deliberately. Versions below were read from the pinned sources, not from memory.

## Evidence

| Component | Version / commit | Evidence (FACT) |
| --- | --- | --- |
| Frappe | `v16.53.0` @ `e8d41dd0061a32ee781caefe5d0b0d2bb7c15362` | `git ls-remote --tags frappe/frappe` (latest v16 tag); `frappe/frappe/__init__.py:58` |
| Python | 3.14 | `frappe/pyproject.toml:7` `requires-python = ">=3.14,<3.15"`; `frappe/bench` image reports 3.14.8 |
| Node | 24 | `frappe/package.json` `engines.node ">=24"`; image reports v24.21.0; `frappe_docker` `docker-bake.hcl` `NODE_VERSION=24` |
| ERPNext | `v16.52.1` @ `ade850bbd6a7412e9994a9637d2c5c713771632a` | `erpnext/pyproject.toml` `frappe >=16.50.0,<17.0.0`, `requires-python >=3.14` |
| Helpdesk (interim) | company fork `feature/nxerp-login-page` @ `1c6981cc515af58b8cdfbad7a7525b33236e399b` | `pyproject.toml`: `frappe >=16.0.0-dev,<18.0.0`, `requires-python >=3.14`; it is a snapshot of upstream **`develop`**, not a release |
| Helpdesk (target) | upstream `v1.31.0` + the 10 company commits | `v1.31.0` `pyproject.toml`: `frappe >=15.123.1,<17.0.0`, `requires-python >=3.10`; spike: all 10 commits cherry-pick onto `v1.31.0` with **0 conflicts** (scratch clone, 64 files changed, +831/-64); both use `frappe-ui 1.0.0-rc.1` |
| payments | `version-16` @ `cca07d9f9392e2ea0e521c5975151db9e4b6c321` | no release tags; ERPNext doctypes (`Payment Request`, `Payment Gateway Account`, `Subscription Plan`) link to `Payment Gateway`, which only the `payments` app defines; `erpnext/hooks.py` does not declare it (a first bootstrap without it left the site missing that DocType and crashed Helpdesk's test generator); `bench get-app` skips dependencies unless `--resolve-deps` |
| telephony | `develop` @ `9447577500a25d242088398157b72c654fa34b20` | no release tags exist (`git ls-remote --tags`); `frappe >=14.101.0,<=17.0.0-dev` |
| MariaDB | 11.8 | `frappe_docker v4.1.1` `overrides/compose.mariadb.yaml`; `frappe/.github/workflows/_base-*.yml` use `mariadb:11.8` |
| Redis | 8.6 (`redis:8.6-alpine`) | `frappe_docker v4.1.1` `overrides/compose.redis.yaml` |
| bench CLI | 5.31.0 inside `frappe/bench@sha256:cb24e8a7...` | `bench --version` in the pinned image |
| frappe_docker | `v4.1.1` | reference for the production image build (not exercised in Phase 1) |

The versions of the *running* legacy Docker site (Frappe 15, Helpdesk 1.30.2) are unrelated to this matrix.

## Decision

1. **Frappe 16 line** (`v16.53.0`), ERPNext `v16.52.1`, Python 3.14, Node 24, MariaDB 11.8, Redis 8.6. Pins live in `deploy/versions.env` and `deploy/apps.json`; `deploy/check_pins.py` enforces exact commits.
2. **Helpdesk target base is the upstream release `v1.31.0`**, with the company commits re-applied on top (verified clean). A released base gets upstream hotfix tags, and it supports the Frappe 16 line we run. Basing the product on an unreleased `develop` snapshot is rejected as the long-term plan.
3. **Interim (Phase 1 only):** the bootstrap pins the fork commit that already exists on a remote (`1c6981cc5`) because the rebased branch needs write access to the company fork, which this session lacks (`READ` only). **Phase 2 prerequisite:** push the rebased branch to the fork, build it with the bootstrap, repin `apps.json`.
4. **Two company lines exist** (audit): `company/nxerp-stable` (07f84a2c8) is upstream v1.30.2 plus 12 NXERP commits for Frappe 15 (CI pinned to Frappe `v15.122.0`); the current branch is the Frappe 16 / develop line. This ADR covers the Frappe 16 line only; the legacy Docker site (Frappe 15) is out of scope.
5. The committed branch does **not** contain the colour-palette work: it is uncommitted in the working tree (43 modified + 8 untracked files). Until the owner commits it, a reproducible build has no palette (see `docs/audit/helpdesk-audit.md`).

## Upstream update policy

- **Security fixes:** review upstream releases at least weekly (Frappe `version-16` tags, ERPNext `version-16` tags, Helpdesk `main` tags). A fix is taken by changing the pin, rebuilding from scratch and running the platform tests; a security release is applied within the window the owner sets (ASSUMPTION: 7 days for critical).
- **Minor/patch updates:** monthly batch, one PR, one ADR-002 table update.
- **Major upgrades** (Frappe 17): a new ADR; never in a patch PR.
- Pins are exact commits. A moving branch is only allowed for `nxerp` itself.
- **Not implemented yet:** an automated check that compares pins with the latest upstream tags (recommended scheduled workflow).
