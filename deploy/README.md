# deploy/

Everything needed to build a reproducible NXERP bench. No secrets live here.

| File | Purpose |
| --- | --- |
| `versions.env` | Frappe tag + commit, `frappe/bench` image digest, MariaDB and Redis images |
| `apps.json` | Other apps in install order, each pinned to an exact commit (`nxerp` follows `main`) |
| `check_pins.py` | CI check that the pins are complete and exact |
| `dev/compose.yaml` | Local stack: MariaDB 11.8, two Redis, one bench container |
| `dev/bootstrap.sh` | Runs inside the bench container: bench init, get-app, new-site, install-app, build, start |
| `dev/up.sh` | The one command (generates `dev/.env` with random passwords on first run) |
| `docker/` | Production-style image: `Dockerfile` (pinned bench base, apps at pinned commits, built assets), `build.sh` (tag `<version>-<git sha>`, SBOM when syft is available), `install_apps.sh`, `entrypoint.sh` |
| `staging-like/` | Compose rehearsal environment: the image + MariaDB + Redis + nginx; `.env.example`, no secrets |
| `environments/` | `staging/` and `production/` config templates and which values are secrets (GitHub Environments) |
| `scripts/` | `backup.sh restore.sh migrate.sh deploy.sh rollback.sh healthcheck.sh smoke.sh` (+ `lib.sh`), parameterised by site and compose file; used by the deploy workflows and the runbooks |

## Bring up the dev platform

```bash
./deploy/dev/up.sh -d
docker compose -p nxerp-dev logs -f bench     # wait for "[bootstrap] ready:"
```

- Site: `http://nxerp.localhost:8100` (ERPNext Desk `/app`, Helpdesk `/helpdesk`, login `/login`). Realtime on `9100`.
- `Administrator` password: the generated value in `deploy/dev/.env` (git-ignored; never share it).
- Stop: `./deploy/dev/up.sh down` (volumes kept). Full reset (destroys the dev site and database): `docker compose -p nxerp-dev down -v`.
- Ports 8100/9100 and project name `nxerp-dev` are chosen so this stack never collides with other Frappe stacks on the machine.

### How it is put together

- The bench lives in a named Docker volume (fast, and outside OneDrive/Windows file sharing). The repository is mounted at `/workspace`.
- The `nxerp` app is **soft-linked** from `/workspace`, so edits apply live. Every other app is fetched at its pinned commit into the `vendor-data` volume and cloned into the bench (a soft link broke ERPNext's `banking/vite.config.ts`, which resolves `../../sites` from the real path). If a pin no longer resolves to its commit, the bootstrap fails on purpose.
- **Helpdesk source:** if a sibling `../helpdesk` git checkout exists, `up.sh` mounts it read-only and the bootstrap installs the branch checked out there (override with `HELPDESK_REF=<branch>`). Only committed work is installed, so commit before rebuilding. Without the sibling folder, the pinned fork commit from `apps.json` is used.
- First-time Frappe/ERPNext setup wizard is **not** run by the bootstrap; it stays pending so the real first-run admin flow can be exercised.

### Seed fake users (dev only)

```bash
docker compose -p nxerp-dev exec bench bash -lc \
  'cd frappe-bench && NXERP_SEED_PASSWORD="<choose one>" bench --site nxerp.localhost execute nxerp.tests.seed_users.seed'
```

Creates `admin@`, `agent@`, `manager@`, `erpuser@`, `customer@example.test`. Omit `NXERP_SEED_PASSWORD` to have one generated and printed once. The script refuses to run unless `developer_mode` is on.

## Changing a pin

1. Update `versions.env` or `apps.json` (commit sha, not a moving branch).
2. Update [ADR-002](../docs/adr/ADR-002-version-matrix.md).
3. `python3 -I deploy/check_pins.py`, then rebuild from scratch (`down -v`, `up.sh -d`) and run the tests.

## Production images

`docker/Dockerfile` builds from the digest-pinned `frappe/bench` image, installs Frappe and every app in `apps.json` at its exact commit
(a pin that resolves to a different commit fails the build) and `nxerp` from the checkout being built, then runs `bench build`.
`python3 -I deploy/check_pins.py` also fails when the Dockerfile's default build args drift from `versions.env`.

```bash
deploy/docker/build.sh --dry-run     # print the command
deploy/docker/build.sh               # build locally (needs ~15 GB free disk and network)
```

**Status:** `docker buildx build --check` passes; the image has **not** been built, run or pushed, and `staging-like/` has not been
started. Registry, hosts, domains, secrets and Environments do not exist yet: [docs/governance/owner-action-list.md](../docs/governance/owner-action-list.md).
Runbooks: [release](../docs/runbooks/release.md), [deploy](../docs/runbooks/deploy.md), [backup-restore](../docs/runbooks/backup-restore.md),
[rollback](../docs/runbooks/rollback.md), [migration-planning](../docs/runbooks/migration-planning.md).
