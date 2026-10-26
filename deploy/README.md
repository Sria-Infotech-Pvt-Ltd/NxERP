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

Not built or tested in Phase 1. The intended route is frappe_docker's layered image with `apps.json` as the build secret (see ADR-001/ADR-006); no registry, staging server or secret exists yet.
