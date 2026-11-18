# Measurements (Phase 1)

Database touched: [fill in]

Fill this in by hand with **redacted** output: replace real names with placeholders such as `[Customer Name]`, never paste a password, hash, token or
`encryption_key`, and run everything on a **restored scratch copy** (compose project `nxerp-scratch`, neutralised first), never on production.
Leave a table empty until a person has run the command. Counts only, never values.

How to run an SQL block: feed it on standard input to the site's `mariadb` client so backticks stay literal.

```bash
S="docker compose -p nxerp-scratch --env-file <env> -f deploy/docker/compose/staging-like/compose.yaml exec -T backend bash -lc 'cd /home/frappe/frappe-bench && bench --site <site> mariadb'"
$S <<'SQL'
-- paste one block here
SQL
```

## U2: apps on the site

```bash
bench --site <site> list-apps
```

| Date | Database touched | Redacted output | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

## U3: DocTypes (and so tables) per owning app

```sql
SELECT m.app_name, COUNT(*) AS doctypes
FROM tabDocType d JOIN `tabModule Def` m ON m.name = d.module
WHERE d.issingle = 0 AND d.is_virtual = 0
GROUP BY m.app_name;
```

| Date | Database touched | Redacted output | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

## U4: grants of the live account and all accounts

```sql
SHOW GRANTS FOR CURRENT_USER;
SELECT user, host FROM mysql.user;
```

| Date | Database touched | Redacted output | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

Flag any global (`*.*`) grant, a host of `%`, or `GRANT OPTION`. The `IDENTIFIED BY PASSWORD` hash in a grant line must be removed before pasting.

## U5: cross-app Link and Table fields

```sql
SELECT mf.app_name AS from_app, mt.app_name AS to_app, COUNT(*) AS fields
FROM tabDocField f
JOIN tabDocType d ON d.name = f.parent
JOIN `tabModule Def` mf ON mf.name = d.module
JOIN tabDocType t ON t.name = f.options
JOIN `tabModule Def` mt ON mt.name = t.module
WHERE f.fieldtype IN ('Link', 'Table', 'Table MultiSelect') AND mf.app_name <> mt.app_name
GROUP BY 1, 2;
```

| Date | Database touched | Redacted output | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

## U9: stored secrets by kind (`__Auth`)

```sql
SELECT doctype, fieldname, COUNT(*) AS rows_found FROM __Auth GROUP BY 1, 2;
```

| Date | Database touched | Redacted output | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

Record counts only. Never select the `password` column.

## Entity measurements (U15 to U18, counts only)

Summarise these in `entity-catalogue.md`.

## U15: row counts of the candidate entities

```sql
SELECT 'Customer' AS entity, COUNT(*) AS n FROM tabCustomer
UNION ALL SELECT 'Contact', COUNT(*) FROM tabContact
UNION ALL SELECT 'Company', COUNT(*) FROM tabCompany
UNION ALL SELECT 'HD Ticket', COUNT(*) FROM `tabHD Ticket`
UNION ALL SELECT 'HD Customer', COUNT(*) FROM `tabHD Customer`
UNION ALL SELECT 'User (System)', COUNT(*) FROM tabUser WHERE user_type = 'System User'
UNION ALL SELECT 'User (Website)', COUNT(*) FROM tabUser WHERE user_type = 'Website User';
```

| Date | Database touched | Redacted output | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

## U16: how many customers use the fields that must stay OUT of the shared layer

```sql
SELECT COUNT(*) AS customers,
  SUM(tax_id IS NOT NULL AND tax_id <> '') AS with_tax_id,
  SUM(default_price_list IS NOT NULL AND default_price_list <> '') AS with_price_list,
  SUM(customer_primary_contact IS NOT NULL AND customer_primary_contact <> '') AS with_primary_contact
FROM tabCustomer;
```

| Date | Database touched | Redacted output | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

## U17: mirror gaps

```sql
SELECT COUNT(*) AS hd_customers_without_customer
FROM `tabHD Customer` h LEFT JOIN tabCustomer c ON c.name = h.erpnext_customer
WHERE h.erpnext_customer IS NOT NULL AND h.erpnext_customer <> '' AND c.name IS NULL;
SELECT COUNT(*) AS tickets_without_contact FROM `tabHD Ticket` WHERE contact IS NULL OR contact = '';
```

| Date | Database touched | Redacted output | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

## U18: companies and currencies

```sql
SELECT COUNT(*) AS companies, COUNT(DISTINCT default_currency) AS currencies FROM tabCompany;
```

| Date | Database touched | Redacted output | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

## Baseline isolation audit (`scripts/isolation_audit.sh all`)

```bash
NXERP_SITE=<site> NXERP_COMPOSE_PROJECT=nxerp-scratch NXERP_ENV_FILES=<env> scripts/isolation_audit.sh all
```

| Date | Database touched | Line (PASS / FAIL / UNVERIFIED / INFO) | Interpretation |
| --- | --- | --- | --- |
|  |  |  |  |

## Restore drill from an encrypted backup

| Date | Backup file | Restore took | Health check | Result |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Phase 5: Tests T1 to T6

Filled in during Phase 5. Leave empty now.

| Test | Date | Command | Redacted output | PASS / FAIL |
| --- | --- | --- | --- | --- |
| T1 |  |  |  |  |
| T2 |  |  |  |  |
| T3 |  |  |  |  |
| T4 |  |  |  |  |
| T5 |  |  |  |  |
| T6 |  |  |  |  |
