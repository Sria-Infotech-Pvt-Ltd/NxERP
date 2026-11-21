# Rehearsal 2 of the cutover (restored, neutralised copy: FAKE-DATA scratch site)

Second consecutive clean run, straight after rehearsal 1, no manual fixes and no code change between them. Same source and same caveat: a fake-data scratch site, not a copy of production.

| Date | Result (PASS or FAIL) | Timings (start, end, freeze window) | Defects found | Sign-off (name, date) |
| --- | --- | --- | --- | --- |
| 2026-11-21 | PASS (every step exit 0; `reconcile` `RESULT: PASS`; replay: added 4, skipped 0, conflicts 0) | whole run 220 s, freeze window 186 s | none | [pending: owner] |

Step times: preflight 1 s, freeze 30 s, backup-source 10 s, clone-hd 103 s, build-id 10 s, reconcile 30 s, delta-export 6 s, delta-import 5 s, unfreeze 15 s.

## Reconcile report

Same checks as rehearsal 1: all counts, file hashes and message ids equal; ERP counts on the source unchanged.

## Rollback section (delta export and import)

| Tickets created on hd | Imported | Conflicts | Notes |
| --- | --- | --- | --- |
| 2 | 2 (added 4 documents) | 0 | both tickets present on the source with their tag column |

## Before and after (checks 8.1 and 8.2)

Not done on this fake-data source.

## What is still needed before the production window

A rehearsal on a restored copy of the real production backup (needs the owner's `GO READ PROD`), with the before and after numbers of checks 8.1 and 8.2 and the freeze time measured on real volumes (assumption A6: 2 hours).
