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

## Rebuild and reconcile

See the sections added with the reconciler and rebuild (work package 4C): when to run `reconcile --recent`, `reconcile --full` and `rebuild`, how often each runs, and what the report says.
