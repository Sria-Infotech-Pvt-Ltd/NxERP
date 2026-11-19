# Read API v1

The only way an app reads the shared read layer (ADR-009). Read-only, per-app tokens, field-level grants, one audit row per call.
Implemented in `nxerp/shared_service/readapi.py` (Werkzeug WSGI, served by gunicorn as service `shared-api`, port 8080, internal network only).

## Calls

All requests are `GET` with `Authorization: Bearer <credential_id>.<secret>`. Every other method is `405` with `Allow: GET`
(with or without a token). Writes go to the owner's command API, never here.

| Call | Meaning |
| --- | --- |
| `GET /v1/health` | no token; `{"status":"ok"}` when the database answers, `503` otherwise; not audited |
| `GET /v1/metrics` | token required; projector and API counters and gauges (numbers only) |
| `GET /v1/{entity}/{id}` | one row |
| `GET /v1/{entity}` | a page of rows, ordered by `entity_id` |

Entities are the contract names the token's app has a grant on (`customer`, `contact`, `org_unit`, ...). Planned or unknown entities are `404`.

Parameters: `fields=a,b` (default: all granted fields), `tenant=<id>` (only inside the grant), `limit` 1..200 (default 50), `after=<entity_id>`
(keyset paging: pass the previous page's `next_after`), `min_version=<source_modified>` (read-your-write, below).

Every response row carries `entity_id`, `tenant_id`, `source_modified`, `synced_at` plus the requested granted fields, and nothing else,
even if a view has more columns: the response is built from the contract's grant, not from the view.

```
GET /v1/customer/CUST-0001?fields=display_name,territory
200 {"data": {"entity_id": "CUST-0001", "tenant_id": "ORG-001", "display_name": "Example A", "territory": "North",
              "source_modified": "2026-11-18 10:00:00.000000", "synced_at": "2026-11-18 10:00:04.113902"}}

GET /v1/customer?limit=2
200 {"data": [ ... 2 rows ... ], "next_after": "CUST-0002"}      (next_after is null on the last page)
```

## Errors

Body `{"error": {"code": "...", "message": "..."}}`; never SQL, a trace, a table name or another tenant's data.

| HTTP | code | When |
| --- | --- | --- |
| 401 | `unauthorized` | no, malformed, wrong, expired or revoked token (`WWW-Authenticate: Bearer`); all look alike |
| 403 | `not_granted` | the app has no grant on this entity |
| 403 | `field_not_granted` | a requested field is outside the grant (or does not exist): an error, never an empty column |
| 403 | `tenant_not_granted` | `tenant` is not the grant's tenant |
| 404 | `unknown_entity`, `not_found` | no such entity; no such live row. A tombstone, another tenant's row and an unknown id are the same answer |
| 405 | `method_not_allowed` | anything but GET |
| 422 | `bad_parameter` | bad `limit`, `after`, `min_version` |
| 429 | `rate_limited` | per-token bucket (default 600/min, `SHARED_API_RATE_PER_MINUTE`); `Retry-After` seconds |
| 503 | `database_unavailable` | the shared database cannot be reached |
| 202 | (`{"status":"pending"}`) | `min_version` not reached after about 2 s |

## Read-your-write

After a command to the owner the caller knows the document's `modified` stamp. `?min_version=<that stamp>` makes the API wait up to
2 seconds for the projector, then answer `200`, or `202 {"status":"pending"}` if it has not arrived. Do not loop faster than once a second.

## Tokens

One token per consuming app, format `<12 hex id>.<64 hex secret>`, shown once when issued (`shared.sh tokens create --app <app>`
to a mode-600 file). The database keeps only a scrypt hash (n=2^14, r=8, p=1, own salt), verified in constant time; an unknown id costs the
same work as a wrong secret. Rotate with `tokens rotate --app <app> [--grace-hours N]`, revoke with `tokens revoke`. `tokens list`
shows ids, apps and dates only. Grants (`consumer_grant`) come from the contracts: `shared.sh grants show|sync`.

## Audit

Every call except `/v1/health` writes one `read_audit` row, denied calls included: time, app (`-` when unauthenticated), entity, id,
tenant, field names returned, row count, outcome, `X-Request-Id`, `X-Acting-User`, and a SHA-256 of the ids returned. Never a token and never a
row value. Rows are written in batches by a background thread so a read does not wait for its own audit; a database outage keeps them queued,
and a full queue drops the newest and logs an error. Retention 400 days (ASSUMPTION; a compliance owner decides).

## Advice to consumers

* **Caching:** cache by `entity_id` for at most 60 seconds, keyed with `source_modified`; for a screen that just changed something, use `min_version` instead of a longer wait.
* **Degradation:** on `503`, `429` or a timeout show what you have (a cached or own-database value, or "details unavailable") and carry on: the shared layer is derived and optional. Never block a ticket or an invoice on it, and never write back the value you read.
* **Tenants:** send `tenant` explicitly when you serve more than one.

## TLS

The service listens on plain HTTP inside the internal Docker network and publishes no host port. TLS is terminated in front of it
by the reverse proxy when a consumer outside that network is added (not needed for same-network consumers; a decision for the human
at go-live). Tokens must never travel over an untrusted network without TLS.

## Libraries available in the image (recorded 2026-11-19; no dependency is added)

The projector, the reconciler and the Read API run in the same application image as the apps, with its Python environment. They are
written to use only what that image already carries:

| Library | Version in the image | Used for |
| --- | --- | --- |
| Python | 3.14.8 | everything |
| PyMySQL | 1.1.2 (package metadata) | the shared database driver |
| Werkzeug | 3.1.9 | the Read API's request and response handling (WSGI) |
| gunicorn | 23.0.0 | serving the Read API |
| `hashlib.scrypt` (standard library) | built in | hashing app tokens |
| `urllib.request` (standard library) | built in | the projector's HTTP client for the owners' feeds |
| mysqlclient 2.2.7, requests 2.33.1 | present, not used by the shared service | |
| jsonschema | **not installed** | not used: envelopes and contracts are checked by the standard-library code in `nxerp/shared/registry.py` |

The shared service imports neither `frappe` nor any other app (ADR-005); it shares only the pure modules `nxerp/shared/registry.py`
and `nxerp/shared/payload.py` with the owners' side.
