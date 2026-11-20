# Runbook: rolling back the isolation cutover, decision point D and the restore points

**Reverting code does not reverse database changes.** A code revert leaves `hd`, `id` and any removed Helpdesk tables exactly as they are. Rollback here means pointing users back at a database that was never modified, plus replaying writes made elsewhere.

Rollback is real only because the original site is untouched until decision point D (it receives only maintenance mode, the disabled incoming mailboxes and the `nxerp_cutover_allowed` flag, all of which `cutover.sh unfreeze` removes or restores).

## The rollback table

| Stage | State | Action | What can be lost |
| --- | --- | --- | --- |
| Before the canary opens (steps 8.4 and 8.5) | the old site untouched except maintenance mode | `deploy/scripts/cutover.sh unfreeze --yes --restore-email`; point the edge back if it was changed; discard `hd` and `id` | nothing |
| Canary to D (steps 8.6 and 8.7) | customers and email write to `hd`; the old site's Helpdesk data is frozen at T0 | 1. maintenance mode on `hd`; 2. `deploy/scripts/cutover.sh delta-export --since <T0> --yes`; 3. `deploy/scripts/cutover.sh delta-import --yes <bundle>` into the old site (skip identical, report different, never overwrite); 4. disable the mailbox on `hd`, re-enable it on the old site; 5. point the edge back; 6. `cutover.sh unfreeze --yes --restore-email`; 7. `cutover.sh reconcile` in compare mode between the old site and the replayed data | ticket-number collisions (mitigated: `clone-hd` reserves an offset of `NXERP_CUTOVER_TICKET_GAP`, default 100000, on `hd`); conflicts are reported for a person to decide, never overwritten |
| After D (step 8.9) | Helpdesk removed from the old site | **No rollback.** Forward-fix on `hd`. A backup restore is disaster recovery only | every change after the backup |
| ERP move, until the old stack is deleted (step 8.9, item 3) | the old ERP stack stopped, kept 30 days | `docker compose -p <old project> start`; point `erp.<domain>` back; re-enter finance records made on the new site by hand (finance records are never imported) | finance entries made on the new site, re-entered by hand |

Every `cutover.sh` step prints its own undo, and `cutover.sh status` shows what was recorded.

## Decision point D

D is the earlier of seven days after opening to customers (step 8.6) or the owner's written sign-off after one full business cycle. It always comes after RP-final: encrypted backups of `hd`, `id` and the old site, each restored once on the scratch machine to prove it opens. The decision, the date, the people who agreed and the RP-final paths go in `docs/architecture-isolation/decision-point.md`. `finalize-erp` refuses without a verified RP-final path and without `NXERP_CUTOVER_DECISION_D=GO` (set only after the owner replied `DECISION D: GO`).

**After D, Helpdesk is removed from the old site and the old way back no longer exists.**

## Restore points

| Name | What | When | Used for |
| --- | --- | --- | --- |
| RP0 | verified backup of the source site | at the freeze (T0), step 8.4 | starting point of every clone; the source can also simply be unfrozen |
| RP1 | backup of `hd` after the prune and migrate | step 8.4, after `reconcile` PASS | undoing a bad canary on `hd` without cloning again |
| RP2 | daily encrypted backup of `hd` and `id` | step 8.7, every day until D | restoring `hd` or `id` to yesterday |
| RP-final | encrypted backups of `hd`, `id` and the old site, restore drill passed | before D (step 8.8) | disaster recovery only after D |
| RP-erp | backup of the old site taken at the ERP freeze | step 8.9, item 3 | the ERP move, and the 30-day way back |

Restore with `deploy/scripts/restore.sh --yes <backup>` (or `deploy/scripts/stack.sh <stack> restore --yes <backup>`); encrypted backups need `NXERP_BACKUP_AGE_IDENTITY`. A restore overwrites the site, so it needs the owner's approval in production. Keep RP-erp and the stopped old stack for 30 days.

## The shared layer in a rollback

The shared layer is derived and never a restore point. To roll back to the old owners: unset `nxerp_shared_read` on Helpdesk first (Helpdesk is back on its own data), then `nxerp_shared_publish` on the owners; point the projector's sources back at the old site with `shared.sh repoint`, then `shared.sh rebuild-and-verify`.

## Who decides

The owner decides every production rollback, except the "before the canary" row, which the operator may run alone when `reconcile` fails. Support lead and accountant are told at once.
