# ADR-009: Hybrid database architecture (database per application plus one shared read database)

- **Status:** Proposed. Becomes Accepted only when the owner confirms assumptions A1 to A13 below (blueprint Phase 1, step 1.11). Nothing in this ADR is built yet.
- **Date:** 2026-11-18
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

## Decision (proposed)

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

## Assumptions A1 to A13 (every one: owner to confirm)

The repository cannot decide these. None is guessed as true: each stays **owner to confirm** until you write "confirmed" or your change next to it.

| ID | Assumption | Status | Owner's answer |
| --- | --- | --- | --- |
| A1 | ~~Production runs one site with all six apps, as staging-like does~~ **Measured 2026-11-19: false.** Production runs two separate Frappe sites on separate benches (`nxerp.nxsys.in`: frappe, erpnext, payments, nxerp; `helpdesk.nxsys.in`: frappe, telephony, helpdesk, nxerp), each with its own database and login | corrected by measurement; owner to confirm | See `docs/architecture-isolation/measurements.md` |
| A2 | One organisation, **one bare-metal host (systemd, no Docker) shared with at least 8 other applications**, a handful of NXDESK apps; the shared model still carries a `tenant_id` from day one | host model corrected by measurement; owner to confirm | The Phase 5 Docker stack template and the Docker-based `backup.sh` do not describe production |
| A3 | Helpdesk no longer writes into ERPNext tables; it may ask ERPNext to change a customer through ERPNext's command API | owner to confirm | |
| A4 | Customers (portal users) sign in at the identity site too | owner to confirm | |
| A5 | Business roles (`Agent`, `Sales User`) stay managed inside each app; the identity site grants only app access | owner to confirm | |
| A6 | A freeze window of up to 2 hours is acceptable for the Helpdesk cutover | owner to confirm | |
| A7 | `telephony` is used only by Helpdesk, so it lives in the Helpdesk stack | owner to confirm | |
| A8 | "nxerp" means the ERP product (ERPNext) inside NXDESK per `CLAUDE.md`; the platform app `nxerp` runs on the identity site | owner to confirm | |
| A9 | The three planned apps are HRMS, Project Management and Budget Management; HRMS and Budget are classed restricted, Project Management standard. AIRA HRMS stays "Coming soon" only | owner to confirm | |
| A10 | The shared read database uses MariaDB 11.8 on its own server instance (not PostgreSQL) | owner to confirm | |
| A11 | Sync lag up to 60 seconds at the 95th percentile is acceptable; reads that must be current go to the owner | owner to confirm | |
| A12 | The shared layer is read-only reference data, not a reporting warehouse; financial amounts are not copied. Open sub-question: may Helpdesk see a derived `has_overdue_invoice` flag (default off) | owner to confirm | |
| A13 | "Royal HRMS" (`CLAUDE.md`, ADR-008) and "AIRA HRMS" (`nxerp/public_catalog.py`) are the same planned product; the repository does not say so | owner to confirm | |

## Open points (not decided here)

- **Hosting:** one Docker host or several; where the restricted (ERPNext, HRMS, Budget) database server runs; off-site backup storage and retention (owner-action-list item 18).
- **Data classification:** the S1/S2/S3 classes and the field allow-lists in `entity-catalogue.md` are a proposal; the owner (and, where applicable, a data-protection adviser) must approve them.
- **Compliance:** which regimes apply to customer and employee data is not stated in the repository. This ADR makes no compliance claim; seek professional review before relying on it.
- **Customers on the identity site:** assumption A4 changes who holds customer credentials.
- **Naming:** assumption A13.
- **Helpdesk Tasks:** the uncommitted `HD Task` work stores HRMS and PBT fields as copies; how it moves to `employee_ref` and `project_ref` is a Phase 7 question.
