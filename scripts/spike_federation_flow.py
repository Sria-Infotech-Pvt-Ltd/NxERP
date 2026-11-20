"""Phase 6A spike: drive the OAuth login flow between two THROWAWAY stacks (identity `id`, app `hd`) and print what Frappe v16.53.0 does.

Findings only, not product code. Run from the repository root with the Phase 5 rehearsal stacks up and the edge answering on 127.0.0.1:8180:

    python scripts/spike_federation_flow.py

Setup goes through `deploy/scripts/stack.sh <stack> bench execute` (as the site's Administrator); the browser side goes over HTTP to the edge with a
Host header, one cookie jar per site, redirects followed by hand. Fake users only (user@example.test). Output lines hold statuses, names and
key NAMES: never a client secret, token, cookie value or password.
"""

import http.client
import json
import os
import re
import secrets
import subprocess
import sys
import urllib.parse

EDGE = ("127.0.0.1", 8180)
DOMAIN = "example.test"
PORT_IN_URL = 8080  # the edge listens on 8080 inside the containers; host names carry it so server-to-server calls reach the edge
ID_HOST, HD_HOST = f"id.{DOMAIN}", f"hd.{DOMAIN}"
USER, USER2, USER3, USER4 = (
	"user@example.test",
	"unknown@example.test",
	"disabled@example.test",
	"norole@example.test",
)
GATE_ROLE = "NXERP Access: Helpdesk"
OUT = []


def say(line: str) -> None:
	OUT.append(line)
	print(line, flush=True)


SITES = {"id": f"id.{DOMAIN}", "hd": f"hd.{DOMAIN}"}


def bench(stack: str, *args: str) -> str:
	"""bench for the stack's site through `docker exec` with an argument list (no shell, so JSON arguments stay intact)."""
	proc = subprocess.run(
		[
			"docker",
			"exec",
			"-w",
			"/home/frappe/frappe-bench",
			f"nxerp-{stack}-backend-1",
			"bench",
			"--site",
			SITES[stack],
			*args,
		],
		capture_output=True,
		text=True,
		check=False,
		env={**os.environ, "MSYS_NO_PATHCONV": "1"},
	)
	if proc.returncode != 0:
		lines = (proc.stderr.strip() or proc.stdout.strip()).splitlines()
		tail = lines[-1] if lines else str(proc.returncode)
		say(f"BENCH-FAIL {stack} {' '.join(args[:2])}: {tail[:240]}")
	return proc.stdout


def execute(stack: str, method: str, **kwargs) -> object:
	out = bench(
		stack, "execute", method, "--kwargs", repr(kwargs)
	)  # bench evaluates kwargs as Python, not JSON
	text = out.strip()
	if not text:
		return None
	for candidate in (text, text.splitlines()[-1].strip()):
		if candidate[:1] in '[{"' or candidate in ("null", "true", "false"):
			try:
				return json.loads(candidate)
			except ValueError:
				continue
	return text.splitlines()[-1].strip()  # a bare string result (bench prints it unquoted)


