# Isolated stacks

One authoritative stack per app (identity `id`, ERP `erp`, Helpdesk `hd`, and later apps), next to the running one. Each stack has its own
site, database, database login, Redis pair, worker, scheduler, files volume and secrets; only the edge proxy and the two database servers
are common. Files here: `db.compose.yaml` (database tiers), `stack.compose.yaml` (the one app stack template), `edge.compose.yaml` (edge).
Driven by `deploy/scripts/stack.sh`. Real env files live in `deploy/env/isolated/` and are git-ignored.

## Database tiers

| Server | Network | Used by | Why |
| --- | --- | --- | --- |
| `mariadb-standard` | `nxerp-db-standard` (172.30.10.0/24) | `id`, `hd`, and ordinary future apps | ordinary data |
| `mariadb-restricted` | `nxerp-db-restricted` (172.30.20.0/24) | `erp` | tax, credit, payment and payroll data (class S3) sits on its own server, reachable only by that stack |

Each stack's account is created by `bench new-site --mariadb-user-host-login-scope <subnet>.%`, so it is valid only from its tier's subnet and holds
one grant on its own database. The two networks are `internal: true`: Docker gives them no route to the outside and no port is published, so
the databases cannot be reached from the host or the internet. A stack joins only its own tier's network.

Check: `docker network inspect nxerp-db-restricted --format '{{.Internal}}'` prints `true`; `docker ps --format '{{.Names}} {{.Ports}}'` shows no
published port for the MariaDB containers; `deploy/scripts/stack.sh db ps` shows both `healthy`.

## Stacks

`stack.compose.yaml` is the only app stack file; the compose project name (`nxerp-id`, `nxerp-erp`, `nxerp-hd`, ...) and the env file choose the instance.
A stack contains redis-cache, redis-queue, configurator, create-site (profile `init`), backend, websocket, queue-worker and scheduler. Its networks:
`default` (the project's own), `db` (its tier, joined by configurator, create-site, backend, queue-worker and scheduler only) and `api` (`nxerp-api`, the
app-to-app network, joined by the backend only). The database root password goes to `create-site` only. A failed `create-site` drops what it created.
Every stack's backend has the alias `<stack>-backend` and its websocket `<stack>-websocket`, so shared networks never see two services with one name.

Add an app: copy `deploy/env/isolated/app.env.example` to `<name>.env`, add one line `<name> <host-prefix> <standard|restricted>` to `deploy/env/isolated/stacks.list`,
then `stack.sh <name> create-site`, `stack.sh <name> up`, `stack.sh edge up` (it regenerates the edge). Nothing else changes.

Phase 4's shared project joins the app-to-app network by setting `SHARED_SYNC_NETWORK=nxerp-api` in `deploy/env/shared/shared.env`.

## Edge proxy

One nginx container (`edge.compose.yaml`, project `nxerp-edge`) routes by host name: `<prefix>.<NXERP_DOMAIN>` to that stack's `<stack>-backend:8000` and `/socket.io` to
`<stack>-websocket:9000`, with `X-Frappe-Site-Name` pinned to the stack's site. It publishes only `127.0.0.1:${NXERP_EDGE_PORT}`; the host's nginx and certbot
terminate TLS and forward to that port. It answers 404 for `/api/method/nxerp.shared.*` and `nxerp.federation.*` (also the `/api/v2` and `?cmd=` forms) and for any unknown host.
The configuration is generated: `deploy/scripts/edge-gen.sh` reads `stacks.list` and writes `edge/generated/default.conf.template` and `edge/generated/edge.networks.override.yaml`
(both git-ignored). `stack.sh edge up` runs it first. Public files are served by each backend (the staging-like `/files` shortcut needs one volume per stack and is not used).

## Starting order

1. `docker network create nxerp-api` (once).
2. `deploy/scripts/stack.sh db up` (both database tiers healthy).
3. `deploy/scripts/stack.sh <stack> create-site` once per stack, then `deploy/scripts/stack.sh <stack> up`.
4. `deploy/scripts/stack.sh edge up`.
Stopping is the reverse. `scripts/isolation_audit.sh cross-read reach published hostnames` checks the result.
