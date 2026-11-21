# Rehearsal 1 of the cutover (restored, neutralised copy: FAKE-DATA scratch site)

**What this is:** the source was the scratch site (`nxerp-scratch`, site `phase3.localhost`: ERPNext, Helpdesk, payments, nxerp, 3 tickets, 45 users, fake data), restored into the staging `hd` stack and copied into the staging `id` stack. It is **not** a copy of production: no `GO READ PROD` had been given. It proves the tools and the order, not production volumes.

| Date | Result (PASS or FAIL) | Timings (start, end, freeze window) | Defects found | Sign-off (name, date) |
| --- | --- | --- | --- | --- |
| 2026-11-21 | PASS (every step exit 0; `reconcile` `RESULT: PASS`; the replay of 2 new tickets: added 6, skipped 1, conflicts 0) | whole run 254 s, freeze window (freeze to unfreeze) 223 s | none in this run; 11 defects were found and fixed in the attempts before it (list below) | [pending: owner] |

Step times of the clean run: preflight 2 s, freeze 27 s, backup-source 10 s, clone-hd 155 s, build-id 8 s, reconcile 25 s, delta-export 5 s, delta-import 5 s, unfreeze 11 s.

## Defects found by the attempts before the clean runs (all fixed, with tests where code)

1. `freeze` could not disable an Email Account whose name has a space, and stopped after the first account (docker swallowed the list on stdin; spaces and carriage returns broke the JSON argument).
2. `bench execute` prints nothing for 0 or an empty list: a blank was read as "queue not empty".
3. The pre-flight ping failed after the freeze because a frozen site answers 503.
4. `docker cp` leaves root-owned files the tools cannot remove: replaced by streaming (stdin, tar) everywhere.
5. The `hd` and `id` images did not contain `nxerp.cutover` (new code): the release image must carry Phase 8 before the window.
6. Uninstalling erpnext queued about 630 jobs; Frappe refuses new work above 500, and draining took about 30 minutes. `clone-hd` now stops the worker and scheduler, lifts the limit, purges the clone's queued jobs and restarts the worker.
7. `migrate` failed with error 1020 while a worker still ran queued jobs (fixed by the same stop).
8. The restore's own health check failed on the deliberately disabled scheduler and on one early `/login` 503 (the check retries `/login` now; `clone-hd` tolerates the disabled scheduler).
9. `delta-export --since` took T0 in UTC while Frappe stores times in the site's timezone: on a site behind UTC the first hours of changes would have been skipped (T0 with `Z` or an offset is now converted).
10. The replay dropped tickets' tags and assignment columns (`_user_tags` and friends) and Tag Links (now exported and restored).
11. The old staging `erp` stack held the alias `erp-backend`; the rehearsal stopped it for the duration and restored it afterwards.

## Reconcile report

Counts per Helpdesk DocType equal on source and target (HD Ticket 3 = 3, HD Customer 10 = 10, HD Agent 4 = 4, and the rest); Communication, Comment, ToDo, Tag Link and Version counts attached to Helpdesk documents equal; file hashes and message ids equal; no duplicate message id; SLA status differences allowed 0; ERP counts on the source unchanged since the freeze. The prune on the clone removed Comment 299, Version 2354, Dynamic Link 12, Address 5, Contact 7, File 1; the ticket counter was reserved at 100181 (+100000).

## Rollback section (delta export and import)

| Tickets created on hd | Imported | Conflicts | Notes |
| --- | --- | --- | --- |
| 2 | 2 (added 6 documents, skipped 1) | 0 | tags and hidden columns restored; a second replay skips what is identical |

## Before and after (checks 8.1 and 8.2)

Not done on this fake-data source (no business numbers to compare). To be recorded in the rehearsal on a real copy.
