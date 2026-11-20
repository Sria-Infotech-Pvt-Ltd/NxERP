"""Phase 6 staging rehearsal: runbook steps 6.3 to 6.9 and tests T7 and T8 on the Phase 5 stacks (identity `id`, app sites `hd` and `erp`).

Fake users and fake credentials only. Run from the repository root with the stacks up and `nxerp_site_role` set (steps 6.2):

    python scripts/rehearse_federation.py

Output lines are `PASS name`, `FAIL name detail` and `INFO name text`: statuses, names and counts, never a secret, token, cookie or password.
Secrets for the helpers travel in this process's environment and are forwarded into the containers by NAME (`docker exec -e NAME`).
"""

import json
import os
import re
import secrets
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spike_federation_flow as flow

DOMAIN = "example.test"
PORT = flow.PORT_IN_URL
ORIGIN = {
	"id": f"http://id.{DOMAIN}:{PORT}",
	"hd": f"http://hd.{DOMAIN}:{PORT}",
	"erp": f"http://erp.{DOMAIN}:{PORT}",
}
SITE = {s: f"{s}.{DOMAIN}" for s in ("id", "hd", "erp")}
flow.SITES.update(SITE)
APP_KEY = {"hd": "helpdesk", "erp": "erpnext"}
ACCESS_ROLE = {"hd": "NXERP Access: Helpdesk", "erp": "NXERP Access: ERPNext"}
USER, USER2 = "fed-user@example.test", "fed-drift@example.test"
PROVISIONER = f"svc-provisioner@{DOMAIN}"
RESULTS = {"PASS": 0, "FAIL": 0}


def line(kind: str, name: str, detail: str = "") -> None:
	RESULTS[kind] = RESULTS.get(kind, 0) + 1
	print(f"{kind} {name} {detail}".rstrip(), flush=True)


def check(name: str, ok: bool, detail: str = "") -> bool:
	line("PASS" if ok else "FAIL", name, "" if ok else detail)
	return ok


def info(name: str, text: str) -> None:
	print(f"INFO {name} {text}", flush=True)


def bench_env(stack: str, names: list, *args: str) -> str:
	"""bench for a stack with the named environment variables forwarded from this process (values never on a command line)."""
	command = ["docker", "exec", "-w", "/home/frappe/frappe-bench"]
	for name in names:
		command += ["-e", name]
	command += [f"nxerp-{stack}-backend-1", "bench", "--site", SITE[stack], *args]
	proc = subprocess.run(
		command, capture_output=True, text=True, check=False, env={**os.environ, "MSYS_NO_PATHCONV": "1"}
	)
	return proc.stdout


def parse_dict(text: str):
	"""The dict `bench execute` printed (JSON, or a Python literal), or None."""
	import ast

	for candidate in (text.strip(), *reversed(text.strip().splitlines())):
		for loader in (json.loads, ast.literal_eval):
			try:
				value = loader(candidate.strip())
			except ValueError, SyntaxError:
				continue
			if isinstance(value, dict):
				return value
	return None


def user_state(stack: str, email: str) -> dict:
	exists = flow.execute(stack, "frappe.db.exists", dt="User", dn=email)
	if not exists:
		return {"exists": False}
	row = (
		flow.execute(
			stack,
			"frappe.db.get_value",
			doctype="User",
			filters=email,
			fieldname=["enabled", "user_type"],
			as_dict=True,
		)
		or {}
	)
	roles = (
		flow.execute(
			stack,
			"frappe.get_all",
			doctype="Has Role",
			filters={"parent": email, "parenttype": "User"},
			pluck="role",
		)
		or []
	)
	return {"exists": True, "enabled": bool(row.get("enabled")), "roles": roles}


def run_process() -> dict:
	"""Deliver due rows now. The scheduler and a worker may be delivering too (one run at a time), so look again until the queue is empty."""
	import time

	last = {}
	for _ in range(12):
		out = flow.execute("id", "nxerp.federation.outbox.process")
		last = out if isinstance(out, dict) else {}
		pending = flow.execute(
			"id", "frappe.db.count", dt="NXERP Provisioning Outbox", filters={"status": "Pending"}
		)
		if str(pending).strip() == "0":
			return last
		time.sleep(5)
	return last


