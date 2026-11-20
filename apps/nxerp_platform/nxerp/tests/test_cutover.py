"""The cutover tools (8A): fake data only. Nothing here talks to a real site; nothing commits (the tools skip the
commit under tests) and the framework rolls the test data back."""

import io
import json
import os
import stat
import tempfile
from contextlib import redirect_stdout
from unittest.mock import patch

import frappe
from cryptography.fernet import Fernet
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime
from frappe.utils.password import check_password, decrypt, encrypt, update_password

from nxerp import cutover

SECRET = "Fake-pass-9d7e!"
OTP_SECRET = "JBSWY3DPEHPK3PXP"


def _run(fn, *args, **kwargs):
	"""Call a tool and return (result, everything it printed)."""
	buffer = io.StringIO()
	with redirect_stdout(buffer):
		result = fn(*args, **kwargs)
	return result, buffer.getvalue()


class CutoverCase(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._saved = frappe.conf.get(cutover.ALLOWED_KEY)
		frappe.conf[cutover.ALLOWED_KEY] = 1
		self.dir = tempfile.mkdtemp(prefix="nxerp-cutover-test-")
		self.addCleanup(self._restore)

	def _restore(self):
		if self._saved is None:
			frappe.conf.pop(cutover.ALLOWED_KEY, None)
		else:
			frappe.conf[cutover.ALLOWED_KEY] = self._saved
		os.environ.pop(cutover.SOURCE_KEY_ENV, None)

	def path(self, name):
		return os.path.join(self.dir, name)

	def make_user(self, label="cutover"):
		email = f"{label}-{frappe.generate_hash(length=6)}@example.test"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Fake",
				"send_welcome_email": 0,
				"roles": [{"role": "System Manager"}],
			}
		).insert(ignore_permissions=True)
		update_password(user.name, SECRET)
		frappe.db.set_default(user.name + "_otpsecret", encrypt(OTP_SECRET), parent="__2fa")
		return user.name


class TestGate(CutoverCase):
	def test_every_function_refuses_without_the_switch(self):
		frappe.conf.pop(cutover.ALLOWED_KEY, None)
		calls = [
			(cutover.identity_export, (self.path("i.json"),)),
			(cutover.identity_import, (self.path("i.json"),)),
			(cutover.prune_helpdesk_site, ()),
			(cutover.reconcile, (self.path("s.json"),)),
			(cutover.reserve_naming_series_offset, (100,)),
			(cutover.delta_export, ("2000-01-01 00:00:00", self.path("d"))),
			(cutover.delta_import, (self.path("d"),)),
			(cutover.feed_head, ()),
		]
		for fn, args in calls:
			with self.subTest(fn.__name__), self.assertRaises(frappe.PermissionError):
				fn(*args)
		self.assertFalse(os.path.exists(self.path("i.json")), "a refused export must write nothing")


