# Entity catalogue (template, Phase 1)

A **proposal**, not a decision: nothing is shared until the owner approves each row and a written contract exists (Phase 2). Source: blueprint section 2.3.
Classes: **S1** internal, **S2** personal, **S3** restricted (never copied to the shared layer).

Rules: one owner per entity; the shared layer never owns anything; nothing is shared unless it is listed here with an allow-list, a class and consumers.

| Entity | Owner | Status | Proposed shared fields (allow-list) | Class | Consumers |
| --- | --- | --- | --- | --- | --- |
| `customer` | NXERP (ERPNext `Customer`) | candidate | `customer_id`, `display_name`, `customer_type`, `customer_group`, `territory`, `disabled`, `primary_contact_id`, `modified_at` | S1; S2 for `display_name` of an individual | Sria Helpdesk (read-only) |
| `contact` | NXERP (Frappe `Contact` for customer contacts) | candidate | `contact_id`, `customer_id`, `full_name`, `email`, `phone`, `is_primary` | S2 (Helpdesk only, by field grant) | Sria Helpdesk |
| `user_ref` | Identity site (Frappe `User`) | candidate | `user_id`, `display_name`, `enabled`, `user_type`, `app_keys_granted` | S2 for the name, S1 for the rest | all installed apps |
| `org_unit` | NXERP (ERPNext `Company`) | candidate | `org_unit_id`, `name`, `parent_id`, `disabled` | S1 | all installed apps (the tenant key) |
| `employee_ref` | planned HRMS app (not installed) | **planned, not built** | `employee_id`, `display_name`, `department`, `designation`, `manager_employee_id`, `active` | S2; no salary, ID number, bank or health data, ever | Sria Helpdesk tasks |
| `project_ref` | planned Project Management app (not installed) | **planned, not built** | `project_id`, `name`, `status`, `owner_user_id`, `modified_at` | S1 | Sria Helpdesk |
| `ticket_summary` | Sria Helpdesk (`HD Ticket`) | candidate | `ticket_id`, `customer_id`, `status`, `priority`, `opened_at`, `resolved_at`, `assignee_user_id` (no subject, no message text) | S1 | NXERP (open tickets on a customer) |

**Never shared (S3):** tax identifiers, credit limits, payment terms, price lists, bank details, ledger entries, invoice and payment amounts, payroll and salary,
health data, passwords, tokens, API keys, `encryption_key`. Reached only through the owner's own API with the owner's authorisation.

Planned entities stay `planned`: nothing is built, mocked or displayed for an app that is not installed (`CLAUDE.md`).

## Measured facts (filled from `measurements.md`, redacted, counts only)

| Entity | Rows (U15) | Fields in use that must stay out (U16) | Gaps (U17) | Notes |
| --- | --- | --- | --- | --- |
| `customer` |  |  |  |  |
| `contact` |  |  |  |  |
| `user_ref` (System / Website) |  |  |  |  |
| `org_unit` (U18) |  |  |  |  |
| `ticket_summary` |  |  |  |  |

## Owner approval

| Entity | Approved by | Date | Changes requested |
| --- | --- | --- | --- |
| *(none yet)* |  |  |  |
