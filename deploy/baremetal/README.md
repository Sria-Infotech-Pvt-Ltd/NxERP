# Bare-metal install for the Hostinger server (no Docker)

For the person who has `sudo` on the server. Companion to `docs/runbooks/hostinger-deploy-steps.md` (code deploy and migration), `docs/runbooks/domains-and-dns.md` (names) and `docs/HANDOVER.md` (what exists, what is verified).

Decision (2026-11-22): the identity site `nxdesk.nxsys.in` is a **second site on the existing `nxerp` bench** (own database and database login, same web and worker processes). This avoids building a third bench. Process-level isolation is not as strong as separate stacks; if that matters later, move the site to its own bench with `bench init`.

## Order

1. **Deploy the code** and migrate both sites: `docs/runbooks/hostinger-deploy-steps.md`. Nothing below is needed for that.
2. **DNS:** the record `A nxdesk 200.234.40.52` in GoDaddy (`docs/runbooks/domains-and-dns.md`).
3. **Backups first.** Copy this repo's `deploy/baremetal/backup/` to a place on the server (the unit expects the repository checkout at `/srv/apps/helpdesk/src/NxERP`, which the deploy script already keeps), then:
   ```
   sudo cp deploy/baremetal/backup/nxdesk-backup.service deploy/baremetal/backup/nxdesk-backup.timer /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now nxdesk-backup.timer
   sudo mkdir -p /var/backups/nxdesk && sudo chown deploy:deploy /var/backups/nxdesk
   sudo systemctl start nxdesk-backup.service && journalctl -u nxdesk-backup.service -n 5 --no-pager
   ```
   Optional: install `age` (`sudo apt install age`), set `AGE_RECIPIENT` and `OFFSITE` in the service for encrypted off-server copies.
4. **The identity site** (on the nxerp bench):
   ```
   cd /srv/apps/nxerp/frappe-bench
   bench new-site nxdesk.nxsys.in --mariadb-root-password "$(cat /srv/apps/helpdesk/.db_password)" --admin-password '<choose one>' --install-app nxerp
   bench --site nxdesk.nxsys.in set-config host_name https://nxdesk.nxsys.in
   bench --site nxdesk.nxsys.in set-config nxerp_site_role identity
   bench --site nxdesk.nxsys.in migrate
   ```
   Then the web entry and certificate: `deploy/baremetal/nginx/nxdesk.conf.template` (its header lists the four commands). Check `https://nxdesk.nxsys.in/login` and `/products`.
   Then connect it to the apps and set up single sign-on exactly as `docs/architecture-isolation/phase-6-user-actions.md` steps 6.2 to 6.8 (peers `helpdesk` = `https://helpdesk.nxsys.in`, `erpnext` = `https://nxerp.nxsys.in`; the OAuth clients; the Social Login Key on each app site). **Do not disable local password login** until single sign-on is proved and a break-glass administrator is recorded (`docs/runbooks/login-recovery.md`).
5. **The shared layer** (optional for the first go-live; everything cross-app stays off until switched on):
   ```
   sudo mkdir -p /etc/nxerp-shared/secrets && sudo chown -R root:deploy /etc/nxerp-shared && sudo chmod 750 /etc/nxerp-shared /etc/nxerp-shared/secrets
   sudo cp deploy/baremetal/shared.env.example /etc/nxerp-shared/shared.env      # then fill every CHANGE_ME, chmod 640
   sudo cp deploy/baremetal/sources.example.json /etc/nxerp-shared/sources.json
   deploy/baremetal/setup-shared-layer.sh /srv/apps/helpdesk/.db_password
   ```
   On the `nxerp` site create a service user with role `NXERP Shared Feed Reader` and an API key; write `api_key:api_secret` (one line) to `/etc/nxerp-shared/secrets/feed-erpnext.key` (mode 640). Then:
   ```
   sudo cp deploy/baremetal/systemd/nxerp-shared-*.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now nxerp-shared-projector nxerp-shared-reconciler nxerp-shared-api
   ```
   Check `curl -s http://127.0.0.1:8210/v1/health`. Create the Helpdesk read token: `set -a; . /etc/nxerp-shared/shared.env; set +a; cd /srv/apps/nxerp/frappe-bench; SHARED_MIGRATE_USER=shared_migrate env/bin/python -m nxerp.shared_service tokens create --app helpdesk` (shown once).
6. **Switch on, one at a time, in this order:** `nxerp_shared_publish 1` on the owner site; wait for lag under 60 s and drift 0 (`python -m nxerp.shared_service status`); then on Helpdesk set `NXDESK_SHARED_API_URL` (`http://127.0.0.1:8210`), `NXDESK_SHARED_API_TOKEN`, the command-API settings and finally `nxerp_shared_read 1`. Undo is the reverse (`docs/runbooks/shared-layer-recovery.md`).
7. **Mail:** Helpdesk already sends through its Gmail account. Give `nxerp.nxsys.in` and `nxdesk.nxsys.in` an outgoing Email Account too (Desk, Email Account; Gmail needs an App password), because signup mail is sent by the site where the person signs up.

## Verified before handover

See `docs/HANDOVER.md`, "What was verified". The shared layer's 178 tests pass on MariaDB 10.11.19 (the server's version) and the migration of both real-data copies passed on staging.