class TestIdentity(CutoverCase):
	def test_round_trip_keeps_password_and_two_factor_and_logs_no_secret(self):
		user = self.make_user()
		file = self.path("identity.json")
		counts, out = _run(cutover.identity_export, file)
		self.assertGreaterEqual(counts["users"], 1)
		self.assertEqual(stat.S_IMODE(os.stat(file).st_mode), 0o600)

		# lose the login on this side, then bring it back from the file
		frappe.db.sql("DELETE FROM `__Auth` WHERE doctype='User' AND name=%s", (user,))
		frappe.db.sql(
			"DELETE FROM tabDefaultValue WHERE parent='__2fa' AND defkey=%s", (user + "_otpsecret",)
		)
		os.environ[cutover.SOURCE_KEY_ENV] = frappe.local.conf.encryption_key
		_, out2 = _run(cutover.identity_import, file, admin_password="keep")

		self.assertEqual(check_password(user, SECRET), user)
		restored = frappe.db.get_default(user + "_otpsecret", parent="__2fa")
		self.assertEqual(decrypt(restored, key=f"{user}.otpsecret"), OTP_SECRET)
		for text in (out, out2):
			self.assertNotIn(SECRET, text)
			self.assertNotIn(OTP_SECRET, text)
			self.assertNotIn(user, text)

	def test_a_different_source_key_is_re_encrypted_for_this_site(self):
		user = self.make_user()
		file = self.path("identity.json")
		_run(cutover.identity_export, file)
		other_key = Fernet.generate_key().decode()
		with open(file, encoding="utf-8") as handle:
			data = json.load(handle)
		for row in data["two_factor"]:
			if row["defkey"] == user + "_otpsecret":
				row["defvalue"] = encrypt(OTP_SECRET, encryption_key=other_key)
		data["auth"] = [a for a in data["auth"] if not a["encrypted"]]
		data["two_factor"] = [r for r in data["two_factor"] if r["defkey"] == user + "_otpsecret"]
		with open(file, "w", encoding="utf-8") as handle:
			json.dump(data, handle)
		os.environ[cutover.SOURCE_KEY_ENV] = other_key
		_run(cutover.identity_import, file, admin_password="keep")
		restored = frappe.db.get_default(user + "_otpsecret", parent="__2fa")
		self.assertEqual(decrypt(restored, key=f"{user}.otpsecret"), OTP_SECRET)

	def test_encrypted_secrets_without_the_source_key_are_refused(self):
		self.make_user()
		file = self.path("identity.json")
		_run(cutover.identity_export, file)
		os.environ.pop(cutover.SOURCE_KEY_ENV, None)
		with self.assertRaises(frappe.ValidationError):
			cutover.identity_import(file, admin_password="keep")

	def test_import_is_idempotent(self):
		self.make_user()
		file = self.path("identity.json")
		_run(cutover.identity_export, file)
		os.environ[cutover.SOURCE_KEY_ENV] = frappe.local.conf.encryption_key
		_run(cutover.identity_import, file, admin_password="keep")
		again, _ = _run(cutover.identity_import, file, admin_password="keep")
		self.assertEqual(again["rows"]["new"], 0)
		self.assertEqual(again["rows"]["updated"], 0)

	def test_a_different_administrator_password_is_refused_and_nothing_is_written(self):
		user = self.make_user()
		file = self.path("identity.json")
		_run(cutover.identity_export, file)
		with open(file, encoding="utf-8") as handle:
			data = json.load(handle)
		for row in data["auth"]:
			if row["name"] == "Administrator" and row["fieldname"] == "password":
				row["password"] = "$argon2id$different"
		data["auth"] = [
			a for a in data["auth"] if a["name"] in ("Administrator", user) and not a["encrypted"]
		]
		with open(file, "w", encoding="utf-8") as handle:
			json.dump(data, handle)
		before = frappe.db.sql(
			"SELECT password FROM `__Auth` WHERE doctype='User' AND name='Administrator' AND fieldname='password'"
		)
		os.environ[cutover.SOURCE_KEY_ENV] = frappe.local.conf.encryption_key
		with self.assertRaises(frappe.ValidationError):
			cutover.identity_import(file)
		after = frappe.db.sql(
			"SELECT password FROM `__Auth` WHERE doctype='User' AND name='Administrator' AND fieldname='password'"
		)
		self.assertEqual(before, after)
		cutover.identity_import(
			file, admin_password="keep"
		)  # leaving the target Administrator alone is allowed
		self.assertEqual(
			before,
			frappe.db.sql(
				"SELECT password FROM `__Auth` WHERE doctype='User' AND name='Administrator' AND fieldname='password'"
			),
		)


