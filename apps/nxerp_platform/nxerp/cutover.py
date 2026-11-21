"""Cutover tools: copy the identity data, clean a cloned Helpdesk site, compare before and after, replay changes back.

Run with `bench --site SITE execute nxerp.cutover.<function> --kwargs '<json>'`. Every function

- refuses to run unless the site config has `nxerp_cutover_allowed = 1` (a person sets it on purpose, per site);
- is idempotent and prints counts only: no secret and no personal data reaches a log, a report or an error;
- stops at the first difference and names the KEY (a short hash), never a value.

The source site stays authoritative until decision point D: only `delta_import` (the rollback replay) writes to it.

How passwords and 2FA are stored (settles blueprint U9):
- `__Auth` row (User, name, `password`, encrypted 0) is a salted hash: portable between sites as it is.
- `__Auth` rows with encrypted 1 (a User's `api_secret`) and the 2FA secret (`tabDefaultValue`, parent `__2fa`, key
  `<user>_otpsecret`) are encrypted with the site's own `encryption_key`. The export keeps them as ciphertext; the
  import decrypts with the SOURCE key from the environment variable `NXERP_CUTOVER_SOURCE_ENCRYPTION_KEY` and
  encrypts again with the identity site's key. The key never goes into the file.
"""

import hashlib
import json
import os
import re
import zoneinfo
from datetime import date, datetime, timedelta
from decimal import Decimal

import frappe
from frappe.utils.password import decrypt, encrypt

ALLOWED_KEY = "nxerp_cutover_allowed"
SOURCE_KEY_ENV = "NXERP_CUTOVER_SOURCE_ENCRYPTION_KEY"
FORMAT_VERSION = 1

# apps whose DocTypes belong on the Helpdesk site, read from Module Def (never a hand-kept list of DocTypes)
KEEP_APPS = ("helpdesk", "nxerp")
# core DocTypes a Helpdesk site keeps references to besides its own
SHARED_KEEP = frozenset(
	{"User", "Role", "Contact", "Address", "Email Account", "Notification Log", "Note", "Event"}
)

# core tables that hang off other documents, and the column that names the DocType they hang off
ATTACHED = {
	"Communication": "reference_doctype",
	"Comment": "reference_doctype",
	"ToDo": "reference_type",
	"File": "attached_to_doctype",
	"Version": "ref_doctype",
	"Tag Link": "document_type",
}
LINKED = {"Contact", "Address"}  # parents of Dynamic Link rows

IDENTITY_TABLES = ("Role", "Role Profile", "User")
IDENTITY_CHILDREN = {  # table -> parenttype (children of a User or a Role Profile)
	"Has Role": ("User", "Role Profile"),
	"User Social Login": ("User",),
}
NEVER_COPY_USERS = ("Guest",)


# ----------------------------------------------------------------------------- guards and helpers


def _require_allowed():
	if not frappe.conf.get(ALLOWED_KEY):
		raise frappe.PermissionError(
			f"Cutover tools are off on this site. A person must set site config {ALLOWED_KEY} to 1 on purpose."
		)


def _commit():
	"""Commit, except under the test runner, which rolls its data back."""
	if not frappe.flags.in_test:
		frappe.db.commit()


def _key(value) -> str:
	"""A short stable hash of a name: enough to name the first difference, never a value."""
	return hashlib.sha256(str(value).encode()).hexdigest()[:16]


def _write_private(path: str, text: str):
	directory = os.path.dirname(os.path.abspath(path))
	os.makedirs(directory, exist_ok=True)
	fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	with os.fdopen(fd, "w", encoding="utf-8") as handle:
		handle.write(text)
	try:
		os.chmod(path, 0o600)
	except OSError:
		pass


def _plain(value):
	if isinstance(value, datetime | date):
		return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
	if isinstance(value, timedelta):
		return str(value)
	if isinstance(value, Decimal):
		return float(value)
	if isinstance(value, bytes):
		return value.decode("utf-8", "replace")
	return value


def _rows(table: str, where: str = "", values=()) -> list[dict]:
	rows = frappe.db.sql(f"SELECT * FROM `tab{table}` {where}", values, as_dict=True)
	return [{k: _plain(v) for k, v in row.items()} for row in rows]


