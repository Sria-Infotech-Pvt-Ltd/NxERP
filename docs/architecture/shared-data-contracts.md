# Shared-data contracts

Part of the hybrid database plan (ADR-009). Each shared entity has one **contract file** in `apps/nxerp_platform/nxerp/shared/contracts/`. The contract is the only place that says who owns the entity, which fields may leave the owner, how sensitive each field is, who may read it and which commands may change it. Later phases (outbox hooks, payload projection, the shared tables' views, consumer grants, command endpoints) are generated from or checked against these files. Nothing in this folder runs yet: it is data, a lint and tests.

## The seven entities

| Entity | Owner app | Status | Consumers (installed) |
| --- | --- | --- | --- |
| `customer` | `erpnext` | active | `helpdesk` |
| `contact` | `erpnext` | active | `helpdesk` |
| `org_unit` | `erpnext` | active | `erpnext`, `helpdesk` |
| `ticket_summary` | `helpdesk` | active | `erpnext` |
| `user_ref` | `identity` | planned (the identity site is Phase 6) | `erpnext`, `helpdesk` |
| `employee_ref` | `hrms` | planned (no HR app is installed) | `helpdesk` |
| `project_ref` | `project_management` | planned (no project app is installed) | `helpdesk` |

A **planned** owner is not in `nxerp/registry.py` on purpose: a registry entry would make the app look installed. The lint keeps a short list of planned owners (`PLANNED_APPS` in `scripts/check_contracts.py`) and only accepts them while the contract's `status` is `planned`.

## Rules the lint enforces (`scripts/check_contracts.py`)

| Rule | What it checks |
| --- | --- |
| C1 | structure: required keys, types, no unknown keys (the unit tests also validate against `contract_schema.json`) |
| C2 | one contract per entity, and the file is named `<entity_type>.json` |
| C3 | the owner is a key in `nxerp/registry.py`, or a planned owner while status is `planned` |
| C4 | classes are `S0`, `S1`, `S2` only; `S3` (finance, tax, payroll, credentials, health) is refused |
| C5 | no field name (shared or source) contains `password`, `secret`, `token`, `key`, `tax`, `salary`, `iban`, `bank`, `ssn` or `health` |
| C6 | consumers are registered or planned apps and list only shared fields of this entity |
| C7 | the owner's id field is never a shared field; a command writes only shared fields |
| C8 | no module path of `erpnext`, `helpdesk`, `telephony` or `payments` appears in any value |

## Run it

```
python3 -I scripts/check_contracts.py                      # all seven contracts
python3 -I scripts/check_contracts.py path/to/copy.json    # one file or folder (used to try a change)
python -m unittest apps/nxerp_platform/nxerp/tests/test_shared_contracts.py
```

On a Windows host without a `python3` shim, use `python`. The unit tests need no Frappe site; the JSON Schema test is skipped if `jsonschema` is not installed.

**CI:** the lint is a step of the `pins-and-architecture` job in `.github/workflows/ci.yml`. UNVERIFIED on GitHub: the workflow has not run with this step (see `docs/PROGRESS.md`).

## Add or change a shared field

1. Edit the entity's contract file: add the field to `fields` with `shared`, `source`, `class` and `type`. Mark it `"verify": true` with a `note` if the owner's field name was not confirmed.
2. Add the field to each consumer that needs it under `consumers` (a consumer can read nothing that is not listed).
3. Bump `contract_version`.
4. Run the lint and the tests. A field whose name hits the deny-list, or whose class is `S3`, is refused: rename it, or do not share it. A reviewed exception needs a line in `EXCEPTIONS` in the lint and a reason in the pull request.
5. The owner of the entity reviews the pull request. The shared tables' DDL (`shared_service/schema/`) must gain the matching column in the same change, or `test_schema_matches_contracts` fails.

## Add or change a consumer grant

A grant is a line under `consumers`: the app key and the shared fields it may read through the Read API. Add the line, run the lint, get the owner's approval. The consumer app must be installed (in `nxerp/registry.py`) or a planned app. Removing a consumer or a field takes effect when the contracts are next loaded.

## Add or change a command

A command is the only way another app asks the owner to change an entity. Add `{name, writable_fields, needs_role}` under `commands`. `writable_fields` are shared fields and never the id. The owner runs the command as the acting user, so the owner's own permissions still decide. `needs_role` is a placeholder until the owner confirms the real role.

## Add a new entity

Add `<entity_type>.json`, a column set in the DDL and, if its owner app is not installed, `status: planned`. Nothing is shared until the contract is merged.
