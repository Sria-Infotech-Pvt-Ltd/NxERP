# NXDESK ecosystem

**NXDESK** is the umbrella platform (ADR-008). It is not another application next to the ones below: it is the one login, one launcher and one identity
that the applications live under. This folder is the planning home for the whole ecosystem: what exists today, what is planned, and what is only an idea.

```
NXDESK  (umbrella platform: one login, one launcher, one identity)
  |-- NXERP            existing   ERP product, ERPNext inside
  |-- Sria Helpdesk    existing   support product, Helpdesk inside
  `-- future products  planned or proposed: see application-registry.md
```

The technical identifiers do not change (ADR-008): the platform app is `nxerp` in `apps/nxerp_platform/`, routes are `/nxerp/*`, grant roles are
`NXERP Access: ...`. A display name is what a person reads; an identifier is what the code uses.

## Three different lists. Do not mix them up

| List | Where | What it means | Who reads it |
| --- | --- | --- | --- |
| Runtime registry | `apps/nxerp_platform/nxerp/registry.py` | Apps that are **installed** and may be entered. Adding an entry is a code change | the access layer, router, launcher |
| Public announcements | `apps/nxerp_platform/nxerp/public_catalog.py` | Products the owner chose to **announce** as "Coming soon" on the public site. No sign-up, no sign-in, no link into an app | the public site |
| **Ecosystem registry (this folder)** | `docs/ecosystem/application-registry.md` | **Planning only**: every existing, planned and proposed application, with status, scope and relationships | people and AI assistants planning work |

Writing an application here installs nothing, creates no folder, adds nothing to `deploy/`, and displays nothing to users. If an entry here
disagrees with the code, the code wins and this file is fixed.

## Status values

| Status | Meaning | May it appear in code or deployment? |
| --- | --- | --- |
| **Existing** | Installed, registered in `registry.py`, in `deploy/apps.json` | yes, that is what it is |
| **Announced** | Planned **and** the owner asked to show it as "Coming soon" (today: AIRA HRMS) | only in `public_catalog.py`, labelled "Coming soon" |
| **Planned** | The owner has named it as a product that will be built; scope is not yet approved in detail | no |
| **Proposed** | An idea that has not been approved | no |
| **Retired** | Was in the ecosystem and has been removed | no |

## Rules (from `CLAUDE.md`)

- Future apps are **not installed**. Never build, mock or display one as if it exists, never create an empty app folder for it, never put it in `deploy/apps.json`,
  compose files or CI.
- Adding an application later must stay cheap: one registry entry, role grants, and the steps in
  [`../guides/how-to-add-an-app.md`](../guides/how-to-add-an-app.md) and [`../architecture/adding-an-app.md`](../architecture/adding-an-app.md).
- Apps never import each other; they exchange data through the platform (ADR-005) and, if ADR-009 is accepted, through the shared read layer and each owner's command API.
- A status change to Existing needs an ADR or ADR amendment in the same pull request as the code.

## How to add or change an entry

1. Copy the block of an existing entry in `application-registry.md` and keep every heading, even where the answer is "to be defined by the owner".
2. Write only what is evidenced (cite a path or document) or mark it **owner to define**. Do not invent scope, customers, dates or capabilities.
3. Keep the summary table at the top of the registry in step with the entry.
4. A new idea goes in as **Proposed**. Only the owner moves an entry to **Planned**.
5. Moving an entry to **Existing** is a platform change: follow the add-an-app guide and record the decision in an ADR.
