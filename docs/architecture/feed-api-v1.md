# Feed API v1

How the shared read layer's projector (Phase 4) reads an owner's changes. Each owner site (NXERP, Helpdesk) publishes its
own feed from its own database; the projector pulls it, in order, over HTTPS. All examples use fake data.

Everything here is **off** unless the site config has `nxerp_shared_publish` set: every method then returns an empty result
(and `ack` changes nothing). Turning it on starts the capture hooks, the relay and the prune job
(see `docs/architecture-isolation/capture-notes.md`).

## Calling it

- Base: `https://<owner site>/api/method/nxerp.shared.feed.<method>`
- Authentication: a dedicated **service user** with the role `NXERP Shared Feed Reader` (Frappe makes a user with only this role a Website User; token authentication works for it, checked over HTTP), using Frappe's API key and secret:
  `Authorization: token <api_key>:<api_secret>`. The role has no desk access. The key and secret belong in the projector's
  own secret store, never in an app's `site_config.json`.
- Replies are JSON; the result is under `"message"`.
- Reads accept `GET`. **`ack` is a `POST`**: Frappe commits only POST, PUT, PATCH and DELETE requests, so an acknowledgement sent
  as a GET would answer 200 and be rolled back.
- No method accepts SQL, a DocType name or a field name. `entity_type` selects an ownership contract
  (`apps/nxerp_platform/nxerp/shared/contracts/`); everything returned is built from that contract's fields only.

## Methods

| Method | HTTP | Arguments | Returns |
| --- | --- | --- | --- |
| `head` | GET | none | where the feed stands |
| `pull` | GET | `after_seq` (default 0), `limit` (1 to 1000, default 1000) | events with `seq` greater than `after_seq`, in order |
| `ack` | POST | `through_seq` | marks events up to it acknowledged |
| `digest` | GET | `entity_type`, `modified_since` (optional), `after_id` (optional), `limit` (1 to 1000, default 500) | `(entity_id, source_modified, deleted, payload_hash)` of live documents |
| `snapshot` | GET | `entity_type`, `after_id` (optional), `limit` (1 to 1000, default 500) | the contract payload of live documents |
| `snapshot_by_ids` | GET or POST | `entity_type`, `ids` (a list, or a JSON list as text; at most 1000 ids of at most 140 characters) | the payload of the ids that exist, and the ids that do not |

### head

```
GET /api/method/nxerp.shared.feed.head
```
```json
{"message": {"max_seq": 18432, "pending_count": 3, "oldest_pending_age_seconds": 41, "acked_through": 18400}}
```

`pending_count` is rows still waiting for a sequence number; `oldest_pending_age_seconds` is the age of the oldest row that is
not yet acknowledged (the lag the projector should alert on).

### pull

```
GET /api/method/nxerp.shared.feed.pull?after_seq=18430&limit=500
```
```json
{
  "message": {
    "events": [
      {
        "event_id": "019a7c1e-5b2f-7c10-8f3a-0d4e2b6a9c11",
        "seq": 18431,
        "source_app": "erpnext",
        "entity_type": "customer",
        "entity_id": "Example Customer Ltd",
        "op": "upsert",
        "contract_version": 1,
        "source_modified": "2026-11-18 10:21:04.512311",
        "tenant_id": "ORG-001",
        "payload": {
          "customer_group": "Commercial",
          "customer_type": "Company",
          "disabled": 0,
          "display_name": "Example Customer Ltd",
          "primary_contact_id": null,
          "territory": "All Territories"
        }
      },
      {
        "event_id": "019a7c1e-6a07-7a52-9b0c-3c1d8e5f7a22",
        "seq": 18432,
        "source_app": "erpnext",
        "entity_type": "customer",
        "entity_id": "Old Example Ltd",
        "op": "delete",
        "contract_version": 1,
        "source_modified": "2026-11-18 10:22:10.004512",
        "tenant_id": "ORG-001",
        "payload": null
      }
    ],
    "next_seq": 18432
  }
}
```

Each event is the envelope in `apps/nxerp_platform/nxerp/shared/envelope_schema.json`. `op` is `upsert` (with a payload),
`delete` (no payload) or `resync` (no payload: re-read this entity with `snapshot_by_ids`, because its payload could not be
built). Only rows that already have a sequence number are returned, so events appear in a gap-free order. Ask again with
`after_seq` set to `next_seq`.

