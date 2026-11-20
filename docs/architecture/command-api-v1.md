# Command API v1

The only way another app changes a shared entity (ADR-009). It runs on the OWNER's site (today: NXERP, the owner of `customer` and `contact`),
on the owner's own DocType named in the contract, as a real person on that site. The caller never writes the owner's tables and cannot name
a DocType or a field that is not in the contract. Code: `apps/nxerp_platform/nxerp/shared/command.py`. Tests: `nxerp/tests/test_commands.py`.

## Call

```
POST /api/method/nxerp.shared.command.apply
Authorization: token <api_key>:<api_secret>        (a service user with the role "NXERP Command Caller")
Content-Type: application/x-www-form-urlencoded    (or JSON)

entity_type=customer
entity_id=CUST-0001
command=request_change                    (or the full name customer.request_change)
fields={"customer_group": "Commercial", "territory": "North"}     (a JSON object)
expected_version=2026-11-20 10:15:00.123456      (optional: the source_modified you read)
idempotency_key=ticket-42-edit-7f3a9c1e          (required, 8 to 140 characters from A-Z a-z 0-9 : _ . | @ + -)
acting_user=agent@example.test                   (a person on the owner's site)
```

Success (HTTP 200): `{"message": {"ok": true, "source_modified": "2026-11-20 10:16:02.456789"}}`. Use `source_modified` as `min_version` on the Read API to wait for
the change to appear in the shared layer.

A repeat with the same `idempotency_key` returns the first answer unchanged and changes nothing (keys are kept 24 hours). The same key for a different
entity, command or caller is a 409.

## Errors

The envelope is `{"message": {"error": "<code>", "message": "<text>"}}`; the HTTP status is the one in the table. No error body holds a stack trace, a SQL text or a submitted value.
Any failure rolls back the document change AND the idempotency row, so a retry with the same key after any 5xx is safe.

| HTTP | `error` | When |
| --- | --- | --- |
| 403 | `forbidden` | the service user lacks the role, is not mapped to an app, or its app is not in the command's `callers`; or the acting user has no permission on the record |
| 403 | `acting_user_invalid` | the acting user is missing, disabled, empty, Administrator or Guest |
| 403 | `acting_user_forbidden` | the acting user does not hold the command's `needs_role` |
| 404 | `unknown_command` | no such entity or command in an active contract, or this site does not own the entity |
| 404 | `not_found` | no record with that id |
| 409 | `version_conflict` | `expected_version` differs from the record's `modified` |
| 409 | `idempotency_key_reused` / `in_progress` | the key belongs to another request / an identical request is still running |
| 422 | `field_not_writable` | a field is not in the command's `writable_fields` (ids, system fields and S3 fields never are) |
| 422 | `bad_request`, `bad_idempotency_key`, `validation_failed` | malformed input; or the owner's own validation refused the change (for example an unknown Territory) |
| 429 | `rate_limited` | more than 600 calls a minute for one service user |
| 503 | `unavailable` | anything unexpected; nothing was stored |

## What the contracts say (today)

| Command | Writable fields | Callers | Acting user needs |
| --- | --- | --- | --- |
| `customer.request_change` | `customer_group`, `territory` | `helpdesk` | `NXERP Access: ERPNext` (placeholder: owner to confirm) |
| `contact.update_contact` | `full_name`, `email`, `phone` | `helpdesk` | `NXERP Access: ERPNext` (placeholder: owner to confirm) |

`contact` `email` and `phone` change the contact's primary email and phone rows (a row is added when there is none); `full_name` is split into first and last name.
A name is never written to the id or to a system field. Adding a command or a caller is a contract change (`contract_version` is bumped, `scripts/check_contracts.py`
rule C9 checks the callers).

## How it is switched on (off by default)

1. The role `NXERP Command Caller` exists (patch `create_command_role`).
2. The owner's site config maps each calling service user to an app key: `nxerp_command_callers` = `{"helpdesk-commands@example.test": "helpdesk"}`. No mapping, no access.
3. The Phase 3 capture publishes the change (site config `nxerp_shared_publish`); the command code never publishes.

## Rate limit and retention

600 commands a minute per service user (a counter in the owner's Redis; if Redis cannot answer, work is not blocked and a warning is logged). `NXERP Command Log` rows
older than 24 hours are removed daily at 03:30 (scheduler cron `nxerp.shared.command.prune_log`).
