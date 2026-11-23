# India Compliance in NXERP

India Compliance is the open-source app (`resilient-tech/india-compliance`, GPL-3.0) that adds GST, GSTIN checks, e-invoicing (IRN), e-way bills, TDS and India-specific reports to ERPNext. It is part of NXERP (owner decision, 2026-11-23).

## How it is integrated

| What | Where |
| --- | --- |
| Pinned upstream release `v16.11.1`, exact commit `68982391ab0e487ba418c1f58359b193680136ec`; never copied into this repository and never edited | `deploy/apps.json` (installed after `erpnext`, before `telephony`, `helpdesk`, `nxerp`), `docs/adr/ADR-002-version-matrix.md` row and decision 6; `deploy/check_pins.py` passes |
| Installed on the **NXERP site only** (not on Helpdesk or the identity site) | `NXERP_STACK_APPS=payments erpnext india_compliance nxerp` in `deploy/env/isolated/erp.env.example` |
| Its whitelisted methods are covered by the ERPNext access grant | `registry.py`, entry `erpnext`, `owns` now includes `india_compliance` |
| The NXDESK look | applies to the public and sign-in pages. India Compliance adds Desk screens (GST Settings, GSTIN fields, reports), which keep the standard Frappe Desk look |

Requirements met: `frappe >=16.0.0,<17.0.0`, `required_apps = frappe/erpnext`.

## What was verified (2026-11-23, staging)

| Check | Result |
| --- | --- |
| `bench get-app` at the tag gives exactly the pinned commit | yes |
| `install-app india_compliance` on a copy of the real NXERP database | exit 0 in 20 s; `GST Settings`, the `gstin` field on Customer and the modules `GST India`, `Income Tax India`, `VAT India`, `Audit Trail` exist |
| `bench migrate` afterwards, and `bench build --app india_compliance` | exit 0 |
| Existing pages on that site (`/login`, `/products`, `/signup`, `/update-password`, 404, `/desk`) | unchanged answers |
| Hooks that both apps define | no overlapping method overrides; shared hooks (`after_install`, `after_migrate`, `Customer` and `Company` events, scheduler) are merged by Frappe. Our sign-in gate (`auth_hook`) and home-page hook stay active |
| Our test suites on a site with all apps plus India Compliance | registry 14, routing 31, guard and admin 14, themed pages 4, commands 17, outbox 17, feed 21, onboarding 29, federation 31, identity site 18, cutover 22, Helpdesk customer 27 and shared integration 33: all OK |
| Not verified | filing real GST returns, e-invoice and e-way bill calls (they need GSP credentials and a configured company), the browser look of its Desk screens, and any behaviour on the live server |

Notes: on an existing site `install-app` puts it after `nxerp` in the site's installed order (a fresh `create-site` follows `NXERP_STACK_APPS`, so `nxerp` is last there). No hook conflict was found, so this is harmless today; keep it in mind if a future change overrides the same hook in both apps.

## Install on the live NXERP site (`nxerp.nxsys.in`), after the main deploy

The server's `deploy-nxerp-apps.sh` updates only `helpdesk` and `nxerp`, so this app is added once by hand. NXERP holds no real data today, which makes this the cheapest time to add it. About 15 minutes.

```
# 1. back up first and keep the file name
cd /srv/apps/nxerp/frappe-bench && /home/deploy/.local/bin/bench --site nxerp.nxsys.in backup --with-files
/home/deploy/.local/bin/bench --site nxerp.nxsys.in set-config maintenance_mode 1
# 2. fetch exactly the pinned release
/home/deploy/.local/bin/bench get-app --skip-assets --branch v16.11.1 india_compliance https://github.com/resilient-tech/india-compliance
test "$(git -C apps/india_compliance rev-parse HEAD)" = 68982391ab0e487ba418c1f58359b193680136ec && echo "pin ok"
# 3. keep nxerp last in the app list, then install, migrate, build
printf 'frappe\npayments\nerpnext\nindia_compliance\nnxerp\n' > sites/apps.txt
/home/deploy/.local/bin/bench --site nxerp.nxsys.in install-app india_compliance
/home/deploy/.local/bin/bench --site nxerp.nxsys.in migrate
/home/deploy/.local/bin/bench build --app india_compliance
# 4. restart and open the site again
sudo systemctl restart nxerp-web nxerp-socketio nxerp-worker-short nxerp-worker-long nxerp-scheduler
/home/deploy/.local/bin/bench --site nxerp.nxsys.in set-config maintenance_mode 0
```

(The `apps.txt` line lists exactly the apps that are in that bench's `apps` folder today: check `ls apps` and keep `frappe` first and `nxerp` last.) Check: `https://nxerp.nxsys.in/login` opens; in Desk, search "GST Settings".

**First use:** in Desk create the Company with country India (or set it on the existing one), open **GST Settings**, enter the company GSTIN and, for e-invoicing and e-way bills, the GSP credentials. India Compliance's own documentation covers filing: `https://docs.indiacompliance.app`.

## Rollback

```
cd /srv/apps/nxerp/frappe-bench
/home/deploy/.local/bin/bench --site nxerp.nxsys.in set-config maintenance_mode 1
/home/deploy/.local/bin/bench --site nxerp.nxsys.in uninstall-app india_compliance --yes
```
and, if anything still misbehaves, restore the backup from step 1 (`docs/runbooks/hostinger-deploy-steps.md`, "Rollback, code and data"). Then remove the line from `sites/apps.txt` and restart.

## Updating it later

A new release means changing the pin in `deploy/apps.json` and the ADR-002 row (one pull request), re-running this verification, then `git -C apps/india_compliance fetch && checkout <new tag>` on the server, `bench migrate`, `bench build --app india_compliance`, and a restart. Never edit its source in place: if a change is needed, fork it, pin the fork, and record why in ADR-002.