**Delivery is at least once.** Apply an event only if its version stamp `(source_modified, seq)` is newer than the row you
hold; replays are then harmless.

### ack

```
POST /api/method/nxerp.shared.feed.ack     through_seq=18432
```
```json
{"message": {"acked_through": 18432, "acked": 2}}
```

Marks every sequenced, unacknowledged event with `seq` up to `through_seq` as acknowledged. Sending it again returns
`"acked": 0`; an older `through_seq` never lowers `acked_through`; a `through_seq` beyond the head of the feed is a 422.
Acknowledged rows are kept for `nxerp_outbox_retention_days` (default 14) and then pruned daily; unacknowledged rows are
never pruned.

### digest

```
GET /api/method/nxerp.shared.feed.digest?entity_type=customer&modified_since=2026-11-18 08:00:00&limit=2
```
```json
{
  "message": {
    "items": [
      {"entity_id": "Example Customer Ltd", "source_modified": "2026-11-18 10:21:04.512311", "deleted": 0, "payload_hash": "9f2c...e1"},
      {"entity_id": "Example Partner Ltd", "source_modified": "2026-11-18 09:02:55.100000", "deleted": 0, "payload_hash": "3ab7...40"}
    ],
    "next_after_id": "Example Partner Ltd"
  }
}
```

Built from the live documents through the same projection the capture uses, so a hash here equals the hash of the payload
`snapshot` returns. `deleted` is always 0: a digest lists live documents, so a deletion is found by comparing the id lists (the
nightly full compare). `next_after_id` is the last name when the page is full, otherwise `null`; ask again with it as `after_id`.

### snapshot and snapshot_by_ids

```
GET /api/method/nxerp.shared.feed.snapshot?entity_type=customer&after_id=&limit=500
GET /api/method/nxerp.shared.feed.snapshot_by_ids?entity_type=customer&ids=["Example Customer Ltd","No Such Customer"]
```
```json
{
  "message": {
    "items": [
      {"entity_id": "Example Customer Ltd", "source_modified": "2026-11-18 10:21:04.512311", "payload": {"customer_group": "Commercial", "customer_type": "Company", "disabled": 0, "display_name": "Example Customer Ltd", "primary_contact_id": null, "territory": "All Territories"}}
    ],
    "missing": ["No Such Customer"]
  }
}
```

(`snapshot` returns `items` and `next_after_id`; `snapshot_by_ids` returns `items` and `missing`.)

## Errors

| HTTP | When | Notes |
| --- | --- | --- |
| 401 | the API key is known but the secret is wrong | answered by Frappe |
| 403 | no token, the caller lacks the role `NXERP Shared Feed Reader`, or the wrong HTTP method is used (`ack` sent as a GET changes nothing) | no detail is given |
| 422 | a bad argument: not an integer, out of range, an unknown or planned `entity_type`, `ids` not a list or over 1000, a bad date, `through_seq` beyond the head | `FeedError`; the message names the argument, never a table or field |
| 500 | a live document could not be projected through its contract | generic message; the entity id and error class are logged, never values |
| 503 | the relay lock is held (only if the relay is called with `raise_if_busy`; the scheduled run just does nothing) | `RelayBusy` |

## Limits

| What | Limit |
| --- | --- |
| events per `pull` | 1000 |
| items per `digest`, `snapshot` page | 1000 (default 500) |
| ids per `snapshot_by_ids` | 1000, each at most 140 characters |
| relay batch | 1000 rows per transaction; run every minute |
| lag target | 60 seconds at the 95th percentile (assumption A11) |
| retention of acknowledged events | 14 days by default |

## Operating notes

- The relay runs from the scheduler (`* * * * *`) and prune daily. Adding or changing these schedules needs `bench migrate`.
  The stack has one worker for every queue, so the relay works in bounded batches and a long job elsewhere delays it.
- A site's database login must be usable from the scheduler and worker containers, not only from the web container
  (`bench new-site --mariadb-user-host-login-scope`), or the relay never runs.
- A web request that fails after a change leaves no outbox row; a change made with `frappe.db.set_value`, `frappe.db.delete`,
  raw SQL or `bulk_insert` produces no event at all (the Phase 4 reconciler repairs those).
