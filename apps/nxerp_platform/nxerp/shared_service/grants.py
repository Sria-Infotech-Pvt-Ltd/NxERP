"""Consumer grants: which app may read which fields of which entity, kept in `consumer_grant`. No frappe.

The contracts' `consumers` sections are the only source. `sync` makes the table match them: it adds a missing grant, updates a changed
one and disables a grant the contract no longer lists. It can never widen a grant beyond the contract, because it only ever writes
what the contract says. Disabled rows stay (with `enabled = 0`) so the history of a grant is visible.
"""

import json

from nxerp.shared import registry


def desired_from_contracts(contracts: dict | None = None) -> dict:
	"""{(consumer_app, entity_type): {granted_fields, contract_version, tenant_id}} for every active contract."""
	contracts = contracts if contracts is not None else registry.load_contracts()
	desired = {}
	for entity_type, contract in contracts.items():
		if contract["status"] != "active":
			continue
		field_order = [f["shared"] for f in contract["fields"]]
		tenant = contract["tenant"]
		for app, fields in contract["consumers"].items():
			desired[(app, entity_type)] = {
				"granted_fields": [f for f in field_order if f in set(fields)],
				"contract_version": contract["contract_version"],
				"tenant_id": tenant["value"] if tenant["mode"] == "constant" else None,
			}
	return desired


def read_grants(conn, enabled_only: bool = True) -> list:
	"""Grant rows as dicts (`granted_fields` decoded to a list)."""
	with conn.cursor() as cur:
		if enabled_only:
			cur.execute(
				"SELECT consumer_app, entity_type, granted_fields, tenant_id, contract_version, enabled "
				"FROM consumer_grant WHERE enabled = 1 ORDER BY consumer_app, entity_type"
			)
		else:
			cur.execute(
				"SELECT consumer_app, entity_type, granted_fields, tenant_id, contract_version, enabled "
				"FROM consumer_grant ORDER BY consumer_app, entity_type"
			)
		rows = cur.fetchall()
	for row in rows:
		fields = row["granted_fields"]
		row["granted_fields"] = json.loads(fields) if isinstance(fields, str | bytes) else list(fields)
	conn.commit()
	return rows


def sync(conn, contracts: dict | None = None) -> dict:
	"""Make consumer_grant match the contracts. Returns counts."""
	desired = desired_from_contracts(contracts)
	existing = {(r["consumer_app"], r["entity_type"]): r for r in read_grants(conn, enabled_only=False)}
	added = updated = disabled = 0
	with conn.cursor() as cur:
		for key, want in desired.items():
			current = existing.get(key)
			same = (
				current is not None
				and current["enabled"] == 1
				and current["granted_fields"] == want["granted_fields"]
				and current["tenant_id"] == want["tenant_id"]
				and current["contract_version"] == want["contract_version"]
			)
			if same:
				continue
			cur.execute(
				"INSERT INTO consumer_grant (consumer_app, entity_type, granted_fields, tenant_id, contract_version, enabled, updated_at) "
				"VALUES (%s, %s, %s, %s, %s, 1, NOW(6)) ON DUPLICATE KEY UPDATE granted_fields = VALUES(granted_fields), "
				"tenant_id = VALUES(tenant_id), contract_version = VALUES(contract_version), enabled = 1, updated_at = NOW(6)",
				(
					key[0],
					key[1],
					json.dumps(want["granted_fields"]),
					want["tenant_id"],
					want["contract_version"],
				),
			)
			if current is None:
				added += 1
			else:
				updated += 1
		for key, current in existing.items():
			if key not in desired and current["enabled"] == 1:
				cur.execute(
					"UPDATE consumer_grant SET enabled = 0, updated_at = NOW(6) WHERE consumer_app = %s AND entity_type = %s",
					key,
				)
				disabled += 1
	conn.commit()
	return {"added": added, "updated": updated, "disabled": disabled}