class Site:
	def __init__(self, host: str):
		self.host = host
		self.cookies: dict = {}
		self.last_set_cookie: list = []

	def call(self, method: str, path: str, form: dict | None = None, headers: dict | None = None):
		conn = http.client.HTTPConnection(*EDGE, timeout=30)
		sent = {"Host": f"{self.host}:{PORT_IN_URL}", "Accept": "text/html,application/json"}
		if self.cookies:
			sent["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
		body = None
		if form is not None:
			body = urllib.parse.urlencode(form)
			sent["Content-Type"] = "application/x-www-form-urlencoded"
		sent.update(headers or {})
		conn.request(method, path, body=body, headers=sent)
		response = conn.getresponse()
		data = response.read().decode("utf-8", "replace")
		self.last_set_cookie = response.headers.get_all("Set-Cookie") or []
		for header in self.last_set_cookie:
			name, _, rest = header.partition("=")
			value = rest.split(";", 1)[0]
			if value in ("", "deleted"):
				self.cookies.pop(name, None)
			else:
				self.cookies[name] = value
		conn.close()
		return response.status, response.headers, data


def split_location(location: str):
	parsed = urllib.parse.urlparse(location)
	return parsed.hostname, parsed.path + (f"?{parsed.query}" if parsed.query else "")


def sid_attributes(site: Site) -> str:
	for header in site.last_set_cookie:
		if header.startswith("sid=") and "sid=Guest" not in header:
			attrs = [part.strip().split("=")[0].lower() for part in header.split(";")[1:]]
			return ",".join(sorted(attrs))
	return "(no sid set)"


def flow(id_site: Site, hd_site: Site, label: str, want_claims: bool = False):
	"""Start at the app site's login page, go through the identity site, come back. Returns (status, location or title, hd_site)."""
	hd_site.cookies.clear()
	status, _, html = hd_site.call("GET", "/login")
	say(
		f"[{label}] hd /login status={status}, page links to the identity site's authorize endpoint={'oauth2.authorize' in html.replace('&amp;', '&')}"
	)
	# the stock Frappe login page builds this link; the NXERP login page does not (yet), so ask the same function the page would call
	url = execute(
		"hd", "frappe.utils.oauth.get_oauth2_authorize_url", provider="frappe", redirect_to="/helpdesk"
	)
	links = [url] if isinstance(url, str) else []
	say(
		f"[{label}] authorize url built by frappe.utils.oauth.get_oauth2_authorize_url: {'yes' if links else 'NO'}"
	)
	if links:
		say(
			f"[{label}] authorize url query keys={sorted(urllib.parse.parse_qs(urllib.parse.urlparse(links[0]).query))}"
		)
	_host, path = split_location(links[0])
	status, headers, page = id_site.call("GET", path)
	location = headers.get("Location", "")
	if status not in (302, 303):
		say(f"[{label}] authorize body = {' '.join(re.sub('<[^>]+>', ' ', page).split())[:300]}")
	say(
		f"[{label}] id authorize status={status}, redirects to host={split_location(location)[0] if location else None}"
	)
	if status not in (302, 303) or not location:
		return None
	query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
	say(f"[{label}] callback query keys={sorted(query)}")
	if want_claims:
		claims_flow(id_site, location)
		return "claims"
	_host, path = split_location(location)
	status, headers, body = hd_site.call("GET", path)
	title = re.search(r"<title>([^<]*)</title>", body)
	say(
		f"[{label}] hd callback status={status}, title={title.group(1).strip() if title else None}, sid cookie attributes={sid_attributes(hd_site)}"
	)
	if status in (302, 303):
		_, _, who = hd_site.call("GET", "/api/method/frappe.auth.get_logged_user")
		say(
			f"[{label}] hd logged user after callback = {json.loads(who).get('message') if who.startswith('{') else who[:40]}"
		)
	else:
		text = re.sub(r"<[^>]+>", " ", body)
		say(f"[{label}] hd page text = {' '.join(text.split())[:160]}")
	return status


def claims_flow(id_site: Site, location: str) -> None:
	"""Exchange a code at the identity site ourselves and list the NAMES of the userinfo claims (never their values)."""
	query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
	client_id, client_secret = CLIENT["id"], CLIENT["secret"]
	redirect = f"http://{HD_HOST}:{PORT_IN_URL}/api/method/frappe.integrations.oauth2_logins.login_via_frappe"
	anon = Site(ID_HOST)
	status, _, body = anon.call(
		"POST",
		"/api/method/frappe.integrations.oauth2.get_token",
		form={
			"grant_type": "authorization_code",
			"code": query["code"][0],
			"redirect_uri": redirect,
			"client_id": client_id,
			"client_secret": client_secret,
		},
	)
	data = json.loads(body) if body.startswith("{") else {}
	say(f"[claims] token endpoint status={status}, response keys={sorted(data)}")
	if "access_token" in data:
		status, _, body = anon.call(
			"GET",
			"/api/method/frappe.integrations.oauth2.openid_profile",
			headers={"Authorization": f"Bearer {data['access_token']}"},
		)
		profile = json.loads(body) if body.startswith("{") else {}
		say(f"[claims] openid_profile status={status}, claim names={sorted(profile)}")
	if "id_token" in data:
		import base64

		part = data["id_token"].split(".")
		header = json.loads(base64.urlsafe_b64decode(part[0] + "=" * (-len(part[0]) % 4)))
		say(f"[claims] id_token header={header} (HS256 means a shared-secret signature, not a public key)")


CLIENT: dict = {}


def main() -> int:
	password = secrets.token_urlsafe(18)
	redirect = f"http://{HD_HOST}:{PORT_IN_URL}/api/method/frappe.integrations.oauth2_logins.login_via_frappe"
	say("== cleanup of an earlier run, then setup (identity site id, app site hd)")
	for stack in ("id", "hd"):
		for email in (USER, USER2, USER3, USER4):
			if execute(stack, "frappe.db.exists", dt="User", dn=email):
				execute(
					stack, "frappe.delete_doc", doctype="User", name=email, force=1, ignore_permissions=True
				)
	for name in execute("id", "frappe.get_all", doctype="OAuth Client", pluck="name") or []:
		execute(
			"id", "frappe.delete_doc", doctype="OAuth Client", name=name, force=1, ignore_permissions=True
		)
	if execute("hd", "frappe.db.exists", dt="Social Login Key", dn="frappe"):
		execute(
			"hd",
			"frappe.delete_doc",
			doctype="Social Login Key",
			name="frappe",
			force=1,
			ignore_permissions=True,
		)
	for stack in ("id", "hd"):
		execute(stack, "frappe.db.commit")
	for stack, host in (("id", ID_HOST), ("hd", HD_HOST)):
		bench(stack, "set-config", "host_name", f"http://{host}:{PORT_IN_URL}")
	for stack in ("id", "hd"):
		bench(stack, "set-config", "developer_mode", "1") if False else None
	# fake user with a password on the identity site
	# the identity site must hold the app's access role (Phase 6C makes install create all of them there)
	if not execute("id", "frappe.db.exists", dt="Role", dn=GATE_ROLE):
		execute(
			"id",
			"frappe.client.insert",
			doc={"doctype": "Role", "role_name": GATE_ROLE, "desk_access": 0, "is_custom": 1},
		)
	for email in (USER, USER2, USER3, USER4):
		roles = [] if email == USER4 else [{"role": GATE_ROLE}]
		execute(
			"id",
			"frappe.client.insert",
			doc={
				"doctype": "User",
				"email": email,
				"first_name": "Spike",
				"send_welcome_email": 0,
				"user_type": "System User",
				"enabled": 1,
				"roles": roles,
			},
		)
		execute("id", "frappe.utils.password.update_password", user=email, pwd=password)
	# the same person on the app site, with no password (as provisioning will create it)
	execute(
		"hd",
		"frappe.client.insert",
		doc={
			"doctype": "User",
			"email": USER,
			"first_name": "Spike",
			"send_welcome_email": 0,
			"user_type": "Website User",
			"enabled": 1,
		},
	)
	execute(
		"hd",
		"frappe.client.insert",
		doc={
			"doctype": "User",
			"email": USER3,
			"first_name": "Spike",
			"send_welcome_email": 0,
			"user_type": "Website User",
			"enabled": 0,
		},
	)
	# OAuth Client on id
	client = execute(
		"id",
		"frappe.client.insert",
		doc={
			"doctype": "OAuth Client",
			"app_name": "Spike Helpdesk",
			"skip_authorization": 1,
			"client_secret": secrets.token_urlsafe(32),
			"allowed_roles": [{"role": GATE_ROLE}],
			"scopes": "all openid",
			"redirect_uris": redirect,
			"default_redirect_uri": redirect,
			"grant_type": "Authorization Code",
			"response_type": "Code",
		},
	)
	if not isinstance(client, dict):
		say("FAIL could not create the OAuth Client")
		return 1
	# v16.53.0: client_secret is a plain Data field, generated as frappe.generate_hash(length=10) when empty (10 hex characters, stored in clear)
	CLIENT["id"] = client["client_id"]
	CLIENT["secret"] = client.get("client_secret") or ""
	say(
		f"OAuth Client auto-generated secret length={len(CLIENT['secret'])} characters, stored as plain Data (not a Password field)"
	)
	say(
		f"OAuth Client fields set by the insert response: {sorted(k for k in client if k in ('client_id', 'client_secret', 'client_name', 'scopes', 'grant_type', 'response_type', 'skip_authorization', 'default_redirect_uri', 'redirect_uris'))}"
	)
	# Social Login Key on hd
	key = {
		"doctype": "Social Login Key",
		"social_login_provider": "Frappe",
		"provider_name": "Frappe",
		"client_id": CLIENT["id"],
		"client_secret": CLIENT["secret"],
		"base_url": f"http://{ID_HOST}:{PORT_IN_URL}",
		"authorize_url": "/api/method/frappe.integrations.oauth2.authorize",
		"access_token_url": "/api/method/frappe.integrations.oauth2.get_token",
		"redirect_url": "/api/method/frappe.integrations.oauth2_logins.login_via_frappe",
		"api_endpoint": "/api/method/frappe.integrations.oauth2.openid_profile",
		"auth_url_data": json.dumps({"response_type": "code", "scope": "openid"}),
		"enable_social_login": 1,
		"sign_ups": "Deny",
	}
	made = execute("hd", "frappe.client.insert", doc=key)
	say(
		f"Social Login Key created: {'yes, name=' + str(made.get('name')) if isinstance(made, dict) else 'NO'}"
	)
	id_site, hd_site = Site(ID_HOST), Site(HD_HOST)
	status, _, body = id_site.call("POST", "/api/method/login", form={"usr": USER, "pwd": password})
	say(f"id login with password: status={status}, sid attributes={sid_attributes(id_site)}")
	say("== S1 happy path: user exists and is enabled on hd")
	flow(id_site, hd_site, "S1")
	say("== S2 user unknown on hd, Sign ups = Deny")
	id2 = Site(ID_HOST)
	id2.call("POST", "/api/method/login", form={"usr": USER2, "pwd": password})
	flow(id2, hd_site, "S2")
	say("== S3 user unknown on hd, Sign ups = Allow")
	execute(
		"hd",
		"frappe.client.set_value",
		doctype="Social Login Key",
		name="frappe",
		fieldname="sign_ups",
		value="Allow",
	)
	flow(id2, hd_site, "S3")
	roles = execute("hd", "frappe.get_roles", username=USER2)
	say(f"S3 roles of the auto-created user = {roles}")
	say(
		f"S3 user_type = {execute('hd', 'frappe.db.get_value', doctype='User', filters=USER2, fieldname='user_type')}"
	)
	execute(
		"hd",
		"frappe.client.set_value",
		doctype="Social Login Key",
		name="frappe",
		fieldname="sign_ups",
		value="Deny",
	)
	say("== S4 user disabled on hd")
	id3 = Site(ID_HOST)
	id3.call("POST", "/api/method/login", form={"usr": USER3, "pwd": password})
	flow(id3, hd_site, "S4")
	say("== S6 user WITHOUT the gate role on the identity site (OAuth Client allowed_roles)")
	id4 = Site(ID_HOST)
	id4.call("POST", "/api/method/login", form={"usr": USER4, "pwd": password})
	flow(id4, hd_site, "S6")
	say("== claims: what the identity site returns for the user (names only)")
	flow(id_site, hd_site, "claims", want_claims=True)
	say("== S5 disable_user_pass_login on hd")
	execute(
		"hd",
		"frappe.db.set_single_value",
		doctype="System Settings",
		fieldname="disable_user_pass_login",
		value=1,
	)
	execute("hd", "frappe.clear_cache")
	probe = Site(HD_HOST)
	status, _, body = probe.call("GET", "/login")
	say(
		f"[S5] hd /login status={status}, has password field={'id="login_password"' in body or 'name="pwd"' in body}, has social button={'oauth2.authorize' in body.replace('&amp;', '&')}"
	)
	status, _, body = probe.call("POST", "/api/method/login", form={"usr": USER, "pwd": "wrong-on-purpose"})
	say(
		f"[S5] hd POST /api/method/login status={status}, sid issued={'sid' in probe.cookies and probe.cookies.get('sid') != 'Guest'}, message={json.loads(body).get('message', body[:60]) if body.startswith('{') else body[:60]}"
	)
	flow(id_site, hd_site, "S5-sso-still-works")
	execute(
		"hd",
		"frappe.db.set_single_value",
		doctype="System Settings",
		fieldname="disable_user_pass_login",
		value=0,
	)
	execute("hd", "frappe.clear_cache")
	say("== done")
	return 0


if __name__ == "__main__":
	sys.exit(main())
