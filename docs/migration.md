# Migration and Rollback Procedures

## Guiding Principles

1. **Always back up first.** No migration runs on production without a verified backup.
2. **Test on staging first.** Every patch is validated on staging before production.
3. **Patches are idempotent.** All patches check for existing state before modifying.
4. **One migration per PR.** Avoid bundling multiple schema changes in one PR.
5. **No raw DDL SQL.** Use Frappe DocType definitions or `frappe.db.add_column()` / `frappe.db.rename_column()`.

---

## What Triggers a Migration

A migration (`bench migrate`) is required when:

- A new DocType is added
- A field is added, renamed, or removed from a DocType
- A patch is added to `patches.txt`
- `hooks.py` changes require data initialization

A migration is **not** required for:
- Python logic changes only
- Frontend-only (Vue/CSS) changes
- Configuration changes via site settings

---

## Writing a Patch

### File location

```
apps/helpdesk/helpdesk/patches/
├── v1_0/
│   ├── __init__.py
│   └── my_descriptive_patch_name.py
└── ...
```

Use the version directory that matches the current major version.

### Patch template

```python
"""
Patch: helpdesk.patches.v1_0.add_escalation_level_to_ticket
Purpose: Add the escalation_level field to HD Ticket.

Safe to re-run: Yes (checks for column existence first).
"""

import frappe


def execute():
    """Add escalation_level field to HD Ticket if absent."""
    # Check prevents failure on re-run or environments where
    # the DocType already has the column from a newer version.
    if frappe.db.has_column("HD Ticket", "escalation_level"):
        return

    # Use frappe.db helpers, not raw ALTER TABLE
    frappe.db.add_column(
        "HD Ticket",
        "escalation_level",
        fieldtype="Int",
        default=0,
    )

    # Only commit when necessary; Frappe commits after each patch
    frappe.db.commit()
```

### Register in patches.txt

```
helpdesk.patches.v1_0.add_escalation_level_to_ticket
```

Lines are executed in order, once per site. They are not re-run unless explicitly listed again.

---

## DocType Schema Changes

Add or modify fields through the Frappe DocType editor or by editing the `.json` file directly:

```
apps/helpdesk/helpdesk/helpdesk/doctype/hd_ticket/hd_ticket.json
```

After editing the JSON:

```bash
bench --site nxerp.localhost migrate
```

Frappe generates and runs the necessary `ALTER TABLE` automatically.

**Never** modify `information_schema` tables directly.

---

## Running Migrations

### Development

```bash
bench --site nxerp.localhost migrate
```

### Staging / Production

Follow the [deployment guide](deployment.md). Migrations are part of step 6 of the production deployment procedure.

---

## Pre-Migration Checklist

- [ ] Database backup taken and verified (see below)
- [ ] Patch tested on a copy of the database
- [ ] Patch registered in `patches.txt`
- [ ] PR reviewed by a senior backend engineer (CODEOWNERS enforcement)
- [ ] Staged: migration tested on staging environment
- [ ] Rollback plan documented if the migration cannot complete

---

## Taking a Database Backup

```bash
# On the server
bench --site nxerp.nxsys.in backup --with-files

# Backup file location
ls -lh ~/nxerp-bench/sites/nxerp.nxsys.in/private/backups/
```

Verify the backup:

```bash
# Test that the backup archive is valid
gunzip -t /path/to/backup.sql.gz && echo "Backup OK"
```

Store backups in a location separate from the server (S3, Google Cloud Storage, etc.) before running a risky migration.

---

## Rolling Back a Failed Migration

### If migrate fails mid-way

```bash
# Check what ran
bench --site nxerp.nxsys.in console
# In the console:
frappe.get_all("Patch Log", filters={"patched": 1}, fields=["name", "modified"], order_by="modified desc", limit=10)
```

### Database restore (last resort)

```bash
# Restore from the pre-migration backup
# WARNING: All data changes since the backup will be lost
bench --site nxerp.nxsys.in restore /path/to/YYYY-MM-DD_backup.sql.gz
```

After restoring, revert the code to the pre-migration commit and redeploy.

---

## Sensitive Migration Operations

These operations require explicit senior / DevOps approval:

| Operation | Risk | Approval Required |
|-----------|------|------------------|
| Renaming a DocType | Breaks existing data links | Senior + DevOps |
| Dropping a column | Data loss | Senior + DevOps |
| Changing a field type | Data conversion or loss | Senior backend |
| Bulk data update in a patch | Performance / locking | Senior backend |
| Modifying System Settings or Website Settings | Affects all users immediately | Senior + sign-off |

---

## Patch Review Requirements

Patches that touch these areas require the `@Sria-Infotech-Pvt-Ltd/senior-backend` code owners:

- `helpdesk/patches/`
- `helpdesk/patches.txt`
- `nxerp/patches/`
- `nxerp/patches.txt`

See [CODEOWNERS](../.github/CODEOWNERS).