def _upsert(table: str, row: dict) -> str:
	"""Insert or update one row, keeping its name and timestamps; only columns the target has. Returns 'new' or 'same' or 'updated'."""
	columns = set(frappe.db.get_table_columns(table))
	data = {k: v for k, v in row.items() if k in columns}
	existing = frappe.db.sql(f"SELECT * FROM `tab{table}` WHERE name = %s", (data["name"],), as_dict=True)
	if existing:
		current = {k: _plain(v) for k, v in existing[0].items() if k in data}
		if current == {k: _plain(v) for k, v in data.items()}:
			return "same"
	names = ", ".join(f"`{c}`" for c in data)
	marks = ", ".join(["%s"] * len(data))
	update = ", ".join(f"`{c}` = VALUES(`{c}`)" for c in data if c != "name")
	frappe.db.sql(
		f"INSERT INTO `tab{table}` ({names}) VALUES ({marks}) ON DUPLICATE KEY UPDATE {update}",
		tuple(data.values()),
	)
	return "updated" if existing else "new"


def _installed_apps() -> list:
	return frappe.get_installed_apps()


def _keep_doctypes() -> set:
	"""DocTypes that belong on a Helpdesk site: the ones its modules own, plus the shared core ones."""
	modules = frappe.get_all("Module Def", filters={"app_name": ["in", list(KEEP_APPS)]}, pluck="name")
	owned = (
		set(frappe.get_all("DocType", filters={"module": ["in", modules]}, pluck="name"))
		if modules
		else set()
	)
	return owned | SHARED_KEEP


def _helpdesk_doctypes(parents_only=True) -> list:
	modules = frappe.get_all("Module Def", filters={"app_name": "helpdesk"}, pluck="name")
	if not modules:
		return []
	filters = {"module": ["in", modules]}
	if parents_only:
		filters.update({"istable": 0, "issingle": 0})
	return sorted(frappe.get_all("DocType", filters=filters, pluck="name"))


# ----------------------------------------------------------------------------- identity


def identity_export(path: str):
	"""Write the identity data to a mode-600 file: User, Has Role, Role, Role Profile, User Social Login, and the
	User rows of __Auth and the 2FA defaults. Ciphertext stays ciphertext. Returns counts only."""
	_require_allowed()
	users = [r for r in _rows("User") if r["name"] not in NEVER_COPY_USERS]
	names = [r["name"] for r in users]
	data = {
		"format": FORMAT_VERSION,
		"Role": _rows("Role"),
		"Role Profile": _rows("Role Profile"),
		"User": users,
		"children": {},
		"auth": [],
		"two_factor": [],
	}
	for table, parents in IDENTITY_CHILDREN.items():
		marks = ", ".join(["%s"] * len(parents))
		data["children"][table] = [
			r
			for r in _rows(table, f"WHERE parenttype IN ({marks})", tuple(parents))
			if r["parent"] in names or r["parenttype"] == "Role Profile"
		]
	if names:
		marks = ", ".join(["%s"] * len(names))
		data["auth"] = frappe.db.sql(
			"SELECT `name`, `fieldname`, `password`, `encrypted` FROM `__Auth` "
			f"WHERE `doctype` = 'User' AND `name` IN ({marks})",
			tuple(names),
			as_dict=True,
		)
	data["two_factor"] = frappe.db.sql(
		"SELECT `defkey`, `defvalue` FROM `tabDefaultValue` WHERE `parent` = '__2fa'", as_dict=True
	)
	_write_private(path, json.dumps(data, default=_plain))
	counts = {
		"roles": len(data["Role"]),
		"role_profiles": len(data["Role Profile"]),
		"users": len(users),
		"has_role": len(data["children"]["Has Role"]),
		"social_logins": len(data["children"]["User Social Login"]),
		"auth_rows": len(data["auth"]),
		"two_factor_rows": len(data["two_factor"]),
	}
	print("identity_export: " + json.dumps(counts))
	return counts