def main() -> int:
	password = secrets.token_urlsafe(18)
	sso_secret = {"helpdesk": secrets.token_urlsafe(36), "erpnext": secrets.token_urlsafe(36)}
	os.environ["NXERP_SSO_SECRET_HELPDESK"] = sso_secret["helpdesk"]
	os.environ["NXERP_SSO_SECRET_ERPNEXT"] = sso_secret["erpnext"]

	info("setup", "cleanup of an earlier rehearsal")
	for stack in ("id", "hd", "erp"):
		for email in (USER, USER2, PROVISIONER):
			if flow.execute(stack, "frappe.db.exists", dt="User", dn=email):
				flow.execute(
					stack, "frappe.delete_doc", doctype="User", name=email, force=1, ignore_permissions=True
				)
	for name in flow.execute("id", "frappe.get_all", doctype="OAuth Client", pluck="name") or []:
		flow.execute(
			"id", "frappe.delete_doc", doctype="OAuth Client", name=name, force=1, ignore_permissions=True
		)
	for name in flow.execute("id", "frappe.get_all", doctype="NXERP Peer", pluck="name") or []:
		flow.execute(
			"id", "frappe.delete_doc", doctype="NXERP Peer", name=name, force=1, ignore_permissions=True
		)
	for stack in ("hd", "erp"):
		if flow.execute(stack, "frappe.db.exists", dt="Social Login Key", dn="frappe"):
			flow.execute(
				stack,
				"frappe.delete_doc",
				doctype="Social Login Key",
				name="frappe",
				force=1,
				ignore_permissions=True,
			)
	flow.execute("id", "frappe.db.delete", doctype="NXERP Provisioning Outbox")
	for stack in ("id", "hd", "erp"):
		flow.execute(stack, "frappe.db.commit")

	# 6.3 the provisioning service user on each app site (fake; the API secret is kept in memory only)
	peers = {}
	for stack in ("hd", "erp"):
		flow.execute(
			stack,
			"frappe.client.insert",
			doc={
				"doctype": "User",
				"email": PROVISIONER,
				"first_name": "Provisioner",
				"send_welcome_email": 0,
				"roles": [{"role": "NXERP Provisioner"}],
			},
		)
		keys = flow.execute(stack, "frappe.core.doctype.user.user.generate_keys", user=PROVISIONER)
		api_key = flow.execute(
			stack, "frappe.db.get_value", doctype="User", filters=PROVISIONER, fieldname="api_key"
		)
		secret = (keys or {}).get("api_secret") if isinstance(keys, dict) else None
		check(
			f"6.3 {stack} service user has one role and an API key",
			bool(api_key and secret),
			"no key generated",
		)
		peers[stack] = (api_key, secret)
		roles = flow.execute(
			stack,
			"frappe.get_all",
			doctype="Has Role",
			filters={"parent": PROVISIONER, "parenttype": "User"},
			pluck="role",
		)
		check(
			f"6.3 {stack} service user holds exactly NXERP Provisioner",
			sorted(roles or []) == ["NXERP Provisioner"],
			str(roles),
		)

	# 6.4 the peers on the identity site
	for stack in ("hd", "erp"):
		api_key, secret = peers[stack]
		made = flow.execute(
			"id",
			"frappe.client.insert",
			doc={
				"doctype": "NXERP Peer",
				"app_key": APP_KEY[stack],
				"origin": ORIGIN[stack],
				"internal_url": f"http://{stack}-backend:8000",
				"site_name": SITE[stack],
				"api_key": api_key,
				"api_secret": secret,
				"enabled": 1,
			},
		)
		check(
			f"6.4 peer {APP_KEY[stack]} saved",
			isinstance(made, dict) and made.get("name") == APP_KEY[stack],
			str(made)[:80],
		)
	masked = flow.execute(
		"id", "frappe.db.get_value", doctype="NXERP Peer", filters="helpdesk", fieldname="api_secret"
	)
	check("6.4 the stored peer secret is not the secret", masked != peers["hd"][1], "")

	# 6.5 OAuth clients on the identity site (helper, secrets from the environment)
	out = bench_env(
		"id",
		["NXERP_SSO_SECRET_HELPDESK", "NXERP_SSO_SECRET_ERPNEXT"],
		"execute",
		"nxerp.federation.setup.configure_identity_site",
	)
	clients = parse_dict(out) or {}
	check("6.5 one OAuth client per peer", set(clients) == {"helpdesk", "erpnext"}, out[-200:])
	again = (
		parse_dict(
			bench_env(
				"id",
				["NXERP_SSO_SECRET_HELPDESK", "NXERP_SSO_SECRET_ERPNEXT"],
				"execute",
				"nxerp.federation.setup.configure_identity_site",
			)
		)
		or {}
	)
	check(
		"6.5 a second run changes nothing",
		clients and not any(v.get("changed") for v in again.values()),
		str(again),
	)
	allowed = flow.execute(
		"id",
		"frappe.get_all",
		doctype="Has Role",
		filters={"parent": clients.get("helpdesk", {}).get("client_id", "-"), "parenttype": "OAuth Client"},
		pluck="role",
	)
	info("6.5 allowed roles of the helpdesk client", str(allowed))

	# 6.6 Social Login Keys on the app sites
	for stack in ("hd", "erp"):
		key = APP_KEY[stack]
		os.environ["NXERP_IDENTITY_ORIGIN"] = ORIGIN["id"]
		os.environ["NXERP_SSO_CLIENT_ID"] = clients[key]["client_id"]
		os.environ["NXERP_SSO_CLIENT_SECRET"] = sso_secret[key]
		names = ["NXERP_IDENTITY_ORIGIN", "NXERP_SSO_CLIENT_ID", "NXERP_SSO_CLIENT_SECRET"]
		first = (
			parse_dict(bench_env(stack, names, "execute", "nxerp.federation.setup.configure_app_site")) or {}
		)
		second = (
			parse_dict(bench_env(stack, names, "execute", "nxerp.federation.setup.configure_app_site")) or {}
		)
		check(
			f"6.6 {stack} Social Login Key created, second run changes nothing",
			first.get("changed") is True and second.get("changed") is False,
			f"{first} {second}",
		)
		sign_ups = flow.execute(
			stack, "frappe.db.get_value", doctype="Social Login Key", filters="frappe", fieldname="sign_ups"
		)
		check(f"6.6 {stack} Sign ups = Deny", sign_ups == "Deny", str(sign_ups))
	for name in ("NXERP_IDENTITY_ORIGIN", "NXERP_SSO_CLIENT_ID", "NXERP_SSO_CLIENT_SECRET"):
		os.environ.pop(name, None)

	# the login page of an app site shows the one SSO button
	hd = flow.Site(f"hd.{DOMAIN}")
	status, _, page = hd.call("GET", "/login")
	check(
		"6.6 hd /login has the sign-in button",
		status == 200 and "Sign in with NXERP" in page,
		f"status {status}",
	)
	links = re.findall(r'href="([^"]*oauth2[.]authorize[^"]*)"', page.replace("&amp;", "&"))
	check(
		"6.6 the button's link goes to the IDENTITY site (an absolute URL on its origin), not to the app itself",
		bool(links) and all(link.startswith(ORIGIN["id"] + "/") for link in links),
		str([link[:60] for link in links[:1]]),
	)

	# 6.7 a grant on the identity site reaches the app site
	flow.execute(
		"id",
		"frappe.client.insert",
		doc={
			"doctype": "User",
			"email": USER,
			"first_name": "Fed",
			"send_welcome_email": 0,
			"user_type": "System User",
			"roles": [{"role": "Desk User"}, {"role": ACCESS_ROLE["hd"]}],
		},
	)
	flow.execute("id", "frappe.utils.password.update_password", user=USER, pwd=password)
	flow.execute("id", "frappe.db.commit")
	rows = (
		flow.execute(
			"id",
			"frappe.get_all",
			doctype="NXERP Provisioning Outbox",
			filters={"user": USER},
			fields=["app_key", "action", "status"],
		)
		or []
	)
	check(
		"6.7 the grant queued one Pending row",
		[(r["app_key"], r["action"]) for r in rows] == [("helpdesk", "Enable")]
		and rows[0]["status"] in ("Pending", "Sent"),
		str(rows),
	)
	info("6.7", f"process: {run_process()}")
	state = user_state("hd", USER)
	check(
		"6.2 (check 6.2) hd has the user, enabled, with the access role",
		state.get("exists") and state.get("enabled") and ACCESS_ROLE["hd"] in state.get("roles", []),
		str(state),
	)
	has_pw = flow.execute(
		"hd", "frappe.db.exists", dt="__Auth", dn={"doctype": "User", "name": USER, "fieldname": "password"}
	)
	check("6.2 the user on hd has no password", not has_pw, "")
	check("6.2 erp does not have the user (no ERP grant)", not user_state("erp", USER).get("exists"), "")
	rows = (
		flow.execute(
			"id",
			"frappe.get_all",
			doctype="NXERP Provisioning Outbox",
			filters={"user": USER},
			fields=["status"],
		)
		or []
	)
	check("6.2 the outbox row is Sent", [r["status"] for r in rows] == ["Sent"], str(rows))

	# 6.7 single sign-on, and T8-style negative: no ERP grant
	id_site = flow.Site(f"id.{DOMAIN}")
	status, _, _ = id_site.call("POST", "/api/method/login", form={"usr": USER, "pwd": password})
	check("6.7 sign in at id", status == 200, str(status))
	result = flow.flow(id_site, hd, "SSO-hd")
	_, _, who = hd.call("GET", "/api/method/frappe.auth.get_logged_user")
	check(
		"6.3 (check 6.3) one sign-in, no second password: hd knows the user",
		result == 302 and USER in who,
		who[:60],
	)
	url = flow.execute(
		"erp", "frappe.utils.oauth.get_oauth2_authorize_url", provider="frappe", redirect_to="/desk/home"
	)
	status, _, _body = (
		id_site.call("GET", flow.split_location(str(url))[1]) if isinstance(url, str) else (0, None, "")
	)
	check(
		"6.4 (check 6.4) no ERP grant: the identity site refuses the sign-in to erp",
		status == 400,
		f"status {status}",
	)

	# T7: password login refused on the app site once local login is off, SSO still works
	flow.execute(
		"hd",
		"frappe.db.set_single_value",
		doctype="System Settings",
		fieldname="disable_user_pass_login",
		value=1,
	)
	flow.execute("hd", "frappe.clear_cache")
	probe = flow.Site(f"hd.{DOMAIN}")
	status, _, _ = probe.call("POST", "/api/method/login", form={"usr": USER, "pwd": password})
	check(
		"T7 a direct password login on hd is refused with no sid",
		status in (401, 403) and probe.cookies.get("sid") in (None, "Guest"),
		f"status {status}",
	)
	check(
		"T7 the sign-in through id still works",
		flow.flow(id_site, flow.Site(f"hd.{DOMAIN}"), "T7-sso") == 302,
		"",
	)
	flow.execute(
		"hd",
		"frappe.db.set_single_value",
		doctype="System Settings",
		fieldname="disable_user_pass_login",
		value=0,
	)
	flow.execute("hd", "frappe.clear_cache")
	status, _, _ = flow.Site(f"hd.{DOMAIN}").call(
		"POST", "/api/method/login", form={"usr": "Administrator", "pwd": "wrong-on-purpose"}
	)
	check(
		"6.6 (check 6.6) after the recovery lines local login answers again (a wrong password gets 401 'invalid', not 'not allowed')",
		status == 401,
		f"status {status}",
	)

	# T8 / 6.9: revocation reaches the app site
	# the supported way: the API every admin screen uses
	flow.execute("id", "nxerp.api.access.set_app_access", user=USER, app_key="helpdesk", grant=1)
	flow.execute("id", "nxerp.api.access.set_app_access", user=USER, app_key="helpdesk", grant=0)
	flow.execute("id", "frappe.db.commit")
	info("T8", f"process: {run_process()}")
	state = user_state("hd", USER)
	check(
		"T8 (check 6.5) revoking on id disables the user on hd and removes the access role",
		state.get("exists") and not state.get("enabled") and ACCESS_ROLE["hd"] not in state.get("roles", []),
		str(state),
	)
	check("T8 the user is never deleted", state.get("exists"), "")

	# 6.9 reconcile: drift in both directions, then 0 differences
	flow.execute("id", "nxerp.api.access.set_app_access", user=USER, app_key="helpdesk", grant=1)
	flow.execute(
		"id", "frappe.db.delete", doctype="NXERP Provisioning Outbox"
	)  # a lost row: the live path never told hd
	flow.execute("id", "frappe.db.commit")
	flow.execute(
		"hd",
		"frappe.client.insert",
		doc={
			"doctype": "User",
			"email": USER2,
			"first_name": "Drift",
			"send_welcome_email": 0,
			"roles": [{"role": ACCESS_ROLE["hd"]}],
		},
	)
	flow.execute("hd", "frappe.db.commit")
	first = flow.execute("id", "nxerp.federation.reconcile.run") or {}
	check(
		"6.9 reconcile found the two drifts (missing and extra) and repaired them",
		first.get("missing", 0) >= 1 and first.get("extra", 0) >= 1,
		str({k: v for k, v in first.items() if k != "delivery"}),
	)
	run_process()  # reconcile delivers too, but a run already in progress holds the lock: wait until the queue is empty
	state = user_state("hd", USER)
	check(
		"6.9 the missing user is enabled on hd again",
		state.get("enabled") and ACCESS_ROLE["hd"] in state.get("roles", []),
		str(state),
	)
	check("6.9 the extra user is disabled on hd", user_state("hd", USER2).get("enabled") is False, "")
	second = flow.execute("id", "nxerp.federation.reconcile.run") or {}
	check(
		"6.9 a second reconcile reports 0 differences", second.get("message") == "0 differences", str(second)
	)
	info("summary", f"{RESULTS}")
	return 1 if RESULTS.get("FAIL") else 0


if __name__ == "__main__":
	try:
		code = main()
	finally:
		print(json.dumps({"results": RESULTS}), flush=True)
	sys.exit(code)
