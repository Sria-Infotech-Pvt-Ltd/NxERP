# Rehearsal on the dev bench (work package 8A)

What was tried on the scratch bench (site `phase3.localhost`, fake data only) while building `nxerp/cutover.py`, what failed, and how the tools handle it. Production was not touched.

## What the tools do

| Function | Writes to | Notes |
| --- | --- | --- |
| `identity_export(path)` | a mode-600 file | User, Has Role, Role, Role Profile, User Social Login, the User rows of `__Auth`, the 2FA defaults. Counts only on screen. |
| `identity_import(path)` | the identity site | Upsert keeping names and timestamps, no hooks and no welcome mail. Refuses (writes nothing) if the target Administrator password differs, unless `admin_password="keep"`. |
| `prune_helpdesk_site(dry_run=1)` | the cloned Helpdesk site | Dry run by default. Apply refuses while `erpnext` or `payments` is still installed. |
| `reconcile(path, mode)` | a mode-600 snapshot or report | Names are hashed (16 hex characters); the report names the first differing key, never a value. |
| `reserve_naming_series_offset(n)` | the Helpdesk site | Raises the HD Ticket counter, never lowers it. |
| `delta_export(since, path)` / `delta_import(path)` | a bundle / the source site | Skip identical, report different, never overwrite. Files are added only if missing. |
| `feed_head()` | nothing | The owner's feed head, so the shared-layer rebuild knows where to start. |

All of them refuse unless site config `nxerp_cutover_allowed` is 1.

## U9 settled: how logins are stored (FACT, read from frappe/utils/password.py, twofactor.py and a count on the scratch site)

- `__Auth` with `encrypted = 0` holds a salted password hash for `User` rows. It is portable between sites as it is.
- `__Auth` with `encrypted = 1` holds values encrypted with the site's own `encryption_key`. For Users this is the `api_secret`; other rows belong to other DocTypes (Email Account, Connected App, NXERP Peer) and are not copied.
- The 2FA secret is `tabDefaultValue` with parent `__2fa` and key `<user>_otpsecret`, encrypted with the site key. The flag that 2FA is set up is the same table, key `<user>_otplogin`.
- Consequence: a copy of the hashes alone keeps passwords working. API secrets and 2FA secrets need the source key. The import takes it from the environment variable `NXERP_CUTOVER_SOURCE_ENCRYPTION_KEY` (never from the file) and encrypts again with the identity site's key. DECISION: the key is not stored in the export file.

## What was hard

- **`uninstall-app` (U10) is not tried here.** It runs against a restored copy of the real site in rehearsal 1 (step 8.2). The prune tool is written so that it does not rely on it having cleaned core rows: it only needs `erpnext` and `payments` to be uninstalled, and then removes rows that still hang off DocTypes the site no longer has. UNVERIFIED until the rehearsal.
- **Core rows attached to ERP documents.** ToDo, Comment, Communication, File, Version and Tag Link are matched on the DocType they hang off. A row with no reference at all is kept (it may be a plain note or an unlinked email), and counted separately by the dry run in the rehearsal report. DECISION: kept, because deleting something we cannot place is worse than keeping it.
- **Contacts and addresses.** A Contact or Address is removed only if it had links and every link points at a DocType the site does not keep. One with no links, or one still linked to a Helpdesk or shared DocType, stays. `Address` is not in the prompt's list; it is included because customer addresses are ERP data and would otherwise stay on the Helpdesk site. DECISION, reviewable in the dry run.
- **Files on disk.** Pruning removes File rows only. The files stay in the cloned site's folder (the prune does not delete from disk). Rehearsal 1 measures how much space that is; removing them is a separate, reviewed step.
- **Tests and commits.** The tools commit, but not under the test runner (the test data rolls back). A restored test site must not be pruned by tests: prune tests mock the list of installed apps and rely on that rollback.
- **Fake rows.** A ToDo or Contact that points at a non-existent Customer cannot be made through the controllers (they look the document up), so the tests write those rows straight into the table.

## Results on the dev bench

`bench --site phase3.localhost run-tests --app nxerp --module nxerp.tests.test_cutover`: 19 tests OK (the gate on every function, the identity round trip with password and 2FA, a different source key, refusal without the key, idempotence, the Administrator refusal, prune dry run and apply, the reconcile cases, the naming counter, delta add/skip/conflict, a file travelling with its row).
