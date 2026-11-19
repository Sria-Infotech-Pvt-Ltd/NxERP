# ADR-009: Hybrid database architecture (database per application plus one shared read database)

- **Status:** Accepted by the owner on 2026-11-19 (reply `ACCEPT ADR-009`), with assumptions A1 to A13 as listed below (defaults accepted 2026-11-18; A1 and A2 as corrected by the 2026-11-19 measurements). Accepting the direction builds nothing: the shared layer is built phase by phase, switched off by default.
- **Date:** 2026-11-18 (updated 2026-11-19: production measurements, Phase 2 contracts)
- **Changes:** nothing yet. This ADR records a direction and the questions the owner must answer. It does not change ADR-001 to ADR-008. If accepted it would
  refine ADR-005 (apps never import each other: the shared read layer is how they exchange reference data) and ADR-006 (the dev and staging stacks).
- **Source:** `docs/architecture-isolation/NXERP_Isolation_Blueprint.md` (isolation-only version) and the NXDESK hybrid database blueprint (version 6, 2026-11-18),
  Part 2 sections 1, 2 and 6.

## Context

> **Correction 2026-11-19 (measured on production):** Frappe-level isolation already exists on the live host: NXERP and Helpdesk are separate sites with separate databases and separate `localhost`-only logins, and `tabCustomer` does not exist in the Helpdesk database. The remaining exposure is the shared host and MariaDB server, not a shared Frappe login. The decision below still holds for the apps that will need shared reference data, but its Phase 5 (split databases) is largely already true in production; Phases 6 to 8 must be re-planned for a bare-metal host.

- **FACT** (`deploy/bootstrap/bootstrap.sh`, `deploy/docker/compose/staging-like/compose.yaml`): one site hosts frappe, payments, erpnext, telephony, helpdesk and nxerp;
  that site has one database and one database login, shared by every app. Role checks (`has_permission`, the `nxerp` gate) are Python inside the same process, so
  they cannot limit which tables code can read. A flaw in the internet-facing Helpdesk therefore reaches the ERPNext tables too.
- **FACT** (blueprint section 1.5): the only app-to-app data sync today is an in-process Customer mirror between Helpdesk and ERPNext (`doc_events` in both
  directions); Helpdesk reads employees and projects from two external systems by polling HTTP; `HD Task` keeps copies of those fields. There is no outbox,
  event bus, broker, read replica or reconciliation anywhere in `apps/` or `deploy/`.
- **FACT**: only ERPNext and Helpdesk (plus payments, telephony and the platform app `nxerp`) are installed. Royal HRMS, Project Management and Budget Management
  are not installed and are shown nowhere (`CLAUDE.md`, ADR-008).
- **NOT YET MEASURED** (Phase 1 does this, on a restored scratch copy): the table-by-app inventory, cross-app Link fields, the grants of the live database account,
  and the row counts and field use of the candidate shared entities. See `docs/architecture-isolation/measurements.md`.

## Decision

1. **Each application gets its own authoritative database and its own database login.** Only that app writes it. No app reads or writes another app's database.
2. **One shared read database** holds an allow-listed, classified copy of a few reference entities (`customer`, `contact`, `user_ref`, `org_unit`, `employee_ref`,
   `project_ref`, `ticket_summary`; see `docs/architecture-isolation/entity-catalogue.md`). It is derived, never authoritative, written only by one projector,
   and can be dropped and rebuilt from the owners.
3. **Owners publish committed changes through a transactional outbox** written in the same transaction as the business change. A resumable pull relay and an
   idempotent projector keep the shared database current; a scheduled reconciler detects drift. No message broker at this size (the triggers for adding one are in the blueprint).
4. **Apps read other apps' data only through a controlled Read API** (per-app token, per-field allow-list, audit log). **They change other apps' data only through the owner's command API.**
5. **Sensitive classes are never copied** into the shared layer: tax identifiers, credit limits, payment terms, price lists, bank details, ledger entries, amounts, payroll, health data, passwords, tokens, API keys, `encryption_key`.
6. **Order of work:** Phase 1 measures and hardens (this ADR is written there); Phases 2 to 4 build and prove the shared layer on the current single site with everything switched off; Phases 5 to 8 split the databases.
7. **Technical identifiers do not change** (`nxerp`, `apps/nxerp_platform`, `/nxerp/*`, `NXERP Access: ...`), and `nxerp` still declares no `required_apps`.

## Consequences

- **Gains:** a flaw in one app no longer exposes another app's database; the shared reference data is managed in one place instead of three unmanaged mechanisms; backups
  and restores are per authoritative database.
- **Costs:** more to operate (database instances, an outbox and projector, a Read API, monitoring of sync lag); cross-app data becomes eventually consistent (target in A11); a
  freeze window at cutover (A6); every new shared field needs a written contract.