def identity_import(path: str, admin_password: str = "refuse"):
	"""Idempotent upsert into the identity site. Refuses (and writes nothing) when the target Administrator has a
	different password and `admin_password` is not "keep" (keep = leave the target Administrator password alone)."""
	_require_allowed()
	with open(path, encoding="utf-8") as handle:
		data = json.load(handle)
	if data.get("format") != FORMAT_VERSION:
		raise frappe.ValidationError("The identity file has an unknown format.")

	auth = data["auth"]
	source_key = os.environ.get(SOURCE_KEY_ENV)
	needs_key = any(a["encrypted"] for a in auth) or bool(data["two_factor"])
	if needs_key and not source_key:
		raise frappe.ValidationError(
			f"The file holds encrypted secrets. Set {SOURCE_KEY_ENV} to the source site's encryption key and run again."
		)

	incoming_admin = next(
		(a for a in auth if a["name"] == "Administrator" and a["fieldname"] == "password"), None
	)
	keep_admin = admin_password == "keep"
	if incoming_admin and not keep_admin:
		current = frappe.db.sql(
			"SELECT `password` FROM `__Auth` WHERE `doctype`='User' AND `name`='Administrator' AND `fieldname`='password'"
		)
		if current and current[0][0] != incoming_admin["password"]:
			raise frappe.ValidationError(
				"The identity site's Administrator password differs from the file's. Nothing was imported. "
				'Re-run with admin_password="keep" to leave the identity Administrator password as it is.'
			)

	counts = {"new": 0, "updated": 0, "same": 0}

	def note(result):
		counts[result] += 1

	for table in IDENTITY_TABLES:
		for row in data[table]:
			note(_upsert(table, row))

	imported_users = [r["name"] for r in data["User"]]
	for table, rows in data["children"].items():
		wanted = {r["name"] for r in rows}
		for row in rows:
			note(_upsert(table, row))
		# a child row removed on the source is removed here too, so the grant lists are equal afterwards
		parents = sorted({r["parent"] for r in rows} | set(imported_users))
		if parents:
			marks = ", ".join(["%s"] * len(parents))
			stale = frappe.db.sql(
				f"SELECT name FROM `tab{table}` WHERE parenttype = 'User' AND parent IN ({marks})",
				tuple(parents),
				pluck=True,
			)
			for name in set(stale) - wanted:
				frappe.db.delete(table, {"name": name})

	for row in auth:
		if row["name"] == "Administrator" and keep_admin and row["fieldname"] == "password":
			continue
		secret = row["password"]
		if row["encrypted"]:
			secret = encrypt(decrypt(secret, encryption_key=source_key))
		frappe.db.sql(
			"INSERT INTO `__Auth` (`doctype`,`name`,`fieldname`,`password`,`encrypted`) VALUES ('User',%s,%s,%s,%s) "
			"ON DUPLICATE KEY UPDATE `password`=VALUES(`password`), `encrypted`=VALUES(`encrypted`)",
			(row["name"], row["fieldname"], secret, row["encrypted"]),
		)

	for row in data["two_factor"]:
		value = row["defvalue"]
		if row["defkey"].endswith("_otpsecret") and value:
			value = encrypt(decrypt(value, encryption_key=source_key))
		frappe.db.set_default(row["defkey"], value, parent="__2fa")

	_commit()
	result = {"rows": counts, "auth_rows": len(auth), "two_factor_rows": len(data["two_factor"])}
	print("identity_import: " + json.dumps(result))
	return result


# ----------------------------------------------------------------------------- prune the cloned Helpdesk site


def _prune_plan(keep: set) -> dict:
	"""{table: [names to delete]}, built from the rows that hang off a DocType this site does not keep."""
	plan = {}
	keep_list = sorted(keep)
	marks = ", ".join(["%s"] * len(keep_list))
	for table, column in ATTACHED.items():
		plan[table] = frappe.db.sql(
			f"SELECT name FROM `tab{table}` WHERE IFNULL(`{column}`, '') <> '' AND `{column}` NOT IN ({marks})",
			tuple(keep_list),
			pluck=True,
		)
	plan["Dynamic Link"] = frappe.db.sql(
		f"SELECT name FROM `tabDynamic Link` WHERE IFNULL(link_doctype, '') <> '' AND link_doctype NOT IN ({marks})",
		tuple(keep_list),
		pluck=True,
	)
	# a Contact or Address goes only when it had links and every one of them points at a DocType we do not keep
	for parent in LINKED:
		plan[parent] = frappe.db.sql(
			f"""SELECT d.parent FROM `tabDynamic Link` d WHERE d.parenttype = %s GROUP BY d.parent
			HAVING SUM(d.link_doctype IN ({marks})) = 0""",
			(parent, *keep_list),
			pluck=True,
		)
	return plan


