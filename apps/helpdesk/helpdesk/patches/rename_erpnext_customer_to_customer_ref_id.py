import frappe


def _columns() -> set:
    """The real column list (not Frappe's cached one, which is stale right after a schema change)."""
    return {
        row[0]
        for row in frappe.db.sql(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            ("tabHD Customer",),
        )
    }


def execute():
    """HD Customer.erpnext_customer becomes customer_ref_id (a plain reference to the system that owns customers).

    Runs before the model sync, so it renames the column in place and the sync then finds the new field already there; the
    values are kept. Idempotent: nothing happens once the old column is gone, and a site that already has both columns
    (the model sync ran first) gets the values copied across and the old column dropped.
    """
    if not frappe.db.table_exists("HD Customer"):
        return
    columns = _columns()
    has_old, has_new = "erpnext_customer" in columns, "customer_ref_id" in columns
    if has_old and not has_new:
        frappe.db.sql_ddl(
            "ALTER TABLE `tabHD Customer` CHANGE `erpnext_customer` `customer_ref_id` varchar(140)"
        )
    elif has_old and has_new:
        frappe.db.sql(
            "UPDATE `tabHD Customer` SET `customer_ref_id` = `erpnext_customer` "
            "WHERE (`customer_ref_id` IS NULL OR `customer_ref_id` = '') AND `erpnext_customer` IS NOT NULL"
        )
        frappe.db.sql_ddl("ALTER TABLE `tabHD Customer` DROP COLUMN `erpnext_customer`")
    frappe.clear_cache(doctype="HD Customer")
