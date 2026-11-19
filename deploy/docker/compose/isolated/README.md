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
