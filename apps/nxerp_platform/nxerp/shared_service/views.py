"""Per-consumer views over the shared entity tables, generated from the ownership contracts and the consumer grants. No frappe.

One view per (consumer app, entity): `v_<app>_<entity>`. Its columns are exactly the granted fields plus `entity_id`, `tenant_id`,
`source_modified` and `synced_at`; it hides tombstones (`deleted_at IS NULL`); and when the grant names a tenant it filters to
that tenant inside the view, so even a direct database reader (a report account) cannot see another tenant's rows. The Read
API adds its own `tenant_id = ?` for grants without a tenant.

A view is never written by hand: a field that is not in the contract, or not in the app's grant, is refused here, so a column
can only reach a consumer through a reviewed contract change.
"""

from nxerp.shared import registry
from nxerp.shared_service import accounts, sqlutil
from nxerp.shared_service.schema.generate_columns import table_name

SYSTEM_COLUMNS = ("entity_id", "tenant_id", "source_modified", "synced_at")


class ViewError(ValueError):
	"""A grant that the contracts do not allow."""


def view_name(app: str, entity_type: str) -> str:
	name = f"v_{app}_{entity_type}"
	sqlutil.ident(name)
	return name


def render_view(contract: dict, app: str, granted_fields: list, tenant: str | None = None) -> str:
	"""CREATE OR REPLACE VIEW for one grant. Raises ViewError when the contract does not allow it."""
	entity_type = contract["entity_type"]
	if contract["status"] != "active":
		raise ViewError(f"{entity_type}: the contract is not active, so nothing is shared")
	allowed_for_app = set(contract["consumers"].get(app, []))
	if not allowed_for_app:
		raise ViewError(f"{entity_type}: {app} is not a consumer in the contract")
	contract_fields = [f["shared"] for f in contract["fields"]]
	for field in granted_fields:
		if field not in contract_fields:
			raise ViewError(f"{entity_type}.{field}: not a field of the contract")
		if field not in allowed_for_app:
			raise ViewError(f"{entity_type}.{field}: the contract does not grant it to {app}")
	if not granted_fields:
		raise ViewError(f"{entity_type}: an empty grant for {app}")
	ordered = [
		field for field in contract_fields if field in set(granted_fields)
	]  # contract order, deterministic
	columns = [*SYSTEM_COLUMNS, *ordered]
	where = "`deleted_at` IS NULL"
	if tenant:
		where += f" AND `tenant_id` = {sqlutil.literal(tenant)}"
	return sqlutil.create_view(view_name(app, entity_type), columns, table_name(entity_type), where)


def render_all(grants: list, contracts: dict | None = None) -> dict:
	"""{view name: SQL} for enabled grant rows (`consumer_app`, `entity_type`, `granted_fields`, `tenant_id`)."""
	contracts = contracts if contracts is not None else registry.load_contracts()
	views = {}
	for grant in grants:
		contract = contracts.get(grant["entity_type"])
		if contract is None:
			raise ViewError(f"{grant['entity_type']}: no such contract")
		views[view_name(grant["consumer_app"], grant["entity_type"])] = render_view(
			contract, grant["consumer_app"], list(grant["granted_fields"]), grant.get("tenant_id")
		)
	return dict(sorted(views.items()))


def apply_views(conn, desired: dict, db: str, accounts_to_revoke: list | None = None) -> dict:
	"""Create or replace the desired views and drop the generated views that are no longer granted. Returns names only."""
	with conn.cursor() as cur:
		cur.execute(
			"SELECT TABLE_NAME AS name FROM information_schema.VIEWS WHERE TABLE_SCHEMA = %s AND TABLE_NAME LIKE 'v\\_%%'",
			(db,),
		)
		existing = {row["name"] for row in cur.fetchall()}
		for sql in desired.values():
			cur.execute(sql)
		dropped = sorted(existing - set(desired))
		for name in dropped:
			for account in (
				accounts_to_revoke or []
			):  # a stale privilege on a dropped view would return with a view of the same name
				accounts.revoke_everything(cur, db, name, account)
			cur.execute(f"DROP VIEW IF EXISTS {sqlutil.ident(name)}")  # nosec B608 - identifier validated
	conn.commit()
	return {"created_or_replaced": sorted(desired), "dropped": dropped}
