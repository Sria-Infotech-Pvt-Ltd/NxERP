# Plan: hosting NXDESK on the Hostinger server (bare metal, no Docker)

**Status: plan only (2026-11-21). Nothing on the server has been changed except two read-only backup files made on 2026-11-21.** Every step below needs the owner's matching approval before it touches the server (`GO <step id>`), a verified backup and its undo. No secret appears here.

## 1. What is on the server today (read-only look, 2026-11-21)

| Fact | Value |
| --- | --- |
| Machine | Ubuntu 24.04, 4 CPUs, 15 GB RAM (about 7 GB used, load near 0), 193 GB disk (23% used) |
| Runtime | no Docker; Python 3.12, Node 22, MariaDB 10.11 (our pin is 11.8), PostgreSQL 16, Redis, Qdrant; certbot 2.9 installed |
| Two Frappe benches, user `deploy` | `/srv/apps/nxerp/frappe-bench` (site `nxerp.nxsys.in`: frappe 16.53.0, erpnext 16.52.1, payments, nxerp; **no real data**, a 1.1 MB database) and `/srv/apps/helpdesk/frappe-bench` (site `helpdesk.nxsys.in`: frappe 16.53.0, helpdesk 1.22.2, telephony, nxerp; **the only real data**, 2.1 MB database and 16 MB of files, used by employees) |
| Services | systemd units per bench: `*-web` (gunicorn on 127.0.0.1:8005 for nxerp), `*-worker-short`, `*-worker-long`, `*-scheduler`, `*-socketio`, `*-redis-cache`, `*-redis-queue` |
| Other live apps on the same host | agribot, aira, budgeting, cashora, eskoolia, expense, nxgen, nxdesk, and more. Treat every change as high blast radius |
| Ports in use on localhost | 22, 53, 80, 443, 3003, 3004, 3140, 3306, 5000, 5432, 6333, 6334, 6379, 8001 to 8006, 8010, 8011, 8110 to 8180, 9005, 9006, 11005, 11006, 13005, 13006. New services use 8200 and up (check again before each use) |
| Access | SSH alias `nxerp-hostinger` as `deploy`; **`sudo` needs a password**, so nginx, systemd and certbot changes are done by a person in the Hostinger web console (root shell) or by `deploy` with the password. Claude does not hold it |
| Not there | no backup job, no off-host backup, no monitoring |

Because Helpdesk is already its own site and database, **the cutover steps "clone Helpdesk out of the old site" and "move ERP" are not needed**. NXERP has no data to move.

## 2. Target on the server

| Piece | How it runs on bare metal |
| --- | --- |
| Helpdesk (upgraded) | same bench, new code from this branch (customer card, command and Read API client) |
| NXERP (upgraded) | same bench, new code (command API, feed) |
| Identity site `id.nxsys.in` | a third bench `/srv/apps/id/frappe-bench` (frappe + nxerp), its own Redis and systemd units, its own database and database user on the existing MariaDB |
| Shared layer | its own database `nxerp_shared` and accounts; the projector, reconciler and Read API run as systemd units from the NXERP virtualenv (`python -m nxerp.shared_service ...`), listening on 127.0.0.1 only |
| nginx | new server block for `id.nxsys.in`; existing blocks unchanged; the app-to-app paths (`/api/method/nxerp.shared.*` and `nxerp.federation.*`) stay refused on public names |
| TLS | `certbot` certificate for `id.nxsys.in` |
| Backups | a daily encrypted backup of all three sites and the shared layer's accounts, copied off the host |

Isolation on this server is **process, user and database level**, not container level. The restricted database tier (a second MariaDB instance for finance data) is postponed: NXERP holds no data yet, and an instance can be added later without moving anything real. This is a DECISION for the owner to confirm (section 6).

## 3. Order of work, with gates (each step: approval, backup, undo)

| Step | What | Who | Undo |
| --- | --- | --- | --- |
| H0 | **Backups first.** A daily backup timer for the two sites (`bench backup --with-files`, encrypted with `age`, copied off the host), and a restore drill of the 2026-11-21 backups on a scratch machine | Claude writes the unit files; a person with sudo installs them | disable the timer |
| H1 | **Next-version copy beside the live one ("blue/green").** A second Helpdesk bench `/srv/apps/helpdesk-next` on its own ports and database, loaded from a fresh backup, running this branch's code, reachable only as `helpdesk-next.nxsys.in` (or an SSH tunnel). Employees' live Helpdesk is untouched | person with sudo for nginx and DNS | stop and remove the next bench |
| H2 | **Identity site** `id.nxsys.in`: bench, database, nginx block, certificate; users copied from Helpdesk with `cutover.sh build-id` logic | person with sudo; Claude writes the units | stop the units, drop the database |
| H3 | **Shared layer** as systemd units; rebuild from the owners; `rebuild-and-verify` drift 0 | person with sudo; Claude writes the units and a bare-metal variant of `shared.sh` | stop the units |
| H4 | **Canary** on `helpdesk-next`: 3 to 5 agents use it with the real data copy; the support lead signs off (gate G8c) | support lead | nothing changed for others |
| H5 | **Switch.** A short freeze of live Helpdesk (maintenance mode), a final backup, load it into the next bench, change the nginx upstream to the next bench, lift the freeze. The old bench stays stopped, not deleted, for 30 days | owner approves the window (gates G8b, G8d) | point nginx back to the old bench and start it |
| H6 | **Alerts and watch** for 48 hours; decision point D | owner (gate G8e) | n/a |

The blue/green copy makes step H5 a switch of one nginx line, so rollback after the switch is the same line again. That replaces the delta replay for this server, because the old bench is never changed.

## 4. What Claude writes (files only, no server change)

1. `deploy/baremetal/` with systemd unit templates for the identity bench, the next Helpdesk bench and the shared layer, an nginx server block template, a backup timer and script, and a `pull-prod-copy` script (read-only by default, git-ignored output, delete step).
2. `deploy/baremetal/README.md` with the exact commands a person with sudo pastes, in order, one gate at a time.
3. Version and database notes: production MariaDB is 10.11 and our tests ran on 11.8, so the real-data copy is loaded into 11.8 on staging first and any difference is recorded.

## 5. What I need from the owner

1. A person who can run the `sudo` commands on the server (the owner, the senior developer, or the Hostinger web console root shell), at each gate.
2. DNS: who can add records for `id.nxsys.in` and `helpdesk-next.nxsys.in` (A records to the server's address).
3. Outgoing email settings for signup and password mails (SMTP host, port and an account; the password is entered by a person, never sent to Claude).
4. Off-host backup storage and an `age` key kept in the password manager.
5. A maintenance window and the support lead for the canary.

## 6. Decisions to confirm

| Question | Default if no answer |
| --- | --- |
| Postpone the restricted second MariaDB instance (NXERP holds no data)? | yes, postpone |
| Blue/green copy on the same server for the switch? | yes |
| Domain names `id.nxsys.in` and `helpdesk-next.nxsys.in`? | as written |
| Keep MariaDB 10.11 on the server for now (we tested on 11.8)? | yes, record any difference found on the copy |
