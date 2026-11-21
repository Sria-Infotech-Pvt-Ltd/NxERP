# Shared read layer: symptoms and actions

The shared read database is derived: it is never the source of truth, nothing is lost if it is damaged, and it can always be rebuilt from the
owners (see "Rebuild" below). Every command is run through `deploy/scripts/shared.sh` on the host that runs the shared stack; none of them
touches an owner's database. Logs and metrics carry ids and counts, never payload values.

Where to look first:

```
deploy/scripts/shared.sh status      # rows per entity table, cursors (state live or gap), unresolved dead letters, metrics
docker compose -p nxerp-shared logs --tail 100 shared-projector
```

Metrics (rows of `sync_metric`, also shown by `status`): `lag_seconds`, `last_success` (unix time), `applied`, `skipped_old`,
`dead_letters`, `errors`, `gap` (1 = a source is stopped on a sequence gap), `source_stopped` (1 = the owner rejected the projector).

## Lag grows

Symptom: `lag_seconds` above 300 for more than a few minutes, or `last_success` is old.

1. `status`: is the source's cursor moving (`last_seq` increasing)? Is `source_stopped` 1 or `gap` 1? Follow those sections if so.
2. The projector log says `FeedUnavailable ... retrying in N s`: the owner or the network is down or slow. The projector backs off (1, 2, 4 ... 60 s) and
   catches up on its own; nothing is lost because the owner keeps the events (acknowledged events are kept 14 days).
3. The projector log says nothing and the cursor is still: is the owner's relay running? On the owner site, `feed.head` shows `pending_count` (rows waiting for a
   sequence number) and `oldest_pending_age_seconds`. A growing `pending_count` means the owner's scheduler or queue worker is down, not the projector.
4. The projector container is down: `docker compose -p nxerp-shared up -d shared-projector`. It resumes from its cursor; run `reconcile --recent` afterwards if it was down for hours.

## A source is stopped on a gap (`gap` = 1, cursor state `gap`)

Symptom: the log says `sequence gap, expected seq N and got M`, or `the owner's feed head is behind our cursor`. The projector applied everything before the gap and stopped that source;
other sources continue. It never skips past an unapplied event.

Likely causes: the owner's outbox was pruned past our cursor (the projector was down longer than the retention, 14 days), the owner was restored from a backup, or its outbox table was emptied.

Action: rebuild that source (one command, no manual step): `deploy/scripts/shared.sh rebuild --source <app_key>`. It snapshots every entity of the source, replays the events after
the snapshot and puts the cursor back to live. Then `reconcile --full` should report drift 0.

## Dead letters

Symptom: `status` shows `unresolved_dead_letters` above 0, or the `dead_letters` counter rises. The stream is not blocked: the event was set aside with its reason and the cursor moved on.

```
docker compose -p nxerp-shared exec shared-db mariadb -u root -p -e \
  "SELECT id, seq, entity_type, entity_id, error_text, attempts FROM nxerp_shared.sync_dead_letter WHERE resolved_at IS NULL"
```

`error_text` says why. A dead letter stores the event's envelope and the NAMES of the payload fields, never their values.

| Reason | Meaning | Action |
| --- | --- | --- |
| `payload field 'x' is not in the allow-list` | the owner sent a field the contract does not list | a contract or capture bug on the owner: fix it there; then `rebuild` that source (or `reconcile --full`) restores the entity |
| `contract_version N is not the current M` | owner and shared service run different contract versions | deploy the same contract files on both; the entity is repaired by the next `reconcile --full` |
| `source_app ... is not the owner` | an event for an entity the sending app does not own | investigate the owner's configuration; never edit the shared tables by hand |
| `... longer than its column` or `DataError after 5 attempts` | a value does not fit its column | widen `max_length` in the contract (a reviewed change) and add a migration |

After the cause is fixed, mark the rows handled: `UPDATE sync_dead_letter SET resolved_at = NOW(6) WHERE id IN (...)` (a human decision, as the migrate account). Resolved dead letters are kept 30 days.

## The owner rejects the projector (`source_stopped` = 1)

Symptom: `the feed answered HTTP 401` or `403`, `source ... is stopped`. A wrong or revoked key does not spin: the source is retried only every five minutes.

Action: on the owner site check the feed service user is enabled, holds the role `NXERP Shared Feed Reader` and that its API key and secret match the projector's key file
(`SHARED_SECRETS_DIR`, one line `api_key:api_secret`). After the fix the projector recovers by itself within five minutes, or restart it.

## The database is unreachable

Symptom: `TransientDbError` in the log. The projector rolls the batch back, never acknowledges it and retries with backoff. Nothing needs doing once the database is back.
If the database volume is lost, start the stack (`shared.sh up`) and `rebuild --all`: the shared layer is rebuilt entirely from the owners.

## Reconcile: drift between an owner and the shared layer

The outbox cannot see a change made without a document event (`frappe.db.set_value`, raw SQL, a bulk insert), so the reconciler compares the shared layer with each owner's feed and repairs the
difference: always owner to shared, never the reverse. It runs by itself (the `shared-reconciler` service, see [shared-layer-jobs.md](../architecture-isolation/shared-layer-jobs.md)); run it by hand after an
outage or when you suspect drift:

```
deploy/scripts/shared.sh reconcile --recent      # documents modified since the last scan (minus 5 minutes): missing and stale rows
deploy/scripts/shared.sh reconcile --full        # every id and payload hash: also extra rows and same-stamp changes
```

