# Phase 3A spike: how Frappe 16.53.0 behaves under the outbox design

Measured on 2026-11-19 on a throwaway bench: Frappe v16.53.0, ERPNext v16.52.1, Helpdesk 1.22.2, `nxerp` at the Phase 2 code, MariaDB 11.8, site `phase3.localhost` (fake data, created for this spike, scheduler off again afterwards). Every row below was **run**, not read from source; where the source was read to explain a result, that is said. Nothing here touched production. The spike code lived only inside the scratch bench and is not in the repository; API keys were generated inside the container and never printed.

**CONTRADICTION: none.** No result contradicts the blueprint (sections 2.6 and 2.9). Four results go beyond it and change what 3B and 3C must do; they are listed first.

## Recommendation

**Proceed with the default design: capture in `doc_events` `on_change`, plus `on_trash` for deletes and `after_rename` for renames.** The `before_commit` fallback is not needed. Evidence: (a) a handler's row commits with the document and disappears with it; (b) `on_change` fires for insert, save, submit and `doc.db_set`.

## What this changes in 3B and 3C

| # | Finding | Consequence |
| --- | --- | --- |
| 1 | A **GET request never commits**: Frappe commits only for POST, PUT, PATCH, DELETE (`sync_database` in `frappe/app.py`, read to explain the result) | `head`, `pull`, `digest`, `snapshot` are read-only GETs and fine. **`ack` must be a POST**, or its status change is rolled back while the call returns 200 |
| 2 | **Rename fires no `on_change`**, only `before_rename` and `after_rename`; **delete fires `on_change` with `flags.in_delete`**, after `on_trash` | Register `after_rename` (rename = delete old id + upsert new id); emit deletes from `on_trash`; `on_change` must ignore `in_delete` |
| 3 | `frappe.db.set_value`, `frappe.db.delete` and `frappe.db.bulk_insert` fire **no** events; `doc.db_set` fires **only** `on_change` | Known capture gap, covered by the Phase 4 reconciler; documented in `capture-notes.md` |
| 4 | A job that **overruns** is not run twice (Frappe de-duplicates scheduled jobs by id), but the stack has **one worker for `short,default,long`**, so a long job delays every other job, including the relay | The relay processes bounded batches (at most 1000 rows) so it finishes in seconds; it still takes `GET_LOCK` and releases it explicitly |
| 5 | A site created with `bench new-site` and the default database-login scope is usable **only from the creating container's IP**: the scheduler container was refused (`Access denied`) until the login host was widened | Phase 5 must pass `--mariadb-user-host-login-scope` for each stack's network range (the blueprint already plans it); a site that works in the web container can still fail in the scheduler and workers |

## Results

Confidence: **High** = observed directly and consistent; **Medium** = observed but the mechanism was not fully explained.