def prune_helpdesk_site(dry_run=1):
	"""After erpnext and payments are uninstalled from the cloned site, remove core rows that belong only to ERP
	documents. Dry run by default; writes counts per table. Apply refuses while erpnext is still installed."""
	_require_allowed()
	dry = str(dry_run).lower() not in ("0", "false", "no")
	installed = set(_installed_apps())
	if not dry and installed & {"erpnext", "payments"}:
		raise frappe.ValidationError(
			"Uninstall erpnext and payments from this site before pruning (apply refused)."
		)
	keep = _keep_doctypes()
	plan = _prune_plan(keep)
	counts = {table: len(names) for table, names in plan.items()}
	if not dry:
		for table in ("Contact", "Address"):
			for name in plan[table]:
				for child in {"Contact": ("Contact Email", "Contact Phone"), "Address": ()}[table]:
					frappe.db.delete(child, {"parent": name})
				frappe.db.delete("Dynamic Link", {"parent": name, "parenttype": table})
				frappe.db.delete(table, {"name": name})
		for table, names in plan.items():
			if table in LINKED:
				continue
			for chunk in _chunks(names, 500):
				frappe.db.delete(table, {"name": ["in", chunk]})
		_commit()
	print(f"prune_helpdesk_site ({'DRY RUN' if dry else 'APPLIED'}): " + json.dumps(counts))
	return {"dry_run": dry, "counts": counts}


def _chunks(items, size):
	for i in range(0, len(items), size):
		yield items[i : i + size]


# ----------------------------------------------------------------------------- reconcile


def _file_hash(row: dict) -> str:
	path = row.get("file_url") or ""
	if path.startswith("/private/files/") or path.startswith("/files/"):
		full = (
			frappe.get_site_path(path.lstrip("/"))
			if path.startswith("/private")
			else frappe.get_site_path("public", path.lstrip("/"))
		)
		if os.path.exists(full):
			digest = hashlib.sha256()
			with open(full, "rb") as handle:
				for block in iter(lambda: handle.read(1 << 20), b""):
					digest.update(block)
			return digest.hexdigest()
	return "missing" if path else "none"


def _snapshot() -> dict:
	hd = _helpdesk_doctypes()
	snap = {
		"format": FORMAT_VERSION,
		"doctypes": {},
		"attached": {},
		"files": {},
		"message_ids": [],
		"duplicate_message_ids": [],
		"sla": {},
	}
	for doctype in hd:
		names = frappe.get_all(doctype, pluck="name", limit_page_length=0)
		hashes = sorted(_key(n) for n in names)
		snap["doctypes"][doctype] = {
			"count": len(hashes),
			"hash": hashlib.sha256("".join(hashes).encode()).hexdigest()[:16],
			"keys": hashes,
		}
	if hd:
		marks = ", ".join(["%s"] * len(hd))
		for table, column in ATTACHED.items():
			if table == "File":
				continue
			rows = frappe.db.sql(
				f"SELECT `{column}`, COUNT(*) FROM `tab{table}` WHERE `{column}` IN ({marks}) GROUP BY 1",
				tuple(hd),
			)
			snap["attached"][table] = {r[0]: r[1] for r in rows}
		files = frappe.db.sql(
			f"SELECT name, file_url, content_hash FROM `tabFile` WHERE attached_to_doctype IN ({marks}) AND IFNULL(is_folder,0)=0",
			tuple(hd),
			as_dict=True,
		)
		snap["files"] = {_key(f.name): _file_hash(f) for f in files}
		snap["attached"]["File"] = {"rows": len(files)}
		ids = frappe.db.sql(
			f"SELECT message_id FROM `tabCommunication` WHERE reference_doctype IN ({marks}) AND IFNULL(message_id,'') <> ''",
			tuple(hd),
			pluck=True,
		)
		hashed = [_key(i) for i in ids]
		snap["message_ids"] = sorted(set(hashed))
		snap["duplicate_message_ids"] = sorted({h for h in hashed if hashed.count(h) > 1})
	if "HD Ticket" in hd:
		snap["status"] = dict(frappe.db.sql("SELECT status, COUNT(*) FROM `tabHD Ticket` GROUP BY status"))
		sla = frappe.db.sql("SELECT name, agreement_status FROM `tabHD Ticket`")
		snap["sla"] = {_key(n): s or "" for n, s in sla}
	return snap