class TestPrune(CutoverCase):
	def erp_rows(self):
		"""One row of each kind attached to an ERP DocType, one attached to a Helpdesk DocType, one attached to nothing."""
		ids = {}
		for label, reference in (("erp", "Customer"), ("hd", "HD Ticket"), ("none", None)):
			# straight into the table: the ToDo controller would look up the (fake) referenced document
			todo = frappe.get_doc(
				{
					"doctype": "ToDo",
					"name": frappe.generate_hash(length=10),
					"description": f"fake {label}",
					"reference_type": reference,
					"reference_name": "FAKE-1" if reference else None,
					"allocated_to": "Administrator",
					"owner": "Administrator",
					"status": "Open",
				}
			)
			todo.db_insert()
			ids[label] = todo.name
		contact = frappe.get_doc({"doctype": "Contact", "first_name": "FakeErp"}).insert(
			ignore_permissions=True
		)
		frappe.get_doc(
			{
				"doctype": "Dynamic Link",
				"name": frappe.generate_hash(length=10),
				"parent": contact.name,
				"parenttype": "Contact",
				"parentfield": "links",
				"link_doctype": "Customer",
				"link_name": "FAKE-1",
			}
		).db_insert()
		ids["contact_erp"] = contact.name
		plain = frappe.get_doc({"doctype": "Contact", "first_name": "FakePlain"}).insert(
			ignore_permissions=True
		)
		ids["contact_plain"] = plain.name
		return ids

	def test_dry_run_changes_nothing(self):
		ids = self.erp_rows()
		before = frappe.db.count("ToDo")
		result, out = _run(cutover.prune_helpdesk_site)
		self.assertTrue(result["dry_run"])
		self.assertGreaterEqual(result["counts"]["ToDo"], 1)
		self.assertEqual(frappe.db.count("ToDo"), before)
		self.assertTrue(frappe.db.exists("Contact", ids["contact_erp"]))
		self.assertIn("DRY RUN", out)

	def test_apply_refuses_while_erpnext_is_installed(self):
		with patch("nxerp.cutover._installed_apps", return_value=["frappe", "erpnext", "helpdesk"]):
			with self.assertRaises(frappe.ValidationError):
				cutover.prune_helpdesk_site(dry_run=0)

	def test_apply_removes_only_erp_attached_rows(self):
		ids = self.erp_rows()
		with patch("nxerp.cutover._installed_apps", return_value=["frappe", "helpdesk", "nxerp"]):
			result, _ = _run(cutover.prune_helpdesk_site, dry_run=0)
		self.assertFalse(result["dry_run"])
		self.assertFalse(frappe.db.exists("ToDo", ids["erp"]))
		self.assertTrue(frappe.db.exists("ToDo", ids["hd"]))
		self.assertTrue(frappe.db.exists("ToDo", ids["none"]))
		self.assertFalse(frappe.db.exists("Contact", ids["contact_erp"]))
		self.assertTrue(frappe.db.exists("Contact", ids["contact_plain"]))
		self.assertFalse(frappe.db.exists("Dynamic Link", {"parent": ids["contact_erp"]}))


class TestReconcile(CutoverCase):
	def snap(self, **over):
		base = {
			"format": 1,
			"doctypes": {"HD Ticket": {"count": 2, "hash": "h", "keys": ["a1", "b2"]}},
			"attached": {"Communication": {"HD Ticket": 3}, "File": {"rows": 1}},
			"files": {"f1": "sha-1"},
			"message_ids": ["m1", "m2"],
			"duplicate_message_ids": [],
			"status": {"Open": 2},
			"sla": {"a1": "Fulfilled", "b2": "Fulfilled"},
		}
		base.update(over)
		return base

	def test_identical_snapshots_pass(self):
		problems, allowed = cutover.compare_snapshots(self.snap(), self.snap())
		self.assertEqual((problems, allowed), ([], 0))

	def test_a_missing_row_is_named_by_key(self):
		target = self.snap(doctypes={"HD Ticket": {"count": 1, "hash": "x", "keys": ["a1"]}})
		problems, _ = cutover.compare_snapshots(self.snap(), target)
		self.assertIn("b2", problems[0])
		self.assertIn("missing on target", problems[0])

	def test_a_changed_file_hash_fails(self):
		problems, _ = cutover.compare_snapshots(self.snap(), self.snap(files={"f1": "sha-2"}))
		self.assertTrue(any("content hash differs" in p for p in problems))

	def test_a_duplicate_message_id_fails(self):
		problems, _ = cutover.compare_snapshots(self.snap(), self.snap(duplicate_message_ids=["m2"]))
		self.assertTrue(any("duplicated on target" in p for p in problems))

	def test_a_missing_message_id_fails(self):
		problems, _ = cutover.compare_snapshots(self.snap(), self.snap(message_ids=["m1"]))
		self.assertTrue(any("message id" in p and "missing" in p for p in problems))

	def test_only_the_sla_status_is_tolerated(self):
		target = self.snap(sla={"a1": "Failed", "b2": "Fulfilled"})
		problems, allowed = cutover.compare_snapshots(self.snap(), target)
		self.assertEqual((problems, allowed), ([], 1))
		problems, _ = cutover.compare_snapshots(self.snap(), self.snap(status={"Open": 1, "Closed": 1}))
		self.assertTrue(problems)

	def test_real_snapshot_and_report_hold_no_names_or_values(self):
		name = "FAKE-TYPE-" + frappe.generate_hash(length=6)
		frappe.get_doc({"doctype": "HD Ticket Type", "name": name}).insert(ignore_permissions=True)
		first, second = self.path("a.json"), self.path("b.json")
		_run(cutover.reconcile, first)
		_run(cutover.reconcile, second)
		self.assertEqual(stat.S_IMODE(os.stat(first).st_mode), 0o600)
		with open(first, encoding="utf-8") as handle:
			self.assertNotIn(name, handle.read())
		result, _ = _run(cutover.reconcile, first, "compare", other=second, report=self.path("r.md"))
		self.assertEqual(result["result"], "PASS")
		with open(self.path("r.md"), encoding="utf-8") as handle:
			report = handle.read()
		self.assertIn("RESULT: PASS", report)
		self.assertNotIn(name, report)
		frappe.get_doc("HD Ticket Type", name).delete(ignore_permissions=True)
		_run(cutover.reconcile, second)
		result, _ = _run(cutover.reconcile, first, "compare", other=second, report=self.path("r2.md"))
		self.assertEqual(result["result"], "FAIL")
		with open(self.path("r2.md"), encoding="utf-8") as handle:
			self.assertIn("RESULT: FAIL", handle.read())


