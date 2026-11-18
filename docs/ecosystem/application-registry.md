# NXDESK application registry

Planning document. Read [README.md](README.md) first: it explains what this list is **not** (it is not the runtime registry and installs nothing).
Last reviewed: 2026-11-18. Tags: **FACT** (checked in the repository, path given), **OWNER TO DEFINE** (the repository does not say), **UNRESOLVED**.

## Summary

| Application | Display name | Status | Technical identity | Data class (proposal, ADR-009) |
| --- | --- | --- | --- | --- |
| ERP | NXERP | **Existing** | Frappe app `erpnext` (pinned `v16.52.1`), key `erpnext` | restricted (finance) |
| Support | Sria Helpdesk | **Existing** | Frappe app `helpdesk` (company fork in `apps/helpdesk`), key `helpdesk` | standard |
| HR and workforce | AIRA HRMS (see naming note) | **Announced** ("Coming soon") | none yet | restricted (personal and payroll data) |
| Project Management | OWNER TO DEFINE | **Planned** | none yet | standard |
| Budget Management | OWNER TO DEFINE | **Planned** | none yet | restricted (finance) |
| CRM | OWNER TO DEFINE | **Proposed** | none yet | OWNER TO DEFINE |

The platform app `nxerp` is not in this table because it is the NXDESK platform itself (login, router, launcher, access layer), not a product under it.

---

## NXERP (existing)

| Field | Entry |
| --- | --- |
| Purpose | The ERP product: accounting, selling, buying, stock, manufacturing and projects, with access that follows each person's role (`registry.py`, `summary`) |
| Status | Existing. Installed, registered, in `deploy/apps.json` (FACT) |
| Technical identity | Frappe app `erpnext`; owns `erpnext` and `payments`; route `/desk/home`; staff role `NXERP Access: ERPNext` (FACT: `apps/nxerp_platform/nxerp/registry.py`). ERPNext is upstream and is never vendored or edited |
| Scope and capabilities | Whatever ERPNext provides at the pinned tag. NXDESK adds nothing to its code |
| Dependencies | Frappe Framework 16; the `payments` app (FACT: `deploy/apps.json`) |
| Integrations | Opt-in in-process Customer mirror with Helpdesk today (FACT: `apps/helpdesk/helpdesk/integrations/erpnext/`). ADR-009 (Proposed) would replace it with the shared read layer and a command API |
| Relationship to NXDESK | A product under the umbrella. The platform decides who may enter it; ERPNext keeps its own permissions and identity |
| Candidate shared entities (ADR-009, Proposed) | owner of `customer`, `contact`, `org_unit` |
| Priority and notes | Not applicable (already live). Its ERPNext setup wizard on the dev site is not completed, which needs real company data from the owner (`docs/PROGRESS.md`) |

## Sria Helpdesk (existing)

| Field | Entry |
| --- | --- |
| Purpose | The support product: tickets, knowledge base, agents and a restricted customer portal |
| Status | Existing. Installed, registered, in `deploy/apps.json` (FACT) |
| Technical identity | Frappe app `helpdesk`, company fork in `apps/helpdesk`; owns `helpdesk` and `telephony`; route `/helpdesk/home`; staff role `NXERP Access: Helpdesk` (FACT: `registry.py`). Helpdesk is a support app and is never the ERP |
| Scope and capabilities | Helpdesk's own, plus the Tasks module (`HD Task`) |
| Dependencies | Frappe Framework 16; `telephony` (FACT: `deploy/apps.json`) |
| Integrations | Optional Customer mirror with ERPNext; HTTP clients to external HRMS and PBT systems (`apps/helpdesk/helpdesk/integrations/external/`, behaviour UNVERIFIED against a live server) |
| Relationship to NXDESK | A product under the umbrella. Customers get the restricted portal only, never Desk |
| Candidate shared entities (ADR-009, Proposed) | owner of `ticket_summary`; consumer of `customer`, `contact`, `user_ref`, `employee_ref`, `project_ref` |
| Priority and notes | Not applicable (already live) |