| Item | Answer | Evidence | Confidence |
| --- | --- | --- | --- |
| **(a)** Does a `doc_events` `on_change` handler's row commit with the document, and vanish when the request later raises? | **Yes, both.** A POST that completes persisted the document and its 5 handler rows together. A POST that saved and then raised returned HTTP 417 and left **no** document and **no** handler rows | `curl -X POST .../nxerp.spike.api.save_ok?title=sp-post-ok` -> `HTTP 200`; `curl -X POST .../save_then_raise?title=sp-post-fail` -> `HTTP 417`. Query: `tabSpike Parent` has `sp-post-ok` and not `sp-post-fail`; `spike_log` for `sp-post-ok`: `before_validate, validate, after_insert, on_update, on_change`; none for `sp-post-fail`. Same calls as GET: `save_ok` returned `HTTP 200` but **nothing persisted** (finding 1) | High |
| **(b)** Which events fire for which operation | See the table below | `bench --site phase3.localhost execute nxerp.spike.runner.item_b` (handlers registered for 10 events on a test DocType) | High |
| **(c)** Does a handler see `flags.in_delete` during `delete_doc`? Does `on_change` fire during delete? | **Yes to both.** `frappe.delete_doc` fires `on_trash`, then `on_change` **with `doc.flags.in_delete` true**, then `after_delete` (also with it true) | `frappe.delete_doc()` -> `["on_trash", "on_change[in_delete]", "after_delete[in_delete]"]` | High |
| **(d)** Can `doc_events` be computed at import from a JSON file? What must happen after a change? | **Yes.** `hooks.py` read a JSON file at import and built `doc_events` from it. After editing the JSON, **`bench clear-cache` alone was enough**: the new handler fired in a fresh process and in the already-running web process, with no restart (observed twice: adding `on_change`, then `after_insert`, then removing it). Before the cache clear, nothing changed (hooks are cached). **`scheduler_events` is different: a new cron entry created no `Scheduled Job Type` row until `bench migrate`** | Step 1 (JSON lists `ToDo`, no cache clear): web `[]`, fresh `[]`. Step 2 (`clear-cache`): web `[on_change]`, fresh `[on_change]`. Step 3 (adds `after_insert`, `clear-cache`): web `[after_insert, on_change]`. Step 5 (removes it, `clear-cache`): web `[on_change]`. Cron: after `clear-cache` no `nxerp.spike%` job type; after `bench migrate` both rows present. Mechanism: `frappe.get_module` is `importlib.import_module`, which would normally keep an imported module; the observation contradicts that, so the explanation is unconfirmed | **Medium** for "no restart needed" (the safe procedure stays: `bench migrate`, `clear-cache`, restart workers on deploy); High for the rest |
| **(e)** Does `Authorization: token key:secret` work for a whitelisted method with `frappe.only_for(role)`? What does a user without the role get? | **Yes.** With the role: 200. Without it: **403** `PermissionError`. No token: 403. Wrong secret: 401 | `reader (has role) -> HTTP 200 {"message":{"user":"spike-reader@example.test","ok":true}}`; `plain (no role) -> HTTP 403 ... PermissionError`; `no token -> HTTP 403`; `wrong secret -> HTTP 401` | High |
| **(f)** Does a `* * * * *` cron run every minute? What happens to a job that overruns? Does `GET_LOCK` work through `frappe.db.sql`? | **Cron:** it runs about once a minute **when the worker is free**; the first run came about 2 minutes after the scheduler was enabled (and after the login-host fix, finding 5). **Overrun:** a 150-second job was never run twice at once; the stack's single worker was occupied, so `cron_tick` ran at 09:40:08 and next at 09:44:05, a gap of about 4 minutes. **`GET_LOCK`:** works; a second connection got 0 while the first held it and 1 after the first connection closed; the lock is tied to the connection, not the transaction | `spike_log`: `cron_tick 09:40:08`, `overrun_start 09:40:12`, `overrun_end 09:42:42`, `cron_tick 09:44:05`, `overrun_start 09:44:06`. Lock: `{"second connection GET_LOCK(.., 0)": 0}` while held, `1` after. Source read to explain: `ScheduledJobType.enqueue` skips queueing when a job with the same id is queued or running | High (timing varies with the other jobs on the worker) |
| **(g)** Does the Deleted Document table get a row for `frappe.delete_doc`? Is there a retention setting? | **Yes, one row** for `delete_doc`; **none** for `delete_permanently`. **No built-in retention**: `Deleted Document` is not in `default_log_clearing_doctypes` (the list Log Settings clears), so rows are never removed automatically | `rows before/after delete_doc: [1, 2]`; after `delete_permanently`: still 2; `"Deleted Document" in default_log_clearing_doctypes: false` (19 doctypes listed, none of them this one) | High |
| **(h)** Customer save time with and without a handler that inserts one row (100 saves each) | **About 0.6 ms more per save (about 2%)**, inside the run-to-run noise: 30.2 and 31.3 ms without, 31.5 and 31.2 ms with | Two rounds each of 100 saves: without 30.20 / 31.33 ms, with 31.49 / 31.23 ms (the handler wrote 100 rows in each "with" round, 0 in each "without"). A first set of rounds was discarded: the handler had not been registered for `Customer`, so it measured nothing (`log_rows` 0) | High (the jobs ran on the same site at the same time, so absolute numbers are noisy) |

### (b) Events by operation

| Operation | Events that fired, in order |
| --- | --- |
| `doc.insert()` | `before_insert`, `before_validate`, `validate`, `after_insert`, `on_update`, `on_change` |
| `doc.save()` | `before_validate`, `validate`, `on_update`, `on_change` |
| `doc.submit()` | `validate`, `before_submit`, `on_update`, `on_submit`, `on_change` |
| `doc.db_set("qty", 3)` | `on_change` only |
| `frappe.db.set_value()` | none |
| `frappe.db.delete()` | none |
| `frappe.rename_doc()` | `before_rename`, `after_rename` (no `on_change`) |
| `frappe.delete_doc()` | `on_trash`, `on_change` (`in_delete` true), `after_delete` (`in_delete` true) |
| `frappe.db.bulk_insert()` | none |

## What was not tested

- The save-time numbers come from one machine with Docker Desktop and are a guide, not a benchmark.
- ERPNext's `Customer` was saved on a site created without the setup wizard (a Customer Group and Territory were added by hand); real sites may carry more `Customer` handlers.
- The feed and relay code do not exist yet (3B and 3C).