class TestNamingSeries(CutoverCase):
	def test_the_counter_only_goes_up(self):
		result, _ = _run(cutover.reserve_naming_series_offset, 50000)
		self.assertEqual(result["counter"], 50000)
		result, _ = _run(cutover.reserve_naming_series_offset, 100)
		self.assertEqual(result["counter"], 50000)
		again, _ = _run(cutover.reserve_naming_series_offset, 50000)
		self.assertEqual(again["counter"], 50000)


class TestNamingGap(CutoverCase):
	def test_a_gap_is_added_to_the_current_counter(self):
		_run(cutover.reserve_naming_series_offset, 70000)
		result, _ = _run(cutover.reserve_naming_series_offset, gap=1000)
		self.assertEqual(result["counter"], 71000)
		again, _ = _run(cutover.reserve_naming_series_offset, 70500)
		self.assertEqual(again["counter"], 71000)


class TestDelta(CutoverCase):
	def test_import_adds_skips_and_reports_conflicts_but_never_overwrites(self):
		since = add_to_date(now_datetime(), minutes=-1).strftime("%Y-%m-%d %H:%M:%S")
		name = "FAKE-DELTA-" + frappe.generate_hash(length=6)
		frappe.get_doc({"doctype": "HD Ticket Type", "name": name, "description": "first"}).insert(
			ignore_permissions=True
		)
		bundle = self.path("bundle")
		counts, out = _run(cutover.delta_export, since, bundle)
		self.assertGreaterEqual(counts["HD Ticket Type"], 1)
		self.assertNotIn(name, out)

		skipped, _ = _run(cutover.delta_import, bundle)
		self.assertEqual(skipped["counts"]["conflicts"], 0)
		self.assertGreaterEqual(skipped["counts"]["skipped"], 1)

		frappe.db.set_value("HD Ticket Type", name, "description", "changed on the source")
		conflict, out = _run(cutover.delta_import, bundle)
		self.assertGreaterEqual(conflict["counts"]["conflicts"], 1)
		self.assertEqual(frappe.db.get_value("HD Ticket Type", name, "description"), "changed on the source")
		self.assertNotIn(name, out)

		frappe.db.delete("HD Ticket Type", {"name": name})
		added, _ = _run(cutover.delta_import, bundle)
		self.assertGreaterEqual(added["counts"]["added"], 1)
		self.assertEqual(frappe.db.get_value("HD Ticket Type", name, "description"), "first")

	def test_a_file_travels_with_its_row_and_is_not_overwritten(self):
		since = add_to_date(now_datetime(), minutes=-1).strftime("%Y-%m-%d %H:%M:%S")
		name = "FAKE-DELTA-" + frappe.generate_hash(length=6)
		frappe.get_doc({"doctype": "HD Ticket Type", "name": name}).insert(ignore_permissions=True)
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"fake-{frappe.generate_hash(length=6)}.txt",
				"attached_to_doctype": "HD Ticket Type",
				"attached_to_name": name,
				"content": "hello fake",
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		bundle = self.path("bundle")
		_run(cutover.delta_export, since, bundle)
		self.assertTrue(os.path.exists(os.path.join(bundle, "files", file.name)))
		full = file.get_full_path()
		os.remove(full)
		frappe.db.delete("File", {"name": file.name})
		_run(cutover.delta_import, bundle)
		with open(full, encoding="utf-8") as handle:
			self.assertEqual(handle.read(), "hello fake")
		with open(full, "w", encoding="utf-8") as handle:
			handle.write("kept")
		_run(cutover.delta_import, bundle)
		with open(full, encoding="utf-8") as handle:
			self.assertEqual(handle.read(), "kept")
