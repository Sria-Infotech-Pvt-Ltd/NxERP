// The special login flows, end to end, on the fresh site: forgot / reset password with the emailed link (a local
// capture server stands in for the mail provider; nothing leaves the machine), two-factor authentication (OTP by
// email), lockout after repeated failures, sign-up (disabled here), login with an emailed link, and the
// social / SSO buttons. Each flow ends by signing in and checking the router still decides the landing.
import assert from "node:assert/strict";
import test, { after, before } from "node:test";
import { startMailSink } from "./mailsink.mjs";
import { BASE, PASSWORD, email, fixture, here, launch, open, session, setConfig, shot, signIn, url, waitForConfig } from "./lib.mjs";

let browser;
let sink;

before(async () => {
	browser = await launch();
	sink = await startMailSink(2525);
	fixture("use_mail_sink", { port: 2525 });
	setConfig("mute_emails", 0); // the dev setup mutes mail; the web worker notices within its 60 s config cache
	await new Promise((r) => setTimeout(r, 65000));
});
after(async () => {
	fixture("two_factor", { enabled: false });
	fixture("drop_mail_sink");
	setConfig("mute_emails", 1);
	await sink?.stop();
	await browser.close();
});

/** Flush the site's mail queue (a scheduler would do this every minute) and wait for the message to reach the sink. */
async function mailFor(recipient, { timeoutMs = 60000 } = {}) {
	const deadline = Date.now() + timeoutMs;
	for (;;) {
		fixture("flush_mail");
		const found = sink.latestFor(recipient);
		if (found) return found;
		if (Date.now() > deadline) return null;
		await new Promise((r) => setTimeout(r, 2000));
	}
}

// --- forgot / reset password ----------------------------------------------------------------------------------

test("forgot password: the emailed link sets a new password, the old one stops working, the link cannot be reused", async () => {
	const user = email("reset");
	const { context, page } = await session(browser);
	await open(page, "/login#forgot");
	await page.fill("#forgot_email", user);
	await page.click(".btn-forgot");
	await page.waitForTimeout(2000);
	await shot(page, "flow-forgot-requested");

	const mail = await mailFor(user);
	assert.ok(mail, "no reset email reached the capture server");
	const link = mail.text.match(/https?:\/\/[^\s"'<>]+update-password\?key=[A-Za-z0-9_\-]+/)?.[0];
	assert.ok(link, "the email carries a reset link");
	assert.ok(link.startsWith(BASE), `the link points at this site, not somewhere else: ${new URL(link).origin}`);

	const NEW_PASSWORD = `${PASSWORD}-new-9!`;
	await page.goto(link, { waitUntil: "domcontentloaded" });
	await page.fill("#new_password", NEW_PASSWORD);
	await page.fill("#confirm_password", NEW_PASSWORD);
	await page.waitForFunction(() => !document.querySelector("#update").disabled, null, { timeout: 15000 });
	await page.click("#update");
	await page.waitForTimeout(4000);
	await shot(page, "flow-password-updated");

	// the new password works and lands through the router
	await context.clearCookies();
	await signIn(page, user, NEW_PASSWORD);
	assert.match(here(page), /^\/helpdesk/);
	// the old one is refused
	const old = await (await session(browser)).page;
	await old.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
	await old.fill("#login_email", user);
	await old.fill("#login_password", PASSWORD);
	await old.click("section.for-login button[type=submit]");
	await old.waitForTimeout(2500);
	assert.equal(url(old).pathname, "/login");
	// the link is single use
	const again = await (await session(browser)).page;
	await again.goto(link, { waitUntil: "domcontentloaded" });
	const text = (await again.locator("body").innerText()).toLowerCase();
	assert.ok(/invalid|expired|not valid|already|link/.test(text) || !(await again.locator("#new_password").isVisible().catch(() => false)), "the used link is refused");
	await context.close();
});

test("forgot password does not reveal whether an address has an account", async () => {
	const answer = async (user) => {
		const { context, page } = await session(browser);
		await open(page, "/login#forgot");
		const response = page.waitForResponse((r) => r.url().includes("reset_password"), { timeout: 30000 });
		await page.fill("#forgot_email", user);
		await page.click(".btn-forgot");
		const r = await response;
		const body = await r.text();
		await context.close();
		return { status: r.status(), body };
	};
	const known = await answer(email("agent"));
	const unknown = await answer("nobody-at-all@example.test");
	assert.equal(known.status, unknown.status, "same status for a known and an unknown address");
	assert.ok(!/not found|no such|does not exist/i.test(unknown.body), `the answer for an unknown address says so: ${unknown.body.slice(0, 120)}`);
});

// --- two-factor authentication (OTP by email) -------------------------------------------------------------------

test("two-factor: the OTP step appears, a wrong code is refused, the emailed code signs in and lands through the router", async () => {
	const user = email("otp");
	fixture("two_factor", { enabled: true });
	try {
		const { context, page } = await session(browser);
		await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
		await page.fill("#login_email", user);
		await page.fill("#login_password", PASSWORD);
		await page.click("section.for-login button[type=submit]");
		await page.waitForSelector("#login_token", { timeout: 30000 });
		await shot(page, "flow-2fa-step");
		assert.equal(url(page).pathname, "/login", "still on the login page until the code is entered");

		await page.fill("#login_token", "000000");
		await page.keyboard.press("Enter");
		await page.waitForTimeout(3000);
		assert.equal(url(page).pathname, "/login", "a wrong code does not sign in");

		const mail = await mailFor(user);
		assert.ok(mail, "no OTP email reached the capture server");
		const code = mail.text.match(/\b(\d{6})\b/)?.[1];
		assert.ok(code, "the OTP email carries a six-digit code");
		await page.fill("#login_token", code);
		await Promise.all([page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 45000 }), page.keyboard.press("Enter")]);
		await page.waitForTimeout(3000);
		assert.match(here(page), /^\/helpdesk/, `landed on ${here(page)}`);
		await context.close();
	} finally {
		fixture("two_factor", { enabled: false });
	}
});

