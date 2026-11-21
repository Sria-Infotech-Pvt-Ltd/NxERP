// Phase 2, end to end with real pages and a real mail round trip (a local capture server stands in for the mail
// provider; nothing leaves the machine): signup is open by default (an administrator can close it); a visitor goes Products -> Get started ->
// Create account -> verification link -> set password -> /welcome/helpdesk -> wizard -> request; the gate still keeps
// them out; an administrator approves; the user can open the app. Also screenshots of every new screen at four widths.
//
//   E2E_SITE=nxerp.localhost E2E_BASE=http://localhost:8000 NXERP_E2E_PASSWORD=... node --test onboarding.test.mjs
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import test, { after, before } from "node:test";
import { startMailSink } from "./mailsink.mjs";
import { BASE, PASSWORD, email, fixture, here, launch, open, session, setConfig, signIn } from "./lib.mjs";
import { audit, keyboardWalk } from "./a11y.mjs";

const OUT = process.env.UI_SHOTS || "/tmp/ui-shots";
mkdirSync(OUT, { recursive: true });
const VIEWPORTS = { "360x800": [360, 800], "768x1024": [768, 1024], "1280x800": [1280, 800], "1920x1080": [1920, 1080] };

let browser;
let sink;
const visitor = `nxt-e2e-signup-${Date.now()}@example.test`;
const NEW_PASSWORD = `${PASSWORD}-new-9!`;

before(async () => {
	browser = await launch();
	sink = await startMailSink(2525);
	await fixture("use_mail_sink", { port: 2525 });
	setConfig("mute_emails", 0); // the dev setup mutes mail; the web worker notices within its 60 s config cache
	await fixture("enable_signup", { enabled: false });
	await fixture("reset_rate_limits"); // repeated runs from one IP would otherwise hit the (working) hourly limits
});
after(async () => {
	await fixture("delete_onboarding_data", { user: visitor });
	await fixture("delete_onboarding_data", { user: email("none"), keep_user: true });
	await fixture("enable_signup", { enabled: false });
	await fixture("drop_mail_sink");
	setConfig("mute_emails", 1);
	await sink?.stop();
	await browser.close();
});

async function shot(page, name) {
	const viewport = page.viewportSize();
	const height = await page.evaluate(() => Math.max(document.documentElement.scrollHeight, window.innerHeight));
	await page.setViewportSize({ width: viewport.width, height });
	await page.waitForTimeout(150);
	await page.screenshot({ path: `${OUT}/${name}.jpg`, type: "jpeg", quality: 82 });
	await page.setViewportSize(viewport);
}

async function until(check, { timeoutMs = 90000, everyMs = 3000 } = {}) {
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		if (await check()) return true;
		await new Promise((r) => setTimeout(r, everyMs));
	}
	return false;
}

async function mailFor(recipient, timeoutMs = 60000) {
	const deadline = Date.now() + timeoutMs;
	for (;;) {
		await fixture("flush_mail");
		const found = sink.latestFor(recipient);
		if (found) return found;
		if (Date.now() > deadline) return null;
		await new Promise((r) => setTimeout(r, 2000));
	}
}

async function shotsAt(path, name, { scheme = ["light", "dark"], who = null, sizes = VIEWPORTS } = {}) {
	for (const s of scheme) {
		for (const [label, [width, height]] of Object.entries(sizes)) {
			const { context, page } = await session(browser, { viewport: { width, height }, colorScheme: s, reducedMotion: "reduce", hasTouch: width < 500 });
			if (who) await signIn(page, who.email, who.password);
			await open(page, path);
			await shot(page, `${name}-${label}-${s}`);
			await context.close();
		}
	}
}

