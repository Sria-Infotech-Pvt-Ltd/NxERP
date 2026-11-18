# Helpdesk parity (Phase 4, Part A)

Source list: `docs/audit/helpdesk-audit.md` section 10. Only items marked ABSENT or PARTIAL were worked on.
Every claim below was checked by running something on 2026-10-28 (dev site, Chromium against the rebuilt SPA).

## Where the code is (read this first)

| Change | Repository and state |
| --- | --- |
| Unseen-assigned badge (a) and the manager-mention tests (f) | Helpdesk fork, branch `phase-4/helpdesk-parity` (a separate git worktree), **committed** (`754cffd93`, `8f77254e9`). Written in Phase 4 |
| Team above Assignee, Assignee follows Team, reset on Team change, Assignee on create (b to e) and "ticket admin" visibility | **Uncommitted edits in the main Helpdesk checkout** (`helpdesk/`, branch `feature/nxerp-platform-login`), made by another working session before Phase 4 and **not written or committed by this work**. A worktree for the same feature on `nxerp-stable` (`port/nxerp-stable-admin-team`) shows that session was still active. They were reviewed, deployed to the dev bench and checked, but must be committed by their author (or on request) before they count as delivered |

The two sets touch different files, so they merge without conflict.

## Status per item

| # | Requirement | Audit status | Now | Evidence |
| --- | --- | --- | --- | --- |
| a | Per-agent badge: count of unseen tickets assigned to the agent | ABSENT | **DONE** (committed) | `helpdesk/api/unseen.py` (`get_unseen_assigned_count`, agent-only, only the caller's own count, through `get_list` so permissions and team limits apply), `desk/src/stores/unseen.ts`, badge on the Tickets nav item. Reuses Frappe's `_assign` and `_seen`: no new state. 5 Python tests pass (`helpdesk/tests/test_unseen_assigned.py`: own tickets only, opening removes it, someone else opening does not hide it, resolved not counted, customers refused). Browser: with two unseen assigned tickets the sidebar shows **2** on Tickets (`docs/evidence/phase4/badge-sidebar.png`) |
| b | Team shown above Assignee | ABSENT on desktop | **Present in the uncommitted edits** | Browser, ticket details tab: Team label at y=249, Assignee at y=287 (`docs/evidence/phase4/ticket-team-above-assignee.png`). Mobile header already had it |
| c | Assignee filtered by Team | PARTIAL (opt-in setting, default off) | **Present in the uncommitted edits** (the list now follows the Team whenever one is set, no longer gated by two HD Settings checkboxes: a behaviour change for existing sites) | Code read; **no automated or browser test of the filtering itself** |
| d | Assignee reset when Team changes | PARTIAL | **Present in the uncommitted edits** (`dropAssigneesOutsideTeam` unassigns people not on the new Team; server-side `remove_assignment_if_not_in_team` already existed) | Code read and the SPA builds; **not exercised in a browser** |
| e | Same on create and edit | ABSENT on create | **PARTIAL** | Create form now has an Assignee control after the template fields (`docs/evidence/phase4/create-assignee.png`) and assigns after the ticket is created. Team appears on create only if the ticket template includes the Team field; the default template does not, so with no Team there is nothing to filter by. Not exercised end to end |
| f | Comments and @mentions notify managers | PARTIAL | **Confirmed present, tests added** | No new code is needed: core mentions notify whoever is mentioned and managers are active HD Agents, so they are in the editor's list. `helpdesk/tests/test_manager_mentions.py` (3 tests pass) pins: a mentioned manager gets a Mention notification pointing at the ticket, managers are in the mention list, the internal comment stays hidden from the customer |

## Related change that needs an owner decision

The uncommitted edits also make **System Manager and Agent Manager "ticket admins"** (`helpdesk/utils.py: is_ticket_admin`): they see every ticket regardless of team restrictions, and a System Manager without an HD Agent record counts as an agent. This **reverses an assertion in Helpdesk's own test** (`test_core_comments.py`: "System Manager is denied like core" became "passes the ticket hook"). Interaction with NXERP: the platform gate still requires the Helpdesk grant (`NXERP Access: Helpdesk`, or `Agent` / `Agent Manager`), so a System Manager alone still cannot open Helpdesk. Three new tests in `test_hd_ticket.py` pass (manager sees every team; System Manager without an agent record sees every ticket; a deactivated manager loses visibility).

## Customer portal

The portal's internal-data protections are covered by Helpdesk's existing suite (comment trust boundary, ticket permission tests) plus the nxerp customer-leak tests; see the full-suite results in `docs/acceptance/acceptance-report.md`. The new unseen endpoint refuses non-agents (test above).
