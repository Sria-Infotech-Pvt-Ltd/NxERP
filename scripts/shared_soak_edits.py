"""Soak load for the shared layer: about one owner edit per second for a set time, on a THROWAWAY site. Never run on production.

    cd /home/frappe/frappe-bench/sites && ../env/bin/python /path/shared_soak_edits.py SITE SECONDS OUTFILE

Each second it saves one Customer with a new marker in `customer_name` (a free-text field in the customer contract), so each save is a
real document event that the outbox captures, and writes `n,customer,committed_at_epoch` to OUTFILE. Every 60th second it also creates and
later deletes a Contact, to exercise inserts and tombstones. `scripts/shared_soak_watch.py`'s counterpart (the watcher) records when each marker
became visible in the shared layer.
"""

import sys
import time

import frappe


def main(site: str, seconds: int, outfile: str) -> None:
	frappe.init(site=site)
	frappe.connect()
	frappe.set_user("Administrator")
	customers = frappe.get_all("Customer", pluck="name", limit=3)
	made = []
	start = time.time()
	with open(outfile, "w", encoding="ascii") as out:
		n = 0
		while time.time() - start < seconds:
			tick = time.time()
			n += 1
			name = customers[n % len(customers)]
			doc = frappe.get_doc("Customer", name)
			doc.customer_name = f"Soak {n:06d}"
			doc.save(ignore_permissions=True)
			if n % 60 == 0:
				contact = frappe.get_doc({"doctype": "Contact", "first_name": f"Soak{n}"}).insert(ignore_permissions=True)
				made.append(contact.name)
				if len(made) > 1:
					frappe.delete_doc("Contact", made.pop(0), ignore_permissions=True, force=True)
			frappe.db.commit()
			out.write(f"{n},{name},{time.time():.3f}\n")
			out.flush()
			time.sleep(max(0.0, 1.0 - (time.time() - tick)))
		for leftover in made:
			frappe.delete_doc("Contact", leftover, ignore_permissions=True, force=True)
		frappe.db.commit()
	frappe.destroy()


if __name__ == "__main__":
	main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