test("signup is closed only when an administrator closes it (Frappe's Disable Customer Signup): the page says so, the API refuses, nothing is created", async () => {
	assert.ok(await until(async () => {
		const { context, page } = await session(browser);
		await open(page, "/signup?app=helpdesk");
		const closed = (await page.locator("#nx-unavailable").count()) === 1;
		await context.close();
		return closed;
	}), "the unavailable state is shown while an administrator has closed signup");
	const { context, page } = await session(browser);
	await open(page, "/signup?app=helpdesk");
	assert.equal(await page.locator("#nx-signup-form").count(), 0);
	assert.match(await page.locator("#nx-unavailable h2").innerText(), /Signup is not available/);
	const refused = await page.request.post(`${BASE}/api/method/nxerp.api.account.sign_up`, { data: { email: visitor, full_name: "Nobody", app: "helpdesk" } });
	assert.ok(!refused.ok(), `sign_up answered ${refused.status()} while signup is off`);
	await context.close();
	await shotsAt("/signup?app=helpdesk", "signup-unavailable");
});

test("journey: Products, Get started, Create account, verify, set password, wizard, request", async () => {
	await fixture("enable_signup", { enabled: true });
	assert.ok(await until(async () => {
		const { context, page } = await session(browser);
		await open(page, "/signup?app=helpdesk");
		const open_ = (await page.locator("#nx-signup-form").count()) === 1;
		await context.close();
		return open_;
	}), "the form appears once the operator switch is on");

	const { context, page } = await session(browser, { reducedMotion: "reduce" });
	await open(page, "/products/helpdesk");
	await page.locator("main").getByRole("link", { name: "Get started" }).click();
	await page.waitForURL(/\/get-started\?product=helpdesk/);
	assert.match(await page.locator("h1").innerText(), /Get started with Sria Helpdesk/);
	await page.getByRole("link", { name: "Create account" }).click();
	await page.waitForURL(/\/signup\?app=helpdesk/);

	// inline errors first
	await page.click("#nx-create");
	assert.match(await page.locator("#nx-full-name-error").innerText(), /full name/i);
	assert.match(await page.locator("#nx-email-error").innerText(), /valid email/i);
	assert.equal(await page.getAttribute("#nx-email", "aria-invalid"), "true");
	await page.fill("#nx-full-name", "Signup Tester");
	await page.fill("#nx-email", visitor);
	await page.click("#nx-create");
	await page.locator("#nx-sent").waitFor({ state: "visible", timeout: 30000 });
	assert.match(await page.locator("#nx-sent h2").innerText(), /Check your email/);
	await shot(page, "signup-sent-1280x800-light");

	// the verification link, read from the captured message
	const mail = await mailFor(visitor);
	assert.ok(mail, `no verification email reached the capture server; sink: ${sink.messages.map((m) => m.to.join(",")).join(" | ")}`);
	const link = mail.text.match(/https?:\/\/[^\s"'<>]+update-password\?key=[A-Za-z0-9_\-]+/)?.[0];
	assert.ok(link, "the email carries a set-password link");
	// the link is built from the site's configured host name (the dev stack is reached on another port inside the container)
	const target = new URL(link);
	await page.goto(BASE + target.pathname + target.search, { waitUntil: "domcontentloaded" });
	await page.locator("#new_password").pressSequentially(NEW_PASSWORD);
	await page.locator("#confirm_password").pressSequentially(NEW_PASSWORD);
	await page.waitForFunction(() => !document.querySelector("#update").disabled, null, { timeout: 15000 });
	await page.click("#update");
	await page.waitForURL(/\/welcome\/helpdesk/, { timeout: 30000 }).catch(() => {});
	await page.waitForLoadState("networkidle").catch(() => {});
	assert.equal(here(page), "/welcome/helpdesk", `after setting the password the visitor lands on the wizard, not ${here(page)}`);

	// the wizard
	assert.match(await page.locator("#nx-step-label").innerText(), /step 1 of 3/i);
	await shot(page, "welcome-basics-1280x800-light");
	await page.locator('form[data-step="basics"] [data-action=continue]').click();
	await page.locator('form[data-step="about"]').waitFor({ state: "visible" });
	assert.match(await page.locator("#nx-step-label").innerText(), /step 2 of 3/i);
	await page.getByText("Customer support").click();
	await page.getByText("2 to 10 people").click();
	await shot(page, "welcome-about-1280x800-light");
	await page.locator('form[data-step="about"] [data-action=continue]').click();
	await page.locator('form[data-step="request"]').waitFor({ state: "visible" });
	assert.match(await page.locator("#nx-step-label").innerText(), /step 3 of 3/i);
	await shot(page, "welcome-request-1280x800-light");
	await page.getByRole("button", { name: "Send request" }).click();
	await page.locator("#nx-pending").waitFor({ state: "visible", timeout: 30000 });
	assert.match(await page.locator("#nx-pending h2").innerText(), /Request sent/);
	await shot(page, "welcome-pending-1280x800-light");

	// a refresh resumes on the pending view; the gate still keeps the user out of the app
	await page.reload({ waitUntil: "domcontentloaded" });
	assert.ok(await page.locator("#nx-pending").isVisible());
	await open(page, "/helpdesk/home");
	assert.match(here(page), /^\/nxerp\/no-access/, `a requester has no access yet; landed on ${here(page)}`);
	await context.storageState({ path: "/tmp/visitor-state.json" });
	await context.close();
});

test("no-access page offers Request access for the named app only", async () => {
	const { context, page } = await session(browser, { storageState: "/tmp/visitor-state.json" });
	await open(page, "/nxerp/no-access?app=helpdesk");
	const button = page.locator("[data-request-access]");
	assert.equal(await button.count(), 1);
	assert.equal(await button.getAttribute("href"), "/welcome/helpdesk");
	const text = await page.locator("body").innerText();
	assert.doesNotMatch(text, /ERPNext|NXERP Access|System Manager/);
	await open(page, "/nxerp/no-access?app=not-a-product");
	assert.equal(await page.locator("[data-request-access]").count(), 0);
	await open(page, "/nxerp/no-access");
	assert.equal(await page.locator("[data-request-access]").count(), 0);
	await context.close();
});

test("an administrator approves it in Desk and the user can open the app", async () => {
	const admin = await session(browser);
	await signIn(admin.page, email("sysmgr"), PASSWORD);
	await open(admin.page, "/desk/nxerp-access-request");
	await admin.page.waitForSelector(".list-row, .no-result", { timeout: 60000 });
	const rows = await admin.page.evaluate(
		(user) => frappe.xcall("frappe.client.get_list", { doctype: "NXERP Access Request", filters: { user }, fields: ["name", "user", "app_key", "status"] }),
		visitor,
	);
	assert.equal(rows.length, 1, "exactly one request exists for the new user");
	assert.deepEqual([rows[0].app_key, rows[0].status], ["helpdesk", "Pending"]);
	await shot(admin.page, "desk-access-request-list-1280x800-light");
	const done = await admin.page.evaluate((name) => frappe.xcall("nxerp.api.access_request.decide", { name, decision: "Approve", note: "Welcome" }), rows[0].name);
	assert.equal(done.status, "Approved");
	const again = await admin.page.evaluate((name) => frappe.xcall("nxerp.api.access_request.decide", { name, decision: "Reject" }), rows[0].name);
	assert.equal(again.status, "Approved", "deciding twice changes nothing");
	await admin.context.close();

	const user = await session(browser);
	await signIn(user.page, visitor, NEW_PASSWORD);
	await open(user.page, "/helpdesk/home");
	assert.match(here(user.page), /^\/helpdesk/, `the approved user opens the app; landed on ${here(user.page)}`);
	assert.doesNotMatch(here(user.page), /no-access/);
	await shot(user.page, "helpdesk-after-approval-1280x800-light");
	await user.context.close();
});

test("screenshots: signup, get started, no-access with a request button, at four widths in light and dark", async () => {
	await shotsAt("/signup?app=helpdesk", "signup");
	await shotsAt("/signup?app=erpnext", "signup-erpnext", { sizes: { "1280x800": [1280, 800] } });
	await shotsAt("/get-started?product=helpdesk", "get-started");
	await shotsAt("/get-started?product=erpnext", "get-started-erpnext", { sizes: { "1280x800": [1280, 800] } });
	await shotsAt("/nxerp/no-access?app=helpdesk", "no-access-request", { who: { email: email("none"), password: PASSWORD } });
});

test("overflow, labels and keyboard on every new page at 320px", async () => {
	const small = { width: 320, height: 640 };
	for (const path of ["/signup?app=helpdesk", "/get-started?product=helpdesk"]) {
		for (const scheme of ["light", "dark"]) {
			const { context, page } = await session(browser, { viewport: small, colorScheme: scheme });
			await open(page, path);
			const m = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, i: window.innerWidth }));
			assert.ok(m.s <= m.i, `${path} ${scheme}: scrollWidth ${m.s} > ${m.i}`);
			const problems = (await audit(page)).filter((x) => !x.startsWith("low contrast"));
			assert.deepEqual(problems, [], `${path}: ${problems.join(" | ")}`);
			const { noIndicator } = await keyboardWalk(page, 30);
			assert.deepEqual(noIndicator, [], `${path}: no visible focus on ${noIndicator.join(", ")}`);
			await context.close();
		}
	}
	// the wizard needs a signed-in user without the grant: the e2e "none" persona
	for (const scheme of ["light", "dark"]) {
		const { context, page } = await session(browser, { viewport: small, colorScheme: scheme });
		await signIn(page, email("none"), PASSWORD);
		await open(page, "/welcome/helpdesk");
		const m = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, i: window.innerWidth }));
		assert.ok(m.s <= m.i, `welcome ${scheme}: scrollWidth ${m.s} > ${m.i}`);
		const problems = (await audit(page)).filter((x) => !x.startsWith("low contrast"));
		assert.deepEqual(problems, [], `welcome: ${problems.join(" | ")}`);
		const { noIndicator } = await keyboardWalk(page, 30);
		assert.deepEqual(noIndicator, [], `welcome: no visible focus on ${noIndicator.join(", ")}`);
		await context.close();
	}
});

