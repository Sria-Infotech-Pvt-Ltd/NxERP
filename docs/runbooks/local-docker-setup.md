# Run NXDESK on your own machine with Docker (new employee, fresh clone)

Starts the same layout the server will have: a database tier, three sites (identity `id`, Helpdesk `hd`, NXERP `erp`) and one front door. About 16 GB of RAM and 15 GB of disk are comfortable. Everything here is local: no password or customer data leaves your machine.

## What you need first

| Need | Check |
| --- | --- |
| Docker Desktop, running | `docker info` prints a server section |
| Git and Git Bash (on Windows run the `.sh` scripts in Git Bash) | `git --version` |
| Read access to the GitHub repositories, including the private Helpdesk fork | you can open the repository in a browser; ask the owner for a read token for the image build (`GIT_TOKEN`) |
| Chrome (for the launcher) | any recent version |

## Steps

**1. Clone and pick the branch**

```
git clone https://github.com/Sria-Infotech-Pvt-Ltd/NxERP.git
cd NxERP
git checkout hybrid/phase-8-cutover
```

**2. Build the image once (slow the first time)**

```
GIT_TOKEN=<your read token> deploy/docker/build.sh
```

It prints a tag such as `0.0.1-ab12cd34ef56`. Write it down: it goes into every env file below. If the build is not possible on your machine, ask for the tag of an image someone already built and use `docker pull`.

**3. Create the env files (they are git-ignored; never commit them)**

```
cd deploy/env/isolated
cp stacks.list.example stacks.list
for n in db edge id hd erp; do cp $n.env.example $n.env; done
chmod 600 *.env
```

Fill the values, using a fresh random value for every password (`python -c "import secrets; print(secrets.token_urlsafe(24))"`):

| File | Set |
| --- | --- |
| `db.env` | `NXERP_DB_ROOT_PASSWORD_STANDARD`, `NXERP_DB_ROOT_PASSWORD_RESTRICTED` |
| `id.env`, `hd.env`, `erp.env` | `NXERP_ADMIN_PASSWORD` (this is the `Administrator` password of that site) and `NXERP_IMAGE_TAG` (from step 2) |
| `edge.env` | `NXERP_DOMAIN=example.test` and `NXERP_EDGE_PORT=8180` |

`stacks.list` already has the three lines `id id standard`, `hd hd standard`, `erp erp restricted`. Back at the repository root: `cd ../../..`.

**4. Start the databases and the shared network**

```
docker network create nxerp-api
deploy/scripts/stack.sh db up
deploy/scripts/stack.sh db ps          # both servers say healthy
```

**5. Create and start each site, then the front door**

```
for s in id hd erp; do deploy/scripts/stack.sh $s create-site; deploy/scripts/stack.sh $s up; done
deploy/scripts/stack.sh edge up
for s in id hd erp; do deploy/scripts/stack.sh $s health; done
```

`create-site` takes a few minutes per site. Each `health` line should end with `healthy`.

**6. Open it**

Double-click `scripts/open-nxdesk-local.cmd` (or run `scripts/open-nxdesk-local.ps1` in PowerShell). It opens a separate Chrome window on the front page. In that window:

| Address | What it is |
| --- | --- |
| `http://id.example.test:8080/` | the NXDESK front page and sign-in |
| `http://hd.example.test:8080/` | Sria Helpdesk (`/helpdesk` for the agent screens) |
| `http://erp.example.test:8080/` | NXERP |

Sign in as `Administrator` with the `NXERP_ADMIN_PASSWORD` of that site. The names only work in that window because the launcher maps `*.example.test` to your front door.

## The one thing that confuses everyone: 404

`http://127.0.0.1:8180/` (the front door's port) answers **404 Not Found on purpose**. The front door picks the site from the name in the address, and a bare IP has no name. Use the launcher, or the addresses above in the launcher's Chrome window. Checking from a terminal: `curl -H "Host: hd.example.test" http://127.0.0.1:8180/login` answers 200.

Ports: only the front door is published, on `127.0.0.1:8180`. The databases publish nothing. No container uses port 80.

## Day to day

```
deploy/scripts/stack.sh <id|hd|erp|db|edge> ps | logs | up | down | health | bench <bench arguments>
```

Stop in the reverse order of the start: edge, the three sites, then `db`. After a reboot or after Docker Desktop restarts, containers come back on their own; if one does not, run `stack.sh <name> up`.

Throw everything away and start again (local data only): `NXERP_ALLOW_DESTROY=1 deploy/scripts/stack.sh <name> down -v` for each stack and `db`.

## Optional

| Goal | Where |
| --- | --- |
| The shared read layer (customer card in Helpdesk, Read API) | `deploy/scripts/shared.sh init-env`, then `up`; read `docs/runbooks/shared-layer-recovery.md` and `docs/architecture/shared-data-contracts.md` |
| Real or sample data | `deploy/scripts/stack.sh hd restore --yes <backup folder>` (the folder needs the files `bench backup --with-files` makes plus a `SHA256SUMS`). Before using real data switch email off: `stack.sh hd bench set-config mute_emails 1` and keep the scheduler off |
| Mail to a real inbox | add an Email Account in Desk (for Gmail an App password, 16 letters) |
| Run the tests | `deploy/scripts/shared.sh test`; the site tests run with `bench --site <site> run-tests --app nxerp --module nxerp.tests.<name>` after setting `allow_tests` |
| Use `*.localhost` names (no launcher) | set `NXERP_DOMAIN=localhost` in `edge.env` and `NXERP_SITE=id.localhost` (and `hd.localhost`, `erp.localhost`) in the three env files before `create-site`; Chrome then resolves them itself. This follows the isolation runbook and has not been re-tested for this guide |

## If something fails

| Symptom | Likely cause and fix |
| --- | --- |
| `docker: failed to connect to the docker API` | Docker Desktop is not running; start it and wait a minute |
| `create-site` fails | the databases are not healthy (`stack.sh db ps`) or `nxerp-api` does not exist; run `stack.sh <name> create-site` again, it cleans up after itself |
| 404 in the browser | see "404" above |
| `unhealthy` for a minute after start | normal while a site warms up; check again with `stack.sh <name> health` |
| A script prints a Windows path error | run it in Git Bash, not in PowerShell |