The output is one JSON report (counts and ids, never values), for example: `{"mode": "full", "drift": 1, "repaired": 1, "refused": 0, "sources": {"nxerp": {"status": "ok", "entities": {"customer": {"owner": 120,
"shared": 120, "missing": 0, "extra": 0, "stale": 0, "hash_mismatch": 1, "ahead": 0, "repaired": 1, "refused": 0, "ids": {"hash_mismatch": ["CUST-0007"]}}}}}}`.

| Category | Meaning | Repair |
| --- | --- | --- |
| `missing` | the owner has it, the shared layer has no live row | copied from the owner |
| `extra` | the shared layer has a live row the owner no longer has | tombstoned (full compare only) |
| `stale` | the owner's version stamp is newer than ours | copied from the owner |
| `hash_mismatch` | same stamp, different content: a change made without an event | copied from the owner |
| `ahead` | our stamp is newer than the owner's | reported only, never repaired: look at the owner's clock and its recent restores |

Healthy: `drift` 0, `refused` 0, every source `ok`. A few `stale` or `missing` rows are normal only after an outage; many `hash_mismatch` rows point at a code path that writes without events (find it:
the reconciler is a safety net, not the design).

| Report says | Action |
| --- | --- |
| `status` `unreachable` or `rejected` for a source | that source was skipped and none of its rows were touched (an unreachable owner is never read as "everything deleted"); see the source sections above |
| `refused` above 0 | the owner returned a field outside the contract for those ids; nothing was written. Fix the owner's projection or the contract (a reviewed change); never edit the shared tables |
| the run fails with `HashFunctionMismatch` | owner and shared service hash payloads differently (almost every row with equal stamps differs). Both must run the same `nxerp/shared/payload.py` and contracts: check both run the same release. Nothing was repaired |
| drift keeps coming back for the same ids | a writer bypasses the outbox for that entity: find it and fix it at the source |

## Rebuild: one command for a first fill and for disaster recovery

```
deploy/scripts/shared.sh rebuild --source nxerp        # one owner
deploy/scripts/shared.sh rebuild --all
```

What it does: marks the source `rebuilding` (the projector leaves it alone), waits up to 90 seconds for the owner's relay, records the owner's head as `start_seq`, streams a snapshot of every entity
the feed serves, tombstones rows the owner no longer has, sets the cursor to `start_seq`, replays the events after it (changes made while it ran arrive here) and finishes with a full compare. The report
has `snapshot_rows` and `tombstoned` per entity, `replayed`, `dead_letters` and `drift_after`; success is `drift_after` 0.

- **A first fill** and **a lost database** are the same thing: `shared.sh up` (or `migrate`) creates the empty tables, then `rebuild --all`. There is no other step.
- **Interrupted** (the owner went down mid-way, the command was stopped): the source stays `rebuilding`; run the same command again. Everything it writes is idempotent.
- **Read API during a rebuild**: it keeps serving what is there; rows appear as the snapshot streams in. Plan a rebuild outside peak hours for a large layer.
- **Cursor behind the owner** after an owner restore: `rebuild --source <app_key>` (the source is stopped on a gap until then).

## Re-point the sources to new owner sites, rebuild, and the order of switching on (Phase 8E)

Used at the cutover (after the Helpdesk clone, and again after the ERP move). The shared layer is derived: it is **rebuilt, never migrated or restored**.

1. **Re-point.** Write the new sources file for review (one entry per app, `base_url`, `key_file`, optional `host_header`; `https` only on a real host). Then:
   `deploy/scripts/shared.sh repoint <reviewed file>`.
   It checks the candidate in a one-shot container first (it must parse, name each app once, and every owner's feed head must answer) and refuses otherwise, changing nothing. Only then does it stop the projector, keep the old file as `sources.json.bak.<time>` next to it and put the new one in place. A re-point never leaves two sources for the same app. **Undo:** copy the `.bak` file back, then step 2.
2. **Rebuild and verify.** `deploy/scripts/shared.sh rebuild-and-verify` rebuilds every source from its owner (snapshot, then replay; the cursor of a re-pointed source starts from this rebuild, never from an old cursor) and then reconciles in full. It exits non-zero unless drift is 0 everywhere, and does not start the projector. On success: `deploy/scripts/shared.sh start projector`. **Undo:** restore the previous sources file and run it again.
3. **Switch on, in this order** (`deploy/scripts/shared.sh cutover-order` prints it): `nxerp_shared_publish` on each owner; wait for lag under 60 seconds and drift 0; only then `nxerp_shared_read` on Helpdesk.
4. **Roll back, in this order:** unset `nxerp_shared_read` (Helpdesk is back on its own data), then `nxerp_shared_publish` on the owners; rebuild the shared layer.

**Metrics and alerts.** The Read API's internal `/v1/metrics?format=text` (or `Accept: text/plain`) exposes `outbox_lag_seconds`, `outbox_pending`, `projector_errors`, `dead_letters`, `reconcile_drift`, `rebuild_age_seconds`, `read_api_requests` and `read_api_denied` (JSON stays the default, Helpdesk reads it). The rules are in `deploy/env/shared/alerts.example.yaml`: lag above 300 s, any dead letter, drift above 0 on two consecutive runs, projector login failure, no successful pull for 15 minutes. The endpoint needs a valid token and is on the internal network only; alert text carries counts and source names, never values.