test("wizard screenshots for a signed-in user without the grant (steps, light and dark, four widths)", async () => {
	await fixture("delete_onboarding_data", { user: email("none"), keep_user: true }); // a clean slate even after an interrupted run
	for (const scheme of ["light", "dark"]) {
		for (const [label, [width, height]] of Object.entries(VIEWPORTS)) {
			// progress is saved server side, so a second visit would resume at the next step: start each capture clean
			await fixture("delete_onboarding_data", { user: email("none"), keep_user: true });
			const { context, page } = await session(browser, { viewport: { width, height }, colorScheme: scheme, reducedMotion: "reduce", hasTouch: width < 500 });
			await signIn(page, email("none"), PASSWORD);
			await open(page, "/welcome/helpdesk");
			await shot(page, `welcome-basics-${label}-${scheme}`);
			await page.locator('form[data-step="basics"] [data-action=continue]').click();
			await page.locator('form[data-step="about"]').waitFor({ state: "visible" });
			await page.getByText("Operations and stock").click();
			await shot(page, `welcome-about-${label}-${scheme}`);
			await page.locator('form[data-step="about"] [data-action=continue]').click();
			await page.locator('form[data-step="request"]').waitFor({ state: "visible" });
			await shot(page, `welcome-request-${label}-${scheme}`);
			await context.close();
		}
	}
	// the pending view: send a request as the same user, then capture it everywhere
	await fixture("delete_onboarding_data", { user: email("none"), keep_user: true });
	const sender = await session(browser);
	await signIn(sender.page, email("none"), PASSWORD);
	await open(sender.page, "/welcome/helpdesk");
	await sender.page.locator('form[data-step="basics"] [data-action=continue]').click();
	await sender.page.locator('form[data-step="about"] [data-action=skip]').click();
	await sender.page.getByRole("button", { name: "Send request" }).click();
	await sender.page.locator("#nx-pending").waitFor({ state: "visible", timeout: 30000 });
	await sender.context.close();
	await shotsAt("/welcome/helpdesk", "welcome-pending", { who: { email: email("none"), password: PASSWORD } });
	await fixture("delete_onboarding_data", { user: email("none"), keep_user: true });
});