def reconcile(
	snapshot_path: str, mode: str = "snapshot", other: str | None = None, report: str | None = None
):
	"""mode "snapshot": write per-DocType counts and name-set hashes, the file SHA-256 manifest and the message-id set
	for the Helpdesk DocTypes and the core rows attached to them (names hashed, no personal data).
	mode "compare": compare the snapshot at `snapshot_path` (source) with `other` (target); write a PASS or FAIL report
	to `report` (default: next to the target). Zero tolerance, except the SLA status of a ticket (one cycle)."""
	_require_allowed()
	if mode == "snapshot":
		snap = _snapshot()
		_write_private(snapshot_path, json.dumps(snap, default=_plain))
		summary = {
			"doctypes": len(snap["doctypes"]),
			"files": len(snap["files"]),
			"message_ids": len(snap["message_ids"]),
		}
		print("reconcile snapshot: " + json.dumps(summary))
		return summary
	if mode != "compare" or not other:
		raise frappe.ValidationError('mode must be "snapshot", or "compare" with other=<second snapshot>.')
	with open(snapshot_path, encoding="utf-8") as a, open(other, encoding="utf-8") as b:
		source, target = json.load(a), json.load(b)
	problems, allowed = compare_snapshots(source, target)
	report = report or os.path.splitext(other)[0] + "-report.md"
	lines = ["# Reconcile report", "", f"RESULT: {'FAIL' if problems else 'PASS'}", ""]
	lines += ["| Check | Source | Target |", "| --- | --- | --- |"]
	for doctype, info in sorted(source["doctypes"].items()):
		t = target["doctypes"].get(doctype, {"count": "missing"})
		lines.append(f"| {doctype} count | {info['count']} | {t['count']} |")
	lines += ["", f"SLA status differences allowed (one cycle): {allowed}", ""]
	if problems:
		lines += ["## First differences (keys are hashes, never values)", ""] + [
			f"- {p}" for p in problems[:50]
		]
	_write_private(report, "\n".join(lines) + "\n")
	print(f"reconcile compare: {'FAIL' if problems else 'PASS'}; report at {report}")
	return {
		"result": "FAIL" if problems else "PASS",
		"problems": problems,
		"sla_allowed": allowed,
		"report": report,
	}


def compare_snapshots(source: dict, target: dict):
	"""([first differences], number of SLA-status differences tolerated). Order of checks decides what is reported first."""
	problems = []
	for doctype, info in sorted(source["doctypes"].items()):
		t = target["doctypes"].get(doctype)
		if t is None:
			problems.append(f"{doctype}: missing on target")
		elif info["count"] != t["count"] or info["hash"] != t["hash"]:
			missing = sorted(set(info["keys"]) - set(t["keys"]))
			extra = sorted(set(t["keys"]) - set(info["keys"]))
			first = (missing or extra or ["?"])[0]
			problems.append(
				f"{doctype}: source {info['count']} vs target {t['count']}; first differing key {first} "
				f"({'missing on target' if missing else 'extra on target'})"
			)
	for table, groups in source["attached"].items():
		if groups != target["attached"].get(table):
			problems.append(f"{table} attached to Helpdesk documents: counts differ")
	for key, digest in sorted(source["files"].items()):
		if key not in target["files"]:
			problems.append(f"File {key}: missing on target")
		elif target["files"][key] != digest:
			problems.append(f"File {key}: content hash differs")
	for key in sorted(set(source["message_ids"]) - set(target["message_ids"])):
		problems.append(f"Communication message id {key}: missing on target")
		break
	new_duplicates = sorted(set(target["duplicate_message_ids"]) - set(source["duplicate_message_ids"]))
	if new_duplicates:
		problems.append(f"Communication message id {new_duplicates[0]}: duplicated on target")
	if source.get("status") != target.get("status"):
		problems.append("HD Ticket status counts differ")
	allowed = sum(
		1 for k, s in source.get("sla", {}).items() if k in target.get("sla", {}) and target["sla"][k] != s
	)
	return problems, allowed


