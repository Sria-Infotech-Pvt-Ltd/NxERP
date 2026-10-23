# Deployment Guide

> **This document describes a Frappe Bench deployment model. Before modifying any step, verify it matches your actual server configuration.**

---

## Production Environment

- **URL:** https://nxerp.nxsys.in
- **Deployment model:** Frappe Bench on a managed Linux server
- **Database:** MariaDB 10.6+
- **Process manager:** Supervisor (managed by Bench)
- **Web server:** Nginx (reverse proxy to Gunicorn)

Treat `nxerp.nxsys.in` as production. Do not run destructive operations or unapproved migrations on this environment.

---

## Pre-Deployment Checklist

Before every deployment (staging or production):

- [ ] All CI checks pass on the target commit
- [ ] Changes have been reviewed and approved per the PR process
- [ ] A database backup has been taken and verified
- [ ] The staging environment has been deployed and tested first
- [ ] Any new DocType patches are registered in `patches.txt`
- [ ] Frontend build has been verified locally
- [ ] The deployment PR / change request is linked in the commit/tag

---

## Staging Deployment

Staging deploys automatically when `main` is pushed (via `cd-staging.yml`), provided the required secrets are configured. See the [CD workflow](../.github/workflows/cd-staging.yml) for details.

**Required GitHub Actions secrets:**

| Secret | Value |
|--------|-------|
| `STAGING_SSH_KEY` | Private SSH key for the staging server |
| `STAGING_HOST` | Hostname or IP |
| `STAGING_USER` | SSH user |
| `STAGING_SITE` | Frappe site name |
| `STAGING_BENCH_PATH` | Absolute bench path on server |

---

## Production Deployment Procedure

> Performed manually by the DevOps team after staging validation and explicit authorization.

### Step 1: Take a database backup

```bash
ssh user@nxerp.nxsys.in
cd ~/nxerp-bench
bench --site nxerp.nxsys.in backup --with-files
```

Record the backup path. Verify the backup is readable before proceeding.

### Step 2: Put the site in maintenance mode (optional for critical changes)

```bash
bench --site nxerp.nxsys.in set-maintenance-mode on
```

### Step 3: Pull the new code

```bash
cd ~/nxerp-bench/apps/helpdesk
git fetch origin
git checkout main
git pull origin main

cd ~/nxerp-bench/apps/nxerp
git fetch origin
git checkout main
git pull origin main
```

### Step 4: Install new Python dependencies

```bash
cd ~/nxerp-bench
./env/bin/pip install -e apps/helpdesk -e apps/nxerp
```

### Step 5: Build frontend assets

```bash
cd ~/nxerp-bench/apps/helpdesk/desk
yarn install --frozen-lockfile
cd ~/nxerp-bench
bench build --app helpdesk --production
```

### Step 6: Run database migrations

```bash
bench --site nxerp.nxsys.in migrate
```

> ⚠️ **Never run `migrate` without a verified backup.**  
> Migrations are one-way. Patches registered in `patches.txt` run once and are not reversible without a database restore.

### Step 7: Clear cache

```bash
bench --site nxerp.nxsys.in clear-cache
bench --site nxerp.nxsys.in clear-website-cache
```

### Step 8: Disable maintenance mode

```bash
bench --site nxerp.nxsys.in set-maintenance-mode off
```

### Step 9: Restart services

```bash
sudo supervisorctl restart all
# or
bench restart
```

### Step 10: Health check

```bash
curl -f https://nxerp.nxsys.in/api/method/ping
```

Expected: `{"message":"pong"}`

Also manually verify:
- Login page loads at `https://nxerp.nxsys.in/login`
- Frappe Desk loads at `https://nxerp.nxsys.in/app`
- Helpdesk loads at `https://nxerp.nxsys.in/helpdesk`
- An agent can log in and view tickets

---

## Rollback Procedure

If the deployment fails or causes regressions:

### Code rollback

```bash
cd ~/nxerp-bench/apps/helpdesk
git fetch origin
git checkout <previous-commit-sha>

cd ~/nxerp-bench/apps/nxerp
git checkout <previous-commit-sha>

# Rebuild and restart
bench build --app helpdesk --production
bench restart
```

### Database rollback

Only if migrations ran and the code rollback alone is insufficient:

```bash
# Restore from pre-deployment backup
# DESTRUCTIVE — all data changes since the backup will be lost
bench --site nxerp.nxsys.in restore /path/to/backup.sql.gz
```

Coordinate with the database administrator before restoring.

---

## Release Tagging

After a successful production deployment:

```bash
git tag v2026.10.1
git push origin v2026.10.1
```

The `release.yml` workflow creates a GitHub Release automatically.

Use calendar versioning: `vYYYY.MM.PATCH`

---

## First-Time Installation on a New Server

```bash
# Install bench
pip install frappe-bench

# Initialize bench with Frappe v16
bench init --frappe-branch version-16 ~/nxerp-bench
cd ~/nxerp-bench

# Get apps
bench get-app erpnext --branch version-16
bench get-app telephony
bench get-app helpdesk https://github.com/Sria-Infotech-Pvt-Ltd/NxERP.git --branch main
# Note: get-app will clone the full repo; apps/helpdesk/ is the app path
bench get-app nxerp https://github.com/Sria-Infotech-Pvt-Ltd/NxERP.git --branch main

# Create the site
bench new-site nxerp.nxsys.in \
  --db-root-password <mariadb-root-password> \
  --admin-password <admin-password>

# Install apps (ORDER MATTERS: nxerp must be last)
bench --site nxerp.nxsys.in install-app erpnext
bench --site nxerp.nxsys.in install-app telephony
bench --site nxerp.nxsys.in install-app helpdesk
bench --site nxerp.nxsys.in install-app nxerp

# Apply NXERP branding to database settings
bench --site nxerp.nxsys.in execute nxerp.branding.apply_branding

# Configure production mode
bench setup nginx
bench setup supervisor
sudo supervisorctl update
sudo nginx -t && sudo nginx -s reload
```

---

## Secrets and Configuration

Site-specific configuration lives in `~/nxerp-bench/sites/nxerp.nxsys.in/site_config.json`. This file is **never** committed to version control.

Example entries (do not commit actual values):

```json
{
  "db_host": "localhost",
  "db_port": 3306,
  "db_name": "nxerp_site",
  "db_password": "<REPLACE>",
  "redis_cache": "redis://localhost:13000",
  "redis_queue": "redis://localhost:11000",
  "redis_socketio": "redis://localhost:12000",
  "nxerp_support_url": "https://mail.google.com/mail/?view=cm&to=it@yourdomain.com",
  "block_endpoints": 1
}
```

See `.env.example` for the full reference without actual values.
