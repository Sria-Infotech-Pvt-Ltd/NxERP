# Shared read layer: which job runs when, and what it reports

All jobs run in the shared stack (`deploy/docker/compose/shared`), outside every owner. None reads an owner's database or writes an owner:
they use the owners' feed APIs ([feed-api-v1.md](../architecture/feed-api-v1.md)) and write only the shared database. Day-to-day
actions are in [the recovery runbook](../runbooks/shared-layer-recovery.md).

| Job | Where | When | What it does | Expected result |
| --- | --- | --- | --- | --- |
| Projector | service `shared-projector` | continuously, polling every 2 s while idle | pulls each owner's events after its cursor, applies them with the version rule and the cursor in one transaction, then acknowledges | `lag_seconds` under 60 at the 95th percentile; `dead_letters` 0; `gap` 0 |
| Recent scan | service `shared-reconciler` | every hour | compares the owner's digest of documents modified since the last scan (minus 5 minutes) with the shared rows: missing and stale | `drift` 0 |
| Full compare | service `shared-reconciler` | every night at 03:00 UTC (`SHARED_RECONCILE_FULL_HOUR`) | compares every owner id and payload hash with every shared row: missing, extra, stale, hash mismatch | `drift` 0; a few repairs are normal only after an outage |
| Rebuild | by hand: `shared.sh rebuild` | first fill, disaster recovery, after a sequence gap | snapshot, tombstone what the owner no longer has, replay from the recorded head, full compare | `drift_after` 0 |
| Owner's relay and prune | on each owner site, not here | relay every minute, prune daily (Phase 3) | gives committed outbox rows a sequence number; removes acknowledged rows older than 14 days | `head.pending_count` near 0 |

The reconciler is a separate process from the projector: a long compare never delays event application, it holds no long database locks (short transactions per repair batch) and writes
through the same account and the same version rule.

## The reports

| Report | How to read it | Success |
| --- | --- | --- |
| `shared.sh status` | rows and tombstones per entity table, each source's cursor and state (`live`, `gap`, `rebuilding`), unresolved dead letters, metrics | cursors `live`, dead letters 0 |
| `shared.sh reconcile --full` | JSON: per source and entity `owner`, `shared`, `missing`, `extra`, `stale`, `hash_mismatch`, `ahead`, `repaired`, `refused` and the first 50 ids of each category; `status` per source | `drift` 0, `refused` 0, every source `ok` |
| `shared.sh rebuild` | JSON: per source `start_seq`, `snapshot_rows` and `tombstoned` per entity, `replayed`, `dead_letters`, `drift_after` | `drift_after` 0 |

Reports hold ids and counts only. Metrics (`sync_metric`): `applied`, `skipped_old`, `dead_letters`, `errors` (counters), `lag_seconds`, `last_success`, `gap`, `source_stopped`, `reconcile_drift`,
`last_reconcile_at`, `rebuilt_rows` (gauges). Suggested alerts: `lag_seconds` above 300, `gap` 1, `source_stopped` 1, `dead_letters` rising, `reconcile_drift` above 0 for two runs in a row.

## The live audit

`scripts/shared_audit.sh all` (or `ports`, `accounts`, `api`, `pipeline`, `sample`, `tests`) checks a running stack and prints `PASS`, `FAIL` or `INFO` lines: no published host port; the exact grant matrix and, as each app account itself, what it
cannot do; no sensitive column names; the live Read API with a real token (401, 403, 405, field denial); no dead letters, gap or stopped source and `reconcile --full` drift 0; 20 random rows per entity equal to the owner's own feed.
It needs a token file `deploy/env/shared/secrets/read-helpdesk.token`. Do not run `shared.sh test` against a stack that is carrying a soak or real data: the database tests reuse the stack's own database and empty the entity tables.
