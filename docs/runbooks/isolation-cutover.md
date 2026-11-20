# Runbook: cutover from the single-site stack to the isolated stacks

Moves Helpdesk and the identity data out of the live single site into the `hd` and `id` stacks, then (after decision point D) moves ERPNext into its own restricted `erp` stack. Rollback is real until D because the old site is not changed except for maintenance mode (see [isolation-rollback.md](isolation-rollback.md)).

**Status of this document:** written, rehearsed only on the scratch bench so far (`docs/architecture-isolation/rehearsal-dev.md`). No production step has been run. No GitHub workflow has run (see "Workflows" at the end).

## Roles and approvals

| Role | Who | Decides |
| --- | --- | --- |
| Operator | the person (or Claude Code, at the owner's request) running the commands | nothing alone: stops at every gate |
| Owner | [Owner Name] | the window (G8a), the freeze (G8b), opening to customers (G8d), decision D (G8e) |
| Support lead | [Support Lead] | the canary result (G8c) |
| Accountant | [Accountant] | the finance check after the ERP move |

Every production change needs the owner's matching approval, a verified backup and a written undo. Secrets live in mode-600 env files outside git and in the password manager; nothing below contains one.

## The commands

`deploy/scripts/cutover.sh` does a dry run unless `--yes` is given, prints its undo after every step and records progress in `deploy/env/cutover/state.env` (`cutover.sh status`). Destructive steps also need a typed phrase (`NXERP_CUTOVER_CONFIRM` when there is no terminal). The tools in `nxerp/cutover.py` refuse to run unless `nxerp_cutover_allowed` is 1 on that site; `freeze` sets it on the source and `unfreeze` removes it, a person sets it on `hd` and `id`.

The source is described by `NXERP_CUTOVER_SOURCE_PROJECT`, `NXERP_CUTOVER_SOURCE_SITE` and, when it is not the default, `NXERP_CUTOVER_SOURCE_COMPOSE_FILE`.

## Step 8.1 Build the rehearsal environment (scratch machine)

Repeat the Phase 5 stack steps with domain `localhost` and fresh secrets, then:

```
deploy/scripts/stack.sh db up
docker network create nxerp-api
for s in id hd; do deploy/scripts/stack.sh $s create-site; deploy/scripts/stack.sh $s up; done
deploy/scripts/stack.sh edge up
export NXERP_CUTOVER_SOURCE_PROJECT=nxerp-scratch NXERP_CUTOVER_SOURCE_SITE=<scratch site>
```

Restore the production backup copy as the source (Phase 1 steps 1.4 to 1.6) and **neutralise it** (mute emails, disable the scheduler, Email Accounts and Webhooks). Never skip that.
**Pass:** all projects up; `curl -s http://id.localhost:8080/api/method/ping` returns `pong`; `docker compose ls`. **Stop if** the restored copy is not neutralised. **Undo:** `NXERP_ALLOW_DESTROY=1 deploy/scripts/stack.sh <stack> down -v` (rehearsal stacks only, never production). **Decides:** operator.

Attach the old backend to the sync network as the interim ERP app: `docker compose -p <old project> -f <old compose file> -f deploy/docker/compose/isolated/legacy-erp.override.yaml up -d backend`. **Undo:** run the same command without the override file.

## Step 8.2 Rehearse the whole cutover, twice

```
deploy/scripts/stack.sh hd bench set-config nxerp_cutover_allowed 1
deploy/scripts/stack.sh id bench set-config nxerp_cutover_allowed 1
date -u +%FT%TZ                                   # start time
deploy/scripts/shared.sh stop projector           # the pre-flight check wants it paused
deploy/scripts/cutover.sh freeze --yes            # prints T0
deploy/scripts/cutover.sh backup-source --yes     # prints RP0
deploy/scripts/cutover.sh clone-hd --yes <RP0 path>
deploy/scripts/cutover.sh build-id --yes
deploy/scripts/cutover.sh reconcile
date -u +%FT%TZ                                   # end time
```

**Pass:** every command exits 0; `reconcile` prints `RESULT: PASS`; ERP counts on the source unchanged; tests T1 to T8 pass on the rehearsal stacks; a seeded fake user signs in once at `http://id.localhost:8080` and 2FA works. Then rehearse the way back: create two fake tickets on `hd`, `cutover.sh delta-export --since <T0> --yes`, `cutover.sh delta-import --yes <bundle>` (expect 2 added, 0 conflicts), `cutover.sh unfreeze --yes`.
**Pass rule:** two consecutive runs, no manual fixes, a freeze time the owner accepts (assumption A6: 2 hours). Record both in `docs/architecture-isolation/rehearsal-1.md` and `rehearsal-2.md`. **Stop if** a run needs a manual fix: fix the tool, start again from a fresh restore. **Undo:** destroy the rehearsal stacks and restore again. **Decides:** owner reads the reports (gate G8a).

## Step 8.3 Prepare the production window (T-7 days to T-1 day)

1. Announce the window: when, how long, what changes (sign in again at one address; ticket links keep working). No personal data in the text.
2. One day before, lower the DNS TTL of `hd.<domain>` and the old host name to 300 seconds.
3. `df -h`: room for the backup, the restore and the clone (three times the database size).
4. Run the Phase 1 restore drill again on the newest production backup.
5. Create the production stacks (Phase 5 steps 5.4 to 5.7 with real passwords); sites `id` and `hd` only; leave `erp` stopped.
6. Attach the old site as the interim ERP app: the override command of step 8.1, then on the old site `nxerp_site_role app`, `nxerp_shared_publish 1`, a Peer origin for `erpnext`, a Social Login Key to `id` (Phase 6 steps 6.3 to 6.6); **leave local login enabled** until step 8.9.
   **Pass:** `docker exec <hd backend> curl -s -H 'X-Frappe-Site-Name: <old site>' http://erp-backend:8000/api/method/ping` prints `pong`; `cutover.sh preflight` passes.
**Stop if** any check is red. **Undo:** recreate the old backend without the override; restore the TTL. **Decides:** owner.

## Step 8.4 Cutover day: freeze, back up, build (gate G8b first)

The owner replies `GO FREEZE`. Then:

```
deploy/scripts/shared.sh stop projector
deploy/scripts/cutover.sh freeze --yes
deploy/scripts/cutover.sh backup-source --yes     # RP0: copy it off the host, encrypt it (age)
deploy/scripts/stack.sh hd bench set-config nxerp_cutover_allowed 1
deploy/scripts/stack.sh id bench set-config nxerp_cutover_allowed 1
deploy/scripts/cutover.sh clone-hd --yes <RP0 path>
deploy/scripts/cutover.sh build-id --yes
deploy/scripts/cutover.sh reconcile
```

**Pass:** every command exits 0; the report says `RESULT: PASS`. **Stop if** FAIL: do not continue; run `cutover.sh unfreeze --yes --restore-email` (users are back on the old site, nothing there changed). Take RP1 (a backup of `hd` after the prune): `deploy/scripts/stack.sh hd backup`. **Decides:** operator on PASS; owner on FAIL.

## Step 8.5 Canary: agents only (gate G8c)

The `hd` scheduler and inbound email are still off; the customer portal is not announced.

1. Confirm `curl -s https://hd.<domain>/api/method/ping`.
2. The 3 to 5 canary agents sign in at `https://id.<domain>`, open Helpdesk, open five existing tickets, reply to one internal test ticket, and open an ERP customer from the ERPNext tile.
3. Compare 10 random tickets with the old site.

**Pass:** history, attachments and comments match; one password only; the support lead signs off in writing (`CANARY OK`). **Stop if** anything differs. **Undo:** `cutover.sh unfreeze --yes --restore-email`; agents use the old address; replay internal canary writes by hand. **Decides:** support lead.

## Step 8.6 Open to customers (gate G8d)

The owner replies `GO OPEN TO CUSTOMERS`. Then:

```
deploy/scripts/stack.sh hd bench enable-scheduler
# on hd: enable ONE mailbox poller (the account(s) listed in deploy/env/cutover/email_accounts.txt); the old site's stay disabled
# in deploy/env/isolated/edge.env: NXERP_LEGACY_HOST=<old host>  NXERP_LEGACY_SITE=<old site>
deploy/scripts/stack.sh edge up
```

**Pass:** `curl -sI https://<old host>/helpdesk/my-tickets` answers `301` with `Location: https://hd.<domain>/helpdesk/my-tickets`; a test email makes exactly one ticket on `hd` and none on the old site; `cutover.sh reconcile` shows no duplicate message id. **Undo:** disable the incoming account on `hd`, re-enable it on the old site, `delta-export` then `delta-import`, `unfreeze --restore-email`, point the edge back. **Decides:** owner.

## Step 8.7 Watch for 48 hours

Check grant drift, Webhook Request Log failures, gate denials, failed database authentications, backup age, and the shared-layer alerts (step 8.13). Daily encrypted backup of `hd` and `id` (RP2). **Stop if** a failure repeats: follow the rollback table. **Undo:** none needed.

## Step 8.8 Decision point D (gate G8e)

D is the earlier of 7 days after step 8.6 or the owner's written sign-off after one full business cycle. Before D take RP-final (encrypted backups of `hd`, `id` and the old site) and restore each once on the scratch machine to prove it opens. Write the decision in `docs/architecture-isolation/decision-point.md`. The owner replies `DECISION D: GO` or `DECISION D: NO-GO`. **After D there is no rollback.** **Decides:** owner.

## Step 8.9 Finalise the ERPNext side, then move it

1. `NXERP_CUTOVER_DECISION_D=GO deploy/scripts/cutover.sh finalize-erp --yes --rp-final <RP-final path>` (refuses unless the path exists and its checksums verify; typed phrase).
2. Merge the branch `phase-8d/retire-legacy-sync` (legacy in-process sync code), deploy, re-run the Helpdesk and nxerp suites.
3. Move ERPNext (its own freeze, because it is finance data): announce a window; `cutover.sh freeze --yes`; `cutover.sh backup-source --yes --label rp-erp` (encrypt, copy off host); stop the old backend (it holds the alias `erp-backend`); `deploy/scripts/stack.sh erp up`; `deploy/scripts/cutover.sh move-erp --yes <RP-erp path>`; T1 to T6 on the production hosts; the accountant checks the trial balance and ten invoices on both sides; point `erp.<domain>` at the new stack; set `disable_user_pass_login` on `erp` only after an SSO test.
4. `docker compose -p <old project> stop` (do not delete). Keep it and RP-erp for 30 days.

**Pass:** ERP users sign in through `id`; the accountant signs off in writing. **Undo (until the old stack is deleted):** `docker compose -p <old project> start`, point `erp.<domain>` back, re-enter finance records made on the new site by hand (do not import them). **Decides:** accountant and owner.

## Step 8.10 Abort and rollback (any time before D)

See [isolation-rollback.md](isolation-rollback.md), row by row.

## Step 8.11 The shared layer: deploy, re-point, rebuild

Deploy the shared stack (`deploy/docker/compose/shared`) with freshly generated secrets, joined to the sync network (`SHARED_SYNC_NETWORK=nxerp-api`). After the clone and again after the ERP move:

```
deploy/scripts/shared.sh repoint <reviewed sources file>     # validates every owner's feed head; refuses otherwise
deploy/scripts/shared.sh rebuild-and-verify                  # rebuild --all, then reconcile --full; non-zero if drift is above 0
```

**Pass:** drift 0 and equal counts. The cursor of a re-pointed source starts from a rebuild, never from an old cursor; a source must never exist twice for the same app. **Undo:** point the sources back at the old site and rebuild. **Decides:** operator.

## Step 8.12 Switch on publication and shared reads, one at a time

`deploy/scripts/shared.sh cutover-order` prints the safe order. First `nxerp_shared_publish` on each owner site; wait for lag under 60 seconds and drift 0; only then `nxerp_shared_read` on Helpdesk. **Undo, in this order:** unset `nxerp_shared_read` (Helpdesk is back on its own data), then `nxerp_shared_publish`; rebuild the shared layer.

## Step 8.13 Turn on the alerts and test them

Rules: `deploy/env/shared/alerts.example.yaml` (lag above 300 s, any dead letter, drift above 0 on two consecutive runs, projector login failure, no successful pull for 15 minutes) plus backup age. Stop the projector for 10 minutes and watch the lag alert fire; start it again. **Undo:** `deploy/scripts/shared.sh start projector`.

## Workflows

`.github/workflows/deploy-staging.yml` and `deploy-production.yml` have a `stack` input (`default`, `id`, `erp`, `hd`, `db`, `edge`) that runs `deploy/scripts/stack.sh` on the host for the isolated stacks; `default` is today's behaviour. **No workflow has run on GitHub**, with or without the input; the host, registry package, Environments and secrets do not exist yet. Until they do, run the commands above by hand on the host.