// --- lockout / rate limiting --------------------------------------------------------------------------------------

test("lockout: repeated wrong passwords lock the account for a while; the right password is refused meanwhile, then works", async () => {
	const user = email("lockout");
	const attempt = async (pwd) => {
		const r = await fetch(`${BASE}/api/method/login`, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ usr: user, pwd }) });
		return { status: r.status, body: await r.text() };
	};
	let locked = null;
	for (let i = 0; i < 15 && !locked; i++) {
		const r = await attempt("wrong-password-" + i);
		if (/locked|too many|try again|attempts/i.test(r.body)) locked = r;
	}
	assert.ok(locked, "the account was never locked after 15 wrong passwords");
	assert.ok(!/Traceback/.test(JSON.parse(locked.body).message ?? ""), "no stack trace in the message");
	const meanwhile = await attempt(PASSWORD);
	assert.notEqual(meanwhile.status, 200, "the right password must not sign in while the account is locked");
	await new Promise((r) => setTimeout(r, 70000)); // Frappe's default lockout is 60 seconds
	const after = await attempt(PASSWORD);
	assert.equal(after.status, 200, `signing in after the lockout expired answered ${after.status}`);
});

// --- sign-up, login with an emailed link, social / SSO ----------------------------------------------------------------

test("sign-up: disabled on this site, so no form is offered and the API refuses", async () => {
	const { context, page } = await session(browser);
	await open(page, "/login");
	assert.equal(await page.locator("form.form-signup:visible").count(), 0);
	const r = await page.request.post(`${BASE}/api/method/frappe.core.doctype.user.user.sign_up`, {
		form: { email: "someone-new@example.test", full_name: "Someone", redirect_to: "/" },
	});
	assert.ok(!r.ok(), "sign-up is refused while disabled");
	assert.ok(!/Traceback/.test((await r.text()).replace(/"exc":"[^"]*"/, "")), "no stack trace in the message");
	await context.close();
});

test("login with an emailed link: not offered on the page; when an administrator switches it on in Frappe it works and lands through the router", async () => {
	const user = email("agent");
	const { context, page } = await session(browser);
	await open(page, "/login");
	assert.equal(await page.locator("section.for-login-with-email-link:visible").count(), 0, "the option is not shown");
	const refused = await page.request.post(`${BASE}/api/method/frappe.www.login.send_login_link`, { form: { email: user } });
	assert.ok(!refused.ok(), "while the Frappe setting is off the endpoint refuses");

	fixture("email_link_login", { enabled: true });
	try {
		const sent = await page.request.post(`${BASE}/api/method/frappe.www.login.send_login_link`, { form: { email: user } });
		assert.ok(sent.ok(), `send_login_link answered ${sent.status()}`);
		const mail = await mailFor(user);
		assert.ok(mail, "no login-link email reached the capture server");
		const link = mail.text.match(/https?:\/\/[^\s"'<>]+login_via_key\?key=[A-Za-z0-9_\-]+/)?.[0];
		assert.ok(link && link.startsWith(BASE), "the email carries a link to this site");
		await page.goto(link, { waitUntil: "domcontentloaded" });
		await page.waitForTimeout(4000);
		await shot(page, "flow-email-link-landing");
		assert.match(here(page), /^\/helpdesk/, `the link landed on ${here(page)}`);
	} finally {
		fixture("email_link_login", { enabled: false });
	}
	await context.close();
});

test("social / SSO: no provider is configured on this site, so there is no button and no provider endpoint answers", async () => {
	const { context, page } = await session(browser);
	await open(page, "/login");
	assert.equal(await page.locator(".social-logins, .btn-login-option.btn-social").count(), 0);
	await context.close();
});
