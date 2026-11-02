# Source Pins and Provenance

## Framework and ERPNext source

| Project | Repository | Ref | Commit |
|---|---|---|---|
| Frappe | `https://github.com/frappe/frappe.git` | `v16.53.0` | `e8d41dd0061a32ee781caefe7d0b0d2bb7c15362` |
| ERPNext | `https://github.com/frappe/erpnext.git` | `v16.52.1` | `ade850bbd6a7412e9994a9637d2c5c713771632a` |
| Telephony | `https://github.com/frappe/telephony.git` | `develop` (default ref observed on 2026-10-23) | `9447577500a25d242088398157b72c654fa34b20` |

ERPNext `v16.52.1` declares Frappe `>=16.50.0,<17.0.0`; the selected Frappe tag satisfies that requirement. Helpdesk's dependency metadata accepts Frappe `>=16.50.0,<17.0.0` after alignment in this integration snapshot. This establishes source metadata compatibility, not a successful installation or migration.

The local inspection clones `erpnext-source/` and `frappe-source/` are intentionally ignored by Git. CI retrieves the pinned refs into temporary `apps/` paths. A Bench install is required to run the applications.

## Customized Helpdesk snapshot

`apps/helpdesk/` was copied from the workspace Helpdesk repository at `1c6981cc515af58b8cdfbad7a7525b33236e399b`, branch `feature/nxerp-login-page`, remote `https://github.com/Sriainfotech/Frappe-Help-Desk.git`, including the pre-existing worktree changes and untracked theme/test files. The original Helpdesk repository remains intact in the workspace. Changes have not been pushed to or committed in that source repository.

Future app updates should be reviewed against the source remote and imported as normal changes into this monorepo. Do not overwrite the vendored snapshot from a clean clone: that would discard the theme, login, and other pre-existing worktree changes included here.

## NXERP app

`apps/nxerp/` was copied from the workspace's unversioned `NXERP/nxerp/` directory. It has no Git remote or source commit available. Its theme, fonts, logo references, required-app order, and generated CSS were aligned with the Helpdesk theme during this integration work.
