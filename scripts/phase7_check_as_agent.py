"""Run a Helpdesk shared-data action AS the fake Helpdesk agent (staging only): `bench --site hd.example.test execute nxerp.phase7_as_agent.run --kwargs "{...}"`."""

import json

import frappe

from helpdesk.integrations.shared import api

AGENT = "agent-helpdesk@example.test"


def run(action: str = "update_customer", fields=None, idempotency_key=None, hd_customer: str = "NXT Support Customer"):
	frappe.set_user(AGENT)
	try:
		result = getattr(api, action)(hd_customer, fields, idempotency_key=idempotency_key) if action != "get_customer_card" else api.get_customer_card(hd_customer)
	except Exception as exc:  # noqa: BLE001  (staging check: show the agent-facing message)
		result = {"raised": type(exc).__name__, "message": str(exc)[:300]}
	finally:
		frappe.set_user("Administrator")
	print(json.dumps(result, default=str))