## HR and workforce, "AIRA HRMS" (announced)

| Field | Entry |
| --- | --- |
| Purpose | The planned HR and workforce product. The public copy describes people records, attendance and leave, workforce reporting and AI-assisted insights (FACT: `public_catalog.py`) |
| Status | **Announced** only: shown as "Coming soon", with no sign-up, sign-in or application link. It is not installed |
| Technical identity | None. No app, no folder, no registry entry |
| Scope and capabilities | OWNER TO DEFINE beyond the four public bullets above |
| Dependencies | OWNER TO DEFINE. Helpdesk Tasks already calls an external HRMS over HTTP (`integrations/external/hrms.py`), so the source of employee data today is a separate system |
| Integrations | Candidate owner of the shared entity `employee_ref` (ADR-009, Proposed). Must never share salary, ID number, bank or health data |
| Relationship to NXDESK | A future product under the umbrella, registered only once installed (ADR-008) |
| Naming note | `CLAUDE.md` and ADR-008 say "Royal HRMS"; `public_catalog.py` says "AIRA HRMS". The repository does not say they are the same product. **UNRESOLVED**, owner to decide (ADR-009 assumption A13) |
| Priority and notes | OWNER TO DEFINE |

## Project Management (planned)

| Field | Entry |
| --- | --- |
| Purpose | OWNER TO DEFINE. Named as a future app in `CLAUDE.md` |
| Status | Planned. Not installed, not shown |
| Technical identity | None |
| Scope and capabilities | OWNER TO DEFINE |
| Dependencies | OWNER TO DEFINE |
| Integrations | Helpdesk Tasks reads projects from an external "PBT" system over HTTP today (`integrations/external/pbt.py`, UNVERIFIED against a live server). Candidate owner of the shared entity `project_ref` (ADR-009, Proposed) |
| Relationship to NXDESK | A future product under the umbrella |
| Priority and notes | OWNER TO DEFINE. Whether PBT becomes this app or stays external is **UNRESOLVED** |

## Budget Management (planned)

| Field | Entry |
| --- | --- |
| Purpose | OWNER TO DEFINE. Named as a future app in `CLAUDE.md` |
| Status | Planned. Not installed, not shown |
| Technical identity | None |
| Scope and capabilities | OWNER TO DEFINE |
| Dependencies | OWNER TO DEFINE. Likely reads finance data owned by NXERP; if so it would call NXERP's own API, never copy finance fields into a shared layer (ADR-009, Proposed) |
| Integrations | Consumer of `project_ref` is suggested by the blueprint, not decided |
| Relationship to NXDESK | A future product under the umbrella |
| Priority and notes | OWNER TO DEFINE |

## CRM (proposed)

| Field | Entry |
| --- | --- |
| Purpose | OWNER TO DEFINE |
| Status | **Proposed**. No CRM app exists in the repository (FACT) and `CLAUDE.md` does not list it; it was named by the owner in conversation on 2026-11-18 |
| Technical identity | None |
| Scope and capabilities | OWNER TO DEFINE |
| Dependencies | OWNER TO DEFINE. ERPNext owns `Customer` today, so a CRM must agree who owns customer data before any design (ADR-009 ownership rule: one owner per entity) |
| Integrations | OWNER TO DEFINE |
| Relationship to NXDESK | A possible future product under the umbrella |
| Priority and notes | OWNER TO DEFINE. Needs owner approval before it can move to Planned |

---

## Open questions for the owner

1. Is "Royal HRMS" the same product as "AIRA HRMS"? (A13)
2. Does the external PBT system become the Project Management app, or stay external?
3. Which of Project Management, Budget Management and CRM is built first, and what is the approved scope of each?
4. Should the CRM move from Proposed to Planned, and who owns customer data if it does?