# ----------------------------------------------------------------------------- naming series


def reserve_naming_series_offset(offset: int = 0, gap: int = 0):
	"""Raise the HD Ticket counter so a new ticket on the new site cannot reuse a number the source may still issue
	after a rollback. Never lowers the counter. `gap` asks for "the current counter plus gap" (the cutover script uses it)."""
	_require_allowed()
	offset = int(offset)
	gap = int(gap)
	autoname = frappe.get_meta("HD Ticket").autoname or ""
	series = autoname.split("#")[0].rstrip(".")
	if autoname.startswith("format:") or not autoname:
		raise frappe.ValidationError("HD Ticket does not use a numbered series here; nothing to reserve.")
	row = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name = %s", (series,))
	current = int(row[0][0]) if row else None
	if gap:
		offset = max(offset, (current or 0) + gap)
	if current is None:
		frappe.db.sql("INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)", (series, offset))
		result = offset
	elif current < offset:
		frappe.db.sql("UPDATE `tabSeries` SET current = %s WHERE name = %s", (offset, series))
		result = offset
	else:
		result = current
	_commit()
	print(f"reserve_naming_series_offset: counter is {result} (asked {offset})")
	return {"counter": result}


# ----------------------------------------------------------------------------- delta (the rollback replay)


def _delta_doctypes() -> list:
	return _helpdesk_doctypes()


def site_time(since: str) -> str:
	"""A timestamp as the database stores it. Frappe stores `modified` in the site's own timezone, while `cutover.sh freeze` prints T0 in UTC
	(`...Z`): a timestamp with `Z` or an offset is converted to the site timezone, a plain one is taken as site time already. Getting this
	wrong would skip (site behind UTC) or repeat (site ahead) the first hours of changes."""
	text = str(since).strip().replace("T", " ")
	zoned = text.endswith("Z") or re.search(r"\d[+-]\d\d:?\d\d$", text)
	if not zoned:
		return text
	stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
	local = stamp.astimezone(zoneinfo.ZoneInfo(frappe.utils.get_system_timezone()))
	return local.strftime("%Y-%m-%d %H:%M:%S")


def delta_export(since: str, path: str):
	"""Every Helpdesk DocType plus Communication, File (rows and files), Comment and ToDo created or modified after
	`since` (a timestamp), into a directory bundle: bundle.json and files/. Counts only on screen."""
	_require_allowed()
	since = site_time(since)
	hd = _delta_doctypes()
	bundle = {"format": FORMAT_VERSION, "since": since, "docs": []}
	counts = {}
	os.makedirs(os.path.join(path, "files"), exist_ok=True)
	for doctype in hd:
		for name in frappe.get_all(
			doctype, filters={"modified": [">", since]}, pluck="name", limit_page_length=0
		):
			bundle["docs"].append(
				frappe.get_doc(doctype, name).as_dict(convert_dates_to_str=True, no_nulls=False)
			)
			counts[doctype] = counts.get(doctype, 0) + 1
	if hd:
		for doctype, column in (
			("Communication", "reference_doctype"),
			("Comment", "reference_doctype"),
			("ToDo", "reference_type"),
			("File", "attached_to_doctype"),
			("Tag Link", "document_type"),
		):
			for name in frappe.get_all(
				doctype,
				filters={column: ["in", hd], "modified": [">", since]},
				pluck="name",
				limit_page_length=0,
			):
				doc = frappe.get_doc(doctype, name)
				bundle["docs"].append(doc.as_dict(convert_dates_to_str=True, no_nulls=False))
				counts[doctype] = counts.get(doctype, 0) + 1
				if doctype == "File" and doc.file_url and not doc.is_folder:
					source = doc.get_full_path()
					if os.path.exists(source):
						with open(source, "rb") as src:
							content = src.read()
						target = os.path.join(path, "files", doc.name)
						fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
						with os.fdopen(fd, "wb") as out:
							out.write(content)
	# a Tag Link points at a Tag: bring the tags it uses, so the link means something in the source
	for tag in sorted({d["tag"] for d in bundle["docs"] if d["doctype"] == "Tag Link" and d.get("tag")}):
		if frappe.db.exists("Tag", tag):
			bundle["docs"].append(
				frappe.get_doc("Tag", tag).as_dict(convert_dates_to_str=True, no_nulls=False)
			)
			counts["Tag"] = counts.get("Tag", 0) + 1
	_write_private(os.path.join(path, "bundle.json"), json.dumps(bundle, default=_plain))
	print("delta_export: " + json.dumps(counts))
	return counts


