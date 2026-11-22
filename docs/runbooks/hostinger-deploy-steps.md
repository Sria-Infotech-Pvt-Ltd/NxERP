# Deploying the new code to the Hostinger server (step by step, for the person at the keyboard)

Written 2026-11-21 from a read-only look at the server. It uses the server's own deploy script, so nothing new is installed. About 30 minutes, with the sites in maintenance mode for about 15 of them. No secret appears here.

## What is on the server today

- Two benches: `/srv/apps/nxerp/frappe-bench` (site `nxerp.nxsys.in`, no real data) and `/srv/apps/helpdesk/frappe-bench` (site `helpdesk.nxsys.in`, **all real data**). Services are systemd units named `nxerp-*` and `helpdesk-*`.
- The code on the server is the repository **as of 2026-11-05 (commit `997ac7936`)**. Everything built since then (sign-up and onboarding pages, the shared layer, the command API, the customer card, the cutover tools, the themed pages) is **not on the server**.
- `/srv/apps/deploy-nxerp-apps.sh <full-commit-sha>` updates both benches from `github.com/Sria-Infotech-Pvt-Ltd/NxERP`: it fetches, copies the apps into each bench, builds the front end, clears the cache and restarts the services (the restart asks for the `sudo` password). **It does not migrate the database**, so step 5 does.
- Production already has outgoing mail on Helpdesk (`mute_emails` is 0 and the Gmail account `sriainfotech@gmail.com` is the default sender) and `host_name` is `https://helpdesk.nxsys.in`, so emailed links will be right. The `nxerp` site has no mail account yet.

## What this deploy changes for real users

- New public pages: `/signup`, `/get-started`, the themed login, set-password and error pages. **Signup is open to anyone** on both sites (owner's decision of 2026-11-21; the one-line way to close it is in `docs/features/signup-gate.md`).
- New database tables and fields, created by the migration. Everything cross-app (shared layer, command API, shared read, identity site) is **switched off by default** and does nothing until configured.
- Helpdesk renames a column (`erpnext_customer` to `customer_ref_id`) in a patch that runs before the schema update. It is safe to repeat and is covered by the backup in step 1.

## The commit to deploy

`7e7e6d7bbc4cf3439842bac96e052c15c9b9aaff` (branch `hybrid/phase-8-cutover`, already pushed). The script fetches every branch, so it does not have to be merged into `main` first.

## Steps

Open a terminal on your laptop: `ssh -t nxerp-hostinger` (or use the Hostinger web console and `su - deploy`). Have the `sudo` password of the `deploy` user ready.

**1. Back up both sites and copy the backups to your laptop (5 minutes)**

```
for pair in "nxerp nxerp.nxsys.in" "helpdesk helpdesk.nxsys.in"; do set -- $pair; (cd /srv/apps/$1/frappe-bench && /home/deploy/.local/bin/bench --site $2 backup --with-files); done
ls -l /srv/apps/helpdesk/frappe-bench/sites/helpdesk.nxsys.in/private/backups | tail -4
```

Note the two file names that end in `-database.sql.gz` with today's time: you need them for a rollback. Copy them off the server (run this on your laptop, not on the server):

```
scp nxerp-hostinger:/srv/apps/helpdesk/frappe-bench/sites/helpdesk.nxsys.in/private/backups/<newest>-database.sql.gz .
```

**2. Put both sites in maintenance mode (1 minute)**

```
cd /srv/apps/helpdesk/frappe-bench && /home/deploy/.local/bin/bench --site helpdesk.nxsys.in set-config maintenance_mode 1
cd /srv/apps/nxerp/frappe-bench    && /home/deploy/.local/bin/bench --site nxerp.nxsys.in set-config maintenance_mode 1
```

**3. Deploy the code (about 10 minutes; it asks for the sudo password when it restarts the services)**

```
/srv/apps/deploy-nxerp-apps.sh 7e7e6d7bbc4cf3439842bac96e052c15c9b9aaff
```

**Stop if** it prints `REAL LOCAL CHANGES ... stopping` or a build error. Nothing is migrated yet; go to "Rollback, code only" below.

**4. Migrate the databases (2 to 4 minutes)**

```
cd /srv/apps/nxerp/frappe-bench    && /home/deploy/.local/bin/bench --site nxerp.nxsys.in migrate
cd /srv/apps/helpdesk/frappe-bench && /home/deploy/.local/bin/bench --site helpdesk.nxsys.in migrate
```

**Stop if** a migrate prints an error: go to "Rollback, code and data".

**5. Restart once more and leave maintenance mode**

```
sudo systemctl restart nxerp-web nxerp-socketio nxerp-worker-short nxerp-worker-long nxerp-scheduler helpdesk-web helpdesk-socketio helpdesk-worker-short helpdesk-worker-long helpdesk-scheduler
cd /srv/apps/helpdesk/frappe-bench && /home/deploy/.local/bin/bench --site helpdesk.nxsys.in set-config maintenance_mode 0
cd /srv/apps/nxerp/frappe-bench    && /home/deploy/.local/bin/bench --site nxerp.nxsys.in set-config maintenance_mode 0
```

**6. Check it (5 minutes)**

1. `https://helpdesk.nxsys.in/login`: signs in as before. Your tickets are there.
2. `https://helpdesk.nxsys.in/products`: the NXDESK front page.
3. `https://helpdesk.nxsys.in/signup?app=helpdesk`: the sign-up form.
4. Sign up with an address you control, for example `yourname+test1@gmail.com`. The email arrives in your Gmail within a minute, sent by the company account.
5. Open the link in the email: the set-password page has the NXDESK look. Set a password and sign in.
6. `https://helpdesk.nxsys.in/this-page-does-not-exist`: the themed "Page not found" page.

## Rollback, code only (nothing migrated yet)

```
OLD=$(git -C /srv/apps/helpdesk/src/NxERP rev-parse 997ac7936)
/srv/apps/deploy-nxerp-apps.sh $OLD
```

then step 5 (leave maintenance mode).

## Rollback, code and data (a migrate failed or the sites misbehave)

```
OLD=$(git -C /srv/apps/helpdesk/src/NxERP rev-parse 997ac7936)
/srv/apps/deploy-nxerp-apps.sh $OLD
cd /srv/apps/helpdesk/frappe-bench && /home/deploy/.local/bin/bench --site helpdesk.nxsys.in --force restore /srv/apps/helpdesk/frappe-bench/sites/helpdesk.nxsys.in/private/backups/<the step-1 database file> --with-public-files <the matching -files.tar> --with-private-files <the matching -private-files.tar> --mariadb-root-password "$(cat /srv/apps/helpdesk/.db_password)"
```

Do the same for `nxerp.nxsys.in` from its own bench, then step 5. The databases are small (2 MB and 1 MB), so a restore takes about a minute.

## Not part of this deploy (still to do later)

The identity site `id.nxsys.in`, the shared layer, shared read in Helpdesk, the cutover tools and the removal of the old sync are built and tested but stay off. They need the plan in `hostinger-bare-metal-hosting.md` and the owner's go for each. The `nxerp` site still has no outgoing mail account.
