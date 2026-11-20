# Phase 8: what the human does (production migration, cutover, rollback and operations)

The ten steps of the blueprint's Phase 8 item 9, in order, with their commands. Replace `<...>`. Secrets appear as `<PLACEHOLDER>`: generate them with
`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`, keep them in the password manager and never paste them into a chat, a ticket or a shell
history line. Claude Code (or an operator) runs the commands; the owner decides at the gates. The full text with pass and stop conditions is
`docs/runbooks/isolation-cutover.md`; the way back is `docs/runbooks/isolation-rollback.md`.

Records to fill: [rehearsal-1.md](rehearsal-1.md), [rehearsal-2.md](rehearsal-2.md), [decision-point.md](decision-point.md).

## Step 8.1 Build the rehearsal environment (scratch machine)

```
deploy/scripts/stack.sh db up
docker network create nxerp-api
for s in id hd; do deploy/scripts/stack.sh $s create-site; deploy/scripts/stack.sh $s up; done
deploy/scripts/stack.sh edge up
export NXERP_CUTOVER_SOURCE_PROJECT=<scratch project> NXERP_CUTOVER_SOURCE_SITE=<scratch site>
```

Restore the production backup copy as the source and neutralise it (mute emails, disable scheduler, Email Accounts and Webhooks). **Undo:** `NXERP_ALLOW_DESTROY=1 deploy/scripts/stack.sh <stack> down -v` (rehearsal only).

## Step 8.2 Rehearse the whole cutover, twice

```
deploy/scripts/stack.sh hd bench set-config nxerp_cutover_allowed 1
deploy/scripts/stack.sh id bench set-config nxerp_cutover_allowed 1
deploy/scripts/cutover.sh freeze --yes
deploy/scripts/cutover.sh backup-source --yes
deploy/scripts/cutover.sh clone-hd --yes <RP0 path>
deploy/scripts/cutover.sh build-id --yes
deploy/scripts/cutover.sh reconcile
deploy/scripts/cutover.sh delta-export --since <T0> --yes
deploy/scripts/cutover.sh delta-import --yes <bundle>
deploy/scripts/cutover.sh unfreeze --yes --restore-email
```

Write start and end times in the rehearsal records. **Pass rule:** two consecutive runs with PASS, no manual fixes, a freeze time you accept (2 hours).

## Step 8.3 Prepare the production window (T-7 days to T-1 day)

Announce the window; lower the DNS TTL of `hd.<domain>` and the old host to 300 seconds one day before; `df -h`; rerun the restore drill on the newest production backup; create the production stacks (sites `id` and `hd` only); attach the old site as the interim ERP app:

```
docker compose -p <old project> -f <old compose file> -f deploy/docker/compose/isolated/legacy-erp.override.yaml up -d backend
deploy/scripts/cutover.sh preflight
```

## Step 8.4 Cutover day: freeze, back up, build (gate G8b: reply `GO FREEZE`)

```
deploy/scripts/shared.sh stop projector
deploy/scripts/cutover.sh freeze --yes
deploy/scripts/cutover.sh backup-source --yes
deploy/scripts/stack.sh hd bench set-config nxerp_cutover_allowed 1
deploy/scripts/stack.sh id bench set-config nxerp_cutover_allowed 1
deploy/scripts/cutover.sh clone-hd --yes <RP0 path>
deploy/scripts/cutover.sh build-id --yes
deploy/scripts/cutover.sh reconcile
```

On FAIL stop and `deploy/scripts/cutover.sh unfreeze --yes --restore-email`.

## Step 8.5 Canary: agents only (gate G8c: reply `CANARY OK` or the problem)

Agents sign in at `https://id.<domain>`, open five tickets, reply to an internal test ticket, open an ERP customer, compare 10 tickets with the old site. The support lead signs off in writing.

## Step 8.6 Open to customers (gate G8d: reply `GO OPEN TO CUSTOMERS`)

```
deploy/scripts/stack.sh hd bench enable-scheduler
# enable ONE mailbox poller on hd; put NXERP_LEGACY_HOST=<old host> and NXERP_LEGACY_SITE=<old site> in deploy/env/isolated/edge.env
deploy/scripts/stack.sh edge up
curl -sI https://<old host>/helpdesk/my-tickets
```

Expected: `301` with `Location: https://hd.<domain>/helpdesk/my-tickets`; one test email makes one ticket on `hd` only.

## Step 8.7 Watch for 48 hours

Check grant drift, Webhook Request Log failures, gate denials, failed database authentications, backup age and the shared-layer alerts. Daily encrypted backup:

```
deploy/scripts/stack.sh hd backup
deploy/scripts/stack.sh id backup
```

## Step 8.8 Decision point D (gate G8e: reply `DECISION D: GO` or `DECISION D: NO-GO`)

Take RP-final (encrypted backups of `hd`, `id` and the old site), restore each once on the scratch machine, then fill `decision-point.md`. After D there is no rollback.

## Step 8.9 Finalise the ERPNext side, then move it

```
NXERP_CUTOVER_DECISION_D=GO deploy/scripts/cutover.sh finalize-erp --yes --rp-final <RP-final path>
# merge phase-8d/retire-legacy-sync, deploy, re-run the Helpdesk and nxerp suites
deploy/scripts/cutover.sh freeze --yes
deploy/scripts/cutover.sh backup-source --yes --label rp-erp
docker compose -p <old project> stop backend
deploy/scripts/stack.sh erp up
deploy/scripts/cutover.sh move-erp --yes <RP-erp path>
docker compose -p <old project> stop
```

The accountant checks the trial balance and ten invoices on both sides, then `erp.<domain>` is pointed at the new stack.

## Step 8.10 Abort and rollback (any time before D)

Follow the rollback table in `docs/runbooks/isolation-rollback.md`. Short form: before the canary, `unfreeze --restore-email`; after it, `delta-export` from `hd`, `delta-import` into the source, re-enable the source mailbox, point the edge back, `unfreeze`.

## Then (operations, steps 8.11 to 8.13)

```
deploy/scripts/shared.sh repoint <reviewed sources file>
deploy/scripts/shared.sh rebuild-and-verify
deploy/scripts/shared.sh cutover-order        # prints: publish on owners, wait lag under 60 s and drift 0, then read on Helpdesk
```

Then turn on the alerts (`deploy/env/shared/alerts.example.yaml`) and stop the projector for 10 minutes to see the lag alert fire.