def _canonical(doc: dict) -> str:
	return json.dumps(_normalise(doc), sort_keys=True, default=_plain)


def _normalise(value):
	if isinstance(value, dict):
		return {
			k: _normalise(v)
			for k, v in value.items()
			if k not in ("__islocal", "__unsaved", "docstatus_label") and v not in (None, "")
		}
	if isinstance(value, list):
		return [_normalise(v) for v in value]
	value = _plain(value)
	return str(value) if isinstance(value, float) else value


def delta_import(path: str):
	"""Replay a bundle into the site. Policy: a document that does not exist is added (without hooks, emails or
	notifications, names and timestamps kept); one that is identical is skipped; one that is different is REPORTED,
	never overwritten. Returns counts and the conflict keys."""
	_require_allowed()
	with open(os.path.join(path, "bundle.json"), encoding="utf-8") as handle:
		bundle = json.load(handle)
	counts = {"added": 0, "skipped": 0, "conflicts": 0}
	conflicts = []
	for raw in bundle["docs"]:
		doctype, name = raw["doctype"], raw["name"]
		if frappe.db.exists(doctype, name):
			current = frappe.get_doc(doctype, name).as_dict(convert_dates_to_str=True, no_nulls=False)
			if _canonical(current) == _canonical(raw):
				counts["skipped"] += 1
			else:
				counts["conflicts"] += 1
				conflicts.append(f"{doctype} {_key(name)}")
			continue
		doc = frappe.get_doc(raw)
		doc.flags.ignore_permissions = True
		doc.flags.in_import = True
		doc.db_insert()
		for child in doc.get_all_children():
			child.db_insert()
		_restore_hidden_columns(raw)
		if doctype == "File" and doc.file_url and not doc.is_folder:
			_restore_file(path, doc)
		counts["added"] += 1
	_commit()
	print(
		"delta_import: "
		+ json.dumps(counts)
		+ (" conflicts: " + ", ".join(conflicts[:20]) if conflicts else "")
	)
	return {"counts": counts, "conflicts": conflicts}


HIDDEN_COLUMNS = ("_user_tags", "_comments", "_assign", "_liked_by")


def _restore_hidden_columns(raw: dict):
	"""The hidden columns Frappe keeps on every document table (tags, comment summary, assignment, likes): db_insert does not write them."""
	columns = set(frappe.db.get_table_columns(raw["doctype"]))
	values = {k: raw[k] for k in HIDDEN_COLUMNS if raw.get(k) and k in columns}
	if values:
		frappe.db.set_value(raw["doctype"], raw["name"], values, update_modified=False)


def _restore_file(bundle_path: str, doc):
	source = os.path.join(bundle_path, "files", doc.name)
	if not os.path.exists(source):
		return
	target = doc.get_full_path()
	if os.path.exists(target):
		return  # never overwrite an existing file
	os.makedirs(os.path.dirname(target), exist_ok=True)
	with open(source, "rb") as src, open(target, "wb") as out:
		out.write(src.read())


def feed_head() -> dict:
	"""The owner's feed head on this site: where the shared layer's rebuild starts after a move."""
	_require_allowed()
	from nxerp.shared import feed

	head = feed.feed_head()
	print("feed_head: " + json.dumps(head))
	return head