- **Phase 1 itself changes nothing in the running system.** It adds an audit script, optional encrypted backups, one container hardening option, and documents. The only
  production change it proposes is one nightly backup job, and only after the owner replies with the matching approval.

## Alternatives rejected (for the owner to challenge)

| Alternative | Why not (JUDGMENT) |
| --- | --- |
| Keep one shared database and rely on RBAC | RBAC is application code; it cannot limit what a flawed app can read. This is the problem being solved |
| Database per app with no shared layer (APIs and live calls only) | Every consumer needs its own mirror or live calls, so ERPNext downtime degrades Helpdesk screens, and every new app adds another integration |
| A shared **operational** database all apps write | Recreates the Integration Database anti-pattern with new tables |
| Webhooks plus a nightly pull | A Frappe webhook can be lost on a crash or outage; a transactional outbox cannot lose a committed change |
| A message broker (Kafka, RabbitMQ) now | Operational weight not justified at five apps; revisit on the written triggers |
| PostgreSQL for the shared layer (row-level security) | A second engine to operate; see assumption A10 |

## The corrected earlier rejection

The isolation-only blueprint (version 5) rejected "a shared database" outright. That stays right for a shared **operational** database, one that several apps write and that holds each app's authoritative data: it recreates the Integration Database pattern and hands every app the same login.
It was wrong for a **read-only, derived, rebuildable** shared layer, which is a different thing: nothing is authoritative there, only one projector writes it, apps reach it only through a Read API that filters by field and tenant and keeps an audit, sensitive classes are never copied into it, and it can be dropped and rebuilt from the owners. The decision to give every app its own authoritative database stands. Phase 2 makes the line concrete: a field can enter the shared layer only through a reviewed contract file (`apps/nxerp_platform/nxerp/shared/contracts/`), checked by `scripts/check_contracts.py`.

## Triggers to reconsider

Revisit this decision, and say so in a new ADR, when any of these becomes true:

- more than about 10 independent consumers of the owners' feeds, sustained load above about 50 events per second, or a need for propagation under 5 seconds: add a broker as a wake-up layer in front of the same outbox (never replacing it);
- a screen needs a shared field to be current to the second: read it from the owner instead, or revisit the lag target (A11);
- finance or reporting needs amounts or balances across apps: that is a governed analytics store, a separate decision (A12), never the shared read layer;
- the contract lint's deny-list refuses fields that several owners legitimately need: review the list rather than adding exceptions one by one;
- the shared layer grows beyond reference data (more than a handful of entities, or free text): reconsider whether it is still a read model;
- production stays one host for every app: re-check whether the isolation gained is worth the extra database instances (the live host already has one database and login per Frappe app, see the 2026-11-19 correction).

## Unresolved items

Not decided by this ADR and not verified. Each one has an owner decision or a check:

1. ~~**DDL not executed.**~~ **Resolved 2026-11-19.** `scripts/check_shared_ddl.sh` runs `0001_shared_model.sql` twice on a throwaway MariaDB 11.8.9 container and checks 12 tables, utf8mb4, no foreign keys, real columns equal to the contracts, the idempotent upsert (older event ignored, replay a no-op, newer wins, tombstone sticks, late older event cannot resurrect), cursor rollback and the dead-letter unique key: all PASS. Re-run it in Phase 4.
2. **MariaDB version.** The pin is 11.8 (ADR-002); the live host runs 10.11.14. Which version the shared layer and the owners run in production is an ADR-002 decision.
3. **Hosting.** The shared read database, the projector and the Read API need a place on a host that today runs more than eight other applications under one operator account.
4. **Identity owner.** `user_ref` is owned by `identity`, a planned site (Phase 6). Until then each app keeps its own `User` table; whether one of them publishes `user_ref` in the meantime is not decided.
5. **Unconfirmed source fields.** Fields marked `verify` in the contracts (`org_unit.disabled`, `ticket_summary.customer_id` and `assignee_user_id`, and all of `employee_ref` and `project_ref`) were not confirmed against a live DocType.
6. **Command roles.** `needs_role` values in the contracts are placeholders until each owner names the real role.
7. **Names.** Whether "Royal HRMS" (`CLAUDE.md`) and "AIRA HRMS" (`public_catalog.py`) are the same product (A13).
8. **Derived overdue flag.** Whether Helpdesk may see a `has_overdue_invoice` boolean (blueprint A12): off by default, not in any contract.
9. **Retention and compliance.** Outbox rows kept 14 days and read audit 400 days are ASSUMPTIONS; a compliance owner decides, including right-to-erasure handling.
10. **Virtual DocType as a Link target** for Desk screens: link validation has a virtual branch, search dispatch was not verified.
11. ~~**CI.**~~ **Partly resolved 2026-11-19.** The contract check ran on GitHub (dispatched on `integration/hybrid-db`) and passed. The first run also exposed a bandit finding in a Phase 2 test (fixed). CI did not run for pull requests into `integration/hybrid-db` until `ci.yml` was extended to `integration/**`. Three CI jobs fail for reasons that predate this programme (`license-check`: four third-party packages outside the licence policy; `e2e (journeys)`; the aggregate `ci-gate`); they were already failing on `develop` on 2026-11-05 and are the team's to resolve.

