# develop

Local develop environment, Compose project `nxerp-develop`, on `http://localhost:8012` (site `nxerp.localhost`).
Same layout as [staging-like](../staging-like/compose.yaml) (MariaDB, two Redis, backend, websocket, worker, scheduler, nginx)
with its own names, port and volumes.

```bash
deploy/docker/build.sh                                  # image from the current commit; put its tag in .env as IMAGE
cd deploy/docker/compose/develop
cp .env.example .env                                    # first time: fill in the passwords (and API settings when known)
docker compose up -d
docker compose --profile init run --rm create-site      # creates the site only when it does not exist
```

After pulling new code: rebuild, update `IMAGE`, `docker compose up -d`, then
`docker compose exec backend bench --site nxerp.localhost migrate`.

| Volume | Holds |
| --- | --- |
| `nxerp-develop_db-data` | MariaDB data |
| `nxerp-develop_sites` | site config, public and private files |
| `nxerp-develop_logs` | bench and site logs |
| `nxerp-develop_redis-queue-data` | queue persistence (AOF) |

HRMS/PBT settings reach only the `backend` service; after changing them run `docker compose up -d backend`.
nginx (the shared `staging-like/nginx.conf.template`) re-resolves `backend` and `websocket` through Docker's DNS, so either
can be restarted alone. `/files/` is proxied with `Host` set to the site, because Frappe's public-file middleware ignores
`X-Frappe-Site-Name`. A missing public file answers 500 instead of 404 (upstream Frappe: the middleware raises NotFound).
`webserver_host`/`webserver_port` point the websocket service's authentication call at `backend:8000`.
The backend runs `frappe.app:application_with_statics()` because the plain WSGI app serves neither `/assets` nor `/files`.
