# ADR-008: NXDESK is the umbrella platform; NXERP is the ERP product

- **Status:** Accepted (owner decision D1, 2026-11-11)
- **Date:** 2026-11-11
- **Changes:** the "Product identity" rules in `CLAUDE.md`, which said NXERP is the umbrella. Nothing in ADR-001 to ADR-007 about
  code, routes, roles or access changes.

## Context

- **FACT** (`CLAUDE.md`, `README.md`, `docs/architecture/overview.md` before this ADR): "NXERP" names the umbrella platform and brand,
  ERPNext is "the ERP app inside it", and ERPNext must never be called NXERP.
- **DECISION (owner, D1):** the umbrella platform is **NXDESK**. The ERPNext-based ERP product is shown to people as **NXERP**.
  The company support app is shown as **Sria Helpdesk**. A future HRMS is shown as **Royal HRMS**.
- **FACT** (`apps/nxerp_platform/nxerp/www/`, `registry.py`, `hooks.py`): the Python app is `nxerp`, the folder is `apps/nxerp_platform`,
  routes live under `/nxerp/*`, grant roles are named `NXERP Access: <App>`, and the existing login, launcher and no-access
  pages carry NXERP logo images.

## Decision

1. **Display names** (what a person reads on a page):

   | Thing | Display name |
   | --- | --- |
   | The umbrella platform | **NXDESK** |
   | The ERP product (ERPNext inside) | **NXERP** |
   | The support product (Helpdesk inside) | **Sria Helpdesk** |
   | A future HRMS | **Royal HRMS**: not installed, so **never shown** anywhere until it is installed and registered |

2. **Technical identifiers do not change.** The Python app `nxerp`, the folder `apps/nxerp_platform`, the routes `/nxerp/*`, the
   roles `NXERP Access: ...`, the registry keys (`erpnext`, `helpdesk`), the Frappe apps `erpnext` and `helpdesk`, and every ERPNext
   package and DocType keep their names. Display names are presentation only.
3. **One place for platform presentation**: `apps/nxerp_platform/nxerp/branding.py` (platform name, tagline, logo paths, support
   link). The registry (`registry.py`) holds each product's display name and copy.
4. **Not renamed, on purpose:** upstream packages, DocTypes and Python modules; the `nxerp` app and its folder; the routes and roles above;
   the `NXERP` logo image files (no NXDESK logo exists; until the owner supplies one the new pages show a typographic wordmark and
   the existing login, launcher and no-access pages keep their look).
5. **The rules that stay:** ERPNext keeps its technical identity and is not treated as the platform; Helpdesk is a separate app and is
   not the ERP; Frappe is technology, not an application shown to business users; unified experience is not merged code.

## Consequences

- Wherever two names meet, the rule is: **the person sees the display name, the code sees the identifier.** A launcher tile still reads
  "ERPNext" and "Helpdesk" until the owner decides to rename the tile text (**ASSUMPTION**: the owner wants the launcher left alone in
  Phase 1; it is listed in the phase report as an open inconsistency, not changed here).
- Documents that said "NXERP is the umbrella" are updated in the same pull request: `CLAUDE.md`, `README.md`,
  `docs/architecture/overview.md`, `docs/architecture/rules.md`. Older ADRs and evidence keep their text because they record what was
  decided at the time; where they say "NXERP platform" read "NXDESK platform".
- Adding a product still takes one registry entry plus role grants (`docs/architecture/adding-an-app.md`), and now also its display
  name and copy.

## Not decided here

Domain names, logo files, and whether the launcher tiles adopt the display names. Those are owner actions.
