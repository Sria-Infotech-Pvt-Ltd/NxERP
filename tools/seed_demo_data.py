"""Dev-only demo data for visual checks: tickets in every status/priority, tickets spread over the existing teams, a customer,
knowledge-base articles. Fake data only (example.test). Run in the bench container:

	bench --site nxerp.localhost console < /workspace/tools/seed_demo_data.py

Refuses to run unless developer_mode is on. Uses doctype names only (no app imports).
"""

import frappe

assert frappe.conf.developer_mode, "demo data is only for developer_mode sites"
frappe.set_user("Administrator")


def meta_options(doctype, fieldname):
	return [o for o in (frappe.get_meta(doctype).get_field(fieldname).options or "").split("\n") if o]


def make(doctype, **values):
	try:
		doc = frappe.get_doc({"doctype": doctype, **values})
		doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
		return doc
	except Exception as e:
		print(f"skip {doctype} {values.get('name') or values.get('subject') or ''}: {str(e)[:90]}")


statuses = [s.name for s in frappe.get_all("HD Ticket Status", fields=["name"])]
priorities = [p.name for p in frappe.get_all("HD Ticket Priority", fields=["name"])]
print("statuses", statuses, "priorities", priorities)

teams = [t.name for t in frappe.get_all("HD Team", fields=["name"])]
if not frappe.db.exists("HD Customer", "Seed Example Co"):
	make("HD Customer", customer_name="Seed Example Co", domain="example.test")

n = 0
for i, status in enumerate(statuses):
	for j, priority in enumerate(priorities):
		doc = make(
			"HD Ticket",
			subject=f"Seed ticket {status} / {priority}",
			description=f"Fake ticket for palette checks ({status}, {priority}).",
			raised_by="customer@example.test",
			status=status,
			priority=priority,
			agent_group=teams[(i + j) % len(teams)] if teams and (i + j) % 3 else None,
		)
		n += bool(doc)
print("tickets created", n)

if frappe.db.exists("DocType", "HD Article Category"):
	cat = make("HD Article Category", category_name="Seed Getting Started")
	if cat:
		for t in ("Seed: resetting your password", "Seed: connecting email", "Seed: understanding SLAs"):
			make("HD Article", title=t, category=cat.name, content=f"<p>{t}. Fake article body.</p>", status="Published")

frappe.db.commit()
print("done")
