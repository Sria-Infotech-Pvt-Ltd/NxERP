# Helpdesk: upstream and our changes

- **Upstream:** https://github.com/frappe/helpdesk
- **Base:** upstream `develop` at `58b82a6e2` (merge of PR #3821, 2026-10-11). Target release per ADR-002: `v1.31.0`.
- **Imported from:** company fork `Sriainfotech/Frappe-Help-Desk`, branch `phase-4/helpdesk-parity`, commit
  `8f77254e9fe92c29956e6e543dd3814f9a22cd75` (23 commits, 136 files, +5,375 / -278 against the base). `apps/helpdesk/`
  is a snapshot of that tree (blob-identical, checked); its git history stays in the fork.
- **Submodule:** `apps/helpdesk/frappe-ui` at `a3d141c63b098d7dfbeb7a511d98fc988a950048`, https://github.com/frappe/frappe-ui.git.
- **Renamed folders (this repository only):** `desk/` to `hd-frontend/`, `e2e/` to `hd-e2e-tests/`, `docker/` to `hd-docker/`.
  Upstream merges must map these paths. `realtime/` keeps its name.

## Our changes (summary; detail in `docs/audit/helpdesk-audit.md` and `docs/parity/helpdesk-parity.md`)

| Area | Change |
| --- | --- |
| Identity | Helpdesk app title "Helpdesk"; the NXERP login, router and launcher moved to the platform app |
| Branding | NXERP names, logos, PWA manifest, email provider labels (see audit tables) |
| Theme | token-driven palette (`hd-frontend/src/theme`, generated `helpdesk/theme_tokens.py`), theme persistence on the user (`helpdesk/api/theme.py`) |
| Parity features | unseen-assigned badge (`helpdesk/api/unseen.py`, `hd-frontend/src/stores/unseen.ts`), manager @mention tests |
| Not included | uncommitted "Assignee follows Team" work (kept as a patch outside the repository) |

| Monorepo adaptation | `hd-frontend/src/theme/build/check-tracked.mjs` finds the git root above `apps/helpdesk` (it used to skip silently when no `.git` sat beside it) |

Keep this list current when you touch Helpdesk (rule 3, `docs/architecture/rules.md`).
