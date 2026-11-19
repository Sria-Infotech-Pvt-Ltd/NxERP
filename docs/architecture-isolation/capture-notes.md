# Capture notes: what the outbox hooks see and what they miss

The capture hooks (`nxerp/shared/capture.py`) write one outbox row per shared-entity change, in the same database
transaction as the change. They are generated from the active ownership contracts and do nothing unless the site sets
`nxerp_shared_publish`. This page records what they catch, what they cannot, and the behaviours found while testing
them. Evidence for the event table is in [spike-publication.md](spike-publication.md) (run on Frappe 16.53.0); the tests
are `nxerp/tests/test_outbox.py`.

## Turning it on and off

| Site config key | Meaning |
| --- | --- |
| `nxerp_shared_publish` | unset or `0`: every handler returns at its first line (behaviour identical to today). `1`: capture is on |
| `nxerp_shared_publish_strict` | `1`: a contract that cannot project its document raises (use in tests and CI). Unset: it writes a `resync` event and logs |

Changing the contracts (hooks are generated at import): run `bench clear-cache` (in the spike this was enough, even for a
running web process; the safe deploy procedure is still `bench migrate`, clear the cache, restart workers). Changing
`scheduler_events` needs `bench migrate`.

## What fires, and what the capture does about it

| Operation | Events Frappe fires | Capture |
| --- | --- | --- |
| `doc.insert()`, `doc.save()`, `doc.submit()` | ends with `on_change` | one `upsert` |
| `doc.db_set(field, value)` | `on_change` only | one `upsert` (the payload is rebuilt from the document) |
| `frappe.rename_doc()` | `before_rename`, `after_rename`; **no `on_change`** | `delete` of the old id, then `upsert` of the new id |
| `frappe.delete_doc()` | `on_trash`, then `on_change` **with `flags.in_delete`**, then `after_delete` | one `delete`, written from `on_trash`; the `on_change` during delete is ignored |
| `frappe.db.set_value()` | none | **not captured** |
| `frappe.db.delete()` | none | **not captured** |
| raw SQL, `frappe.db.bulk_insert()` | none | **not captured** |

### The known gap

`frappe.db.set_value`, `frappe.db.delete`, raw SQL and bulk inserts change data without any document event, so no outbox
row exists for them. This is by design of Frappe and cannot be closed by a hook. The Phase 4 reconciler compares the
owner's rows with the shared copy (hourly scan of recently modified rows, nightly full compare of ids and payload hashes)
and repairs what the outbox missed. Until Phase 4, a change made one of these ways is not published.

`Deleted Document` is not a substitute: Frappe writes a row for `delete_doc` only (none for `delete_permanently`, none
for raw deletes) and has no retention setting for it.

## Behaviours found while testing

1. **A rename can produce an extra upsert first.** ERPNext's own `Customer.after_rename` runs `self.db_set("customer_name",
   newdn)` (when the site names customers by name), which fires `on_change`. A rename of a Customer therefore writes
   `upsert(new id)`, then `delete(old id)`, then `upsert(new id)`. The sequence is harmless: the last event for the new id is an
   upsert, and the projector applies events by version stamp.
2. **A delete's version stamp is the time of the delete.** `delete` and the upsert after a rename use the current time
   as `source_modified`, so they are newer than any earlier upsert of that id. An ordinary `upsert` carries the document's
   own `modified`.
3. **Capture runs only where the owner app is installed.** `Contact` exists on every Frappe site, but its contract is
   owned by `erpnext`; on the Helpdesk site (no ERPNext) its changes are not captured. The same applies to `Company` and
   `HD Ticket`.
4. **Nothing is captured during app installation** (`frappe.flags.in_install`): the outbox table may not exist yet.
5. **Derived fields.** `contact.customer_id`, `email`, `phone` and the ticket's `opened_at`, `resolved_at`, `assignee_user_id`
   are computed from child tables or related records (`nxerp/shared/digest.py`). A field marked `verify` in the contract
   whose source is not in the DocType (today `org_unit.disabled`) is shared as empty, not as an error; any other missing
   source field is a contract mismatch.
6. **The payload is stored as canonical JSON** (keys sorted, no spaces), so its hash is stable. Key order in the stored
   text is therefore not the contract order.

## Failure policy

| Failure | What happens |
| --- | --- |
| The outbox insert fails (database error) | the error propagates and the business change fails with it: both or neither |
| The payload cannot be built (a contract mismatch) | outside strict mode: a `resync` event (entity id only) and one log line with the entity id and the error class name, never field values; in strict mode: the error is raised |
| The request or job fails after the save | the transaction rolls back and the outbox row disappears with the change (checked by test, and over HTTP in the spike) |

A web request commits only for POST, PUT, PATCH and DELETE; a GET that changes data is rolled back together with its outbox
rows, which keeps the guarantee intact.

## Measured cost

One extra row per save adds about 0.6 ms to a Customer save (about 2%, within run-to-run noise): see the spike for the
measurement and the final report for the figure with the real capture code.