## Assumptions A1 to A13 (accepted by the owner)

The repository cannot decide these; the owner did. On 2026-11-18 the owner replied `ACCEPT DEFAULTS` for A1 to A13, and on 2026-11-19 accepted this ADR. A1 and A2 were then measured on the live host and corrected (see `docs/architecture-isolation/measurements.md`). A10 and A13 are accepted as defaults but remain open questions in the unresolved list above (items 2 and 7).

| ID | Assumption | Status | Owner's answer |
| --- | --- | --- | --- |
| A1 | ~~Production runs one site with all six apps, as staging-like does~~ **Measured 2026-11-19: false.** Production runs two separate Frappe sites on separate benches (`nxerp.nxsys.in`: frappe, erpnext, payments, nxerp; `helpdesk.nxsys.in`: frappe, telephony, helpdesk, nxerp), each with its own database and login | corrected by measurement; accepted 2026-11-19 | See `docs/architecture-isolation/measurements.md` |
| A2 | One organisation, **one bare-metal host (systemd, no Docker) shared with at least 8 other applications**, a handful of NXDESK apps; the shared model still carries a `tenant_id` from day one | host model corrected by measurement; accepted 2026-11-19 | The Phase 5 Docker stack template and the Docker-based `backup.sh` do not describe production |
| A3 | Helpdesk no longer writes into ERPNext tables; it may ask ERPNext to change a customer through ERPNext's command API | accepted | default accepted 2026-11-18 |
| A4 | Customers (portal users) sign in at the identity site too | accepted | default accepted 2026-11-18 |
| A5 | Business roles (`Agent`, `Sales User`) stay managed inside each app; the identity site grants only app access | accepted | default accepted 2026-11-18 |
| A6 | A freeze window of up to 2 hours is acceptable for the Helpdesk cutover | accepted | default accepted 2026-11-18 |
| A7 | `telephony` is used only by Helpdesk, so it lives in the Helpdesk stack | accepted | default accepted 2026-11-18 |
| A8 | "nxerp" means the ERP product (ERPNext) inside NXDESK per `CLAUDE.md`; the platform app `nxerp` runs on the identity site | accepted | default accepted 2026-11-18 |
| A9 | The three planned apps are HRMS, Project Management and Budget Management; HRMS and Budget are classed restricted, Project Management standard. AIRA HRMS stays "Coming soon" only | accepted | default accepted 2026-11-18 |
| A10 | The shared read database uses MariaDB 11.8 on its own server instance (not PostgreSQL) | accepted | default accepted 2026-11-18; see unresolved item 2 (production runs MariaDB 10.11) |
| A11 | Sync lag up to 60 seconds at the 95th percentile is acceptable; reads that must be current go to the owner | accepted | default accepted 2026-11-18 |
| A12 | The shared layer is read-only reference data, not a reporting warehouse; financial amounts are not copied. Open sub-question: may Helpdesk see a derived `has_overdue_invoice` flag (default off) | accepted | default accepted 2026-11-18 |
| A13 | "Royal HRMS" (`CLAUDE.md`, ADR-008) and "AIRA HRMS" (`nxerp/public_catalog.py`) are the same planned product; the repository does not say so | accepted | default accepted 2026-11-18; still open, see unresolved item 7 |

## Open points (not decided here)

- **Hosting:** one Docker host or several; where the restricted (ERPNext, HRMS, Budget) database server runs; off-site backup storage and retention (owner-action-list item 18).
- **Data classification:** the S1/S2/S3 classes and the field allow-lists in `entity-catalogue.md` are a proposal; the owner (and, where applicable, a data-protection adviser) must approve them.
- **Compliance:** which regimes apply to customer and employee data is not stated in the repository. This ADR makes no compliance claim; seek professional review before relying on it.
- **Customers on the identity site:** assumption A4 changes who holds customer credentials.
- **Naming:** assumption A13.
- **Helpdesk Tasks:** the uncommitted `HD Task` work stores HRMS and PBT fields as copies; how it moves to `employee_ref` and `project_ref` is a Phase 7 question.
