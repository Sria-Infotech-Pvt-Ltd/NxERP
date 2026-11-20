# Measurements (Phase 1)

Database touched: scratch stack `nxerp-scratch` (fake data) for the audit and backup drill; production (read-only) for the section below.

Fill this in by hand with **redacted** output: replace real names with placeholders such as `[Customer Name]`, never paste a password, hash, token or
`encryption_key`, and run everything on a **restored scratch copy** (compose project `nxerp-scratch`, neutralised first), never on production.
Leave a table empty until a person has run the command. Counts only, never values.

## Production measurements (live host, read-only, 2026-11-19)

Database touched: **production**, the live Hostinger host, sites `nxerp.nxsys.in` (database `nxerp_db`) and `helpdesk.nxsys.in` (database `helpdesk_db`). Read-only, through each site's own login via `bench ... mariadb`. Counts and grants only: no row contents, no secrets, nothing copied off the host. (This overrides the "scratch copy only" rule above for these counts: the owner replied `GO READ PROD` on 2026-11-19.)

| Fact (FACT, run 2026-11-19) | Result |
| --- | --- |
| Deployment model | bare metal under systemd, no Docker; benches `/srv/apps/nxerp/frappe-bench` and `/srv/apps/helpdesk/frappe-bench`, behind nginx |
| Sites | **two separate sites**, one per bench (not one site with all apps) |
| `nxerp.nxsys.in` apps | frappe 16.53.0, erpnext 16.52.1, payments 0.0.1, nxerp 0.0.1 (matches the pins) |
| `helpdesk.nxsys.in` apps | frappe 16.53.0, telephony 0.0.1, helpdesk 1.22.2, nxerp 0.0.1 |
| Database engine | MariaDB 10.11.14 (pin says 11.8); PostgreSQL 16 also on the host for other applications |
| Database accounts | `nxerp_user` and `helpdesk_user`: one `ALL PRIVILEGES` grant each on its own database, no global privilege beyond USAGE, no GRANT OPTION, host `localhost` (not `%`) |
| Tables | `nxerp_db` 767, `helpdesk_db` 323; each login sees 2 schemas (its own and `information_schema`) |
| ERPNext Customer in the Helpdesk database | `tabCustomer` **does not exist** in `helpdesk_db`, so the in-process Customer mirror cannot be running |
| `nxerp_db` rows | Customer 0, Contact 2, System Users 3, Website Users 1, Company 2, Sales Invoice 0, customers with tax id / credit limit / default price list / primary contact: 0 |
| `helpdesk_db` rows | HD Ticket 53, HD Customer 5, Contact 66, System Users 22, Website Users 2, HD Team 10 |
| Other applications on the same host | at least 8 more (agribot, aira, budgeting, cashora, eskoolia, expense, nxgen, nxdesk) on the same MariaDB/PostgreSQL servers and nginx |

Interpretation (JUDGMENT): production already has one database and one login per Frappe app, so the Frappe-level "one shared login" finding of the original blueprint does not hold here. What remains is a **shared host and shared MariaDB server** (any process as `deploy`, or MariaDB root, reaches every database), no encrypted or scheduled backups verified, and no cross-app data flow at all. The NXERP site holds almost no business data yet, so the shared read layer has little to carry today. Not yet measured: backups present on the host (a `backups/` folder and migration archives exist in `/home/deploy`), MariaDB `mysql.user` accounts (needs root), Redis exposure, firewall rules.

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

Run 2026-11-19 on Docker Desktop (Windows), image `nxerp:0.0.1-8a4910610a5b-dirty`, fake data, domain `example.test`: **rehearsal on a developer machine, not on the server** (the server steps are behind GATE G5). Outputs are PASS lines only: no secret is printed. Command: `scripts/isolation_audit.sh cross-read reach published hostnames stacks` (three stacks), and the same without `stacks` with six sites (three throwaway stand-ins `app3`, `app4`, `app5`, removed afterwards).

| Test | Date | Command | Redacted output | PASS / FAIL |
| --- | --- | --- | --- | --- |
| T1 | 2026-11-19 | `isolation_audit.sh cross-read` (SELECT as one stack's login on every other stack's database) | 3 stacks: 6 lines `PASS cross-read-<a>-cannot-SELECT-<b> (error 1142)`; 6 sites: 30 lines, all error 1142 | PASS |
| T2 | 2026-11-19 | same (`DELETE ... WHERE 1=0`) | 3 stacks: 6 lines error 1142; 6 sites: 30 lines, all error 1142 (60 cross-read checks in total for 6 sites = the full 6 by 6 matrix) | PASS |
| T3 | 2026-11-19 | `isolation_audit.sh stacks` (grants) | per stack: `PASS grants-one-database-level-grant`, `-no-global-privilege`, `-no-grant-option`, `-host-not-wildcard`; `mysql.user` shows hosts `172.30.10.%` (id, hd) and `172.30.20.%` (erp), none `%` | PASS |
| T4 | 2026-11-19 | `isolation_audit.sh stacks` (root-env) | per stack: `PASS root-env-backend`, `-websocket`, `-queue-worker`, `-scheduler` (value length 0) | PASS |
| T5 | 2026-11-19 | `isolation_audit.sh reach` | each stack to the other tier's database server, to `shared-db` and to every other stack's redis-cache and redis-queue: `PASS reach-...` (blocked); 3 stacks: 18 lines | PASS |
| T6 | 2026-11-19 | `isolation_audit.sh published` | `PASS published-nxerp-db-none`, `-nxerp-id-none`, `-nxerp-hd-none`, `-nxerp-erp-none`, `PASS published-nxerp-edge-loopback-only` | PASS |
| hostnames | 2026-11-19 | `isolation_audit.sh hostnames` | per host: `PASS hostnames-<stack>-ping`, `PASS hostnames-<stack>-feed-hidden` (`/api/method/nxerp.shared.feed.head` answers 404 through the edge) | PASS |

Totals: three stacks 65 PASS, 0 FAIL, 0 UNVERIFIED; six sites (cross-read, reach, published, hostnames) 152 PASS, 0 FAIL, 0 UNVERIFIED; 39 long-running containers from the new projects (db 2, edge 1, six stacks with 6 each) as the footprint table predicts. After removal of the stand-ins: 41 PASS, 21 long-running containers of the new projects.
Note: `id` and `hd` share one database server, so a TCP connection between them is possible by design; their isolation is the account grants (T1 and T2), not the network.
