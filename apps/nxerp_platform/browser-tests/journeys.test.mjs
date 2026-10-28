// The user journeys, in a real browser, through the real login form: Case 1 (Administrator), Case 2 (one app),
// the customer portal, plus the negative paths (deep links, wrong password, disabled user, tampered redirect-to,
// expired session, logout). Case 3 (a third app) is in case3.test.mjs because it changes site config.
import assert from "node:assert/strict";
import test, { after, before } from "node:test";
import { ADMIN_PASSWORD, BASE, PASSWORD, email, failedSignIn, here, launch, open, session, shot, signIn, tiles, url, fixture } from "./lib.mjs";

let browser;
before(async () => (browser = await launch()));
after(async () => browser.close());

const EVIL = ["//evil.example", "https://evil.example/x", "/\\evil.example", "/%2f%2fevil.example", "javascript:alert(1)"];

async function visibleText(page) {
	return (await page.locator("body").innerText()).replace(/\s+/g, " ");
}

// --- Case 1: Administrator, every app ---------------------------------------------------------------------

test("Case 1: Administrator signs in once and gets the launcher with every installed app, correctly named", async () => {
	const { context, page } = await session(browser);
	await signIn(page, "Administrator", ADMIN_PASSWORD);
	assert.equal(url(page).pathname, "/nxerp/apps");
	assert.deepEqual(await tiles(page), ["erpnext", "helpdesk"]);
	const names = await page.$$eval("a.nxp-tile", (n) => n.map((x) => x.querySelector(".nxp-tile-title")?.textContent.trim()));
	assert.deepEqual(names, ["ERPNext", "Helpdesk"]);
	const text = await visibleText(page);
	for (const forbidden of ["Frappe", "Framework", "Payments", "Telephony"]) assert.ok(!text.includes(forbidden), `${forbidden} is not an application`);
	await context.close();
});

test("Case 1: from the launcher, ERPNext opens ERPNext and Helpdesk opens Helpdesk", async () => {
	const { context, page } = await session(browser);
	await signIn(page, "Administrator", ADMIN_PASSWORD);
	await Promise.all([page.waitForURL(/\/desk/, { timeout: 60000 }), page.click('a.nxp-tile[data-app="erpnext"]')]);
	assert.match(here(page), /^\/desk/);
	await open(page, "/nxerp/apps");
	await Promise.all([page.waitForURL(/\/helpdesk/, { timeout: 60000 }), page.click('a.nxp-tile[data-app="helpdesk"]')]);
	assert.match(here(page), /^\/helpdesk/);
	await context.close();
});

test("Case 1: a switch-app route leads back to the launcher from Helpdesk and from ERPNext", async () => {
	const { context, page } = await session(browser);
	await signIn(page, "Administrator", ADMIN_PASSWORD);
	// the server tells each app that this user holds more than one application
	await open(page, "/desk");
	const boot = await page.evaluate(() => frappe.boot.nxerp);
	assert.equal(boot.launcher, "/nxerp/apps");
	const row = await page.evaluate(() =>
		frappe.boot.navbar_settings.settings_dropdown.find((i) => i.item_label === "All applications"),
	);
	assert.equal(row.route, "/nxerp/apps");
	assert.ok(await page.evaluate((c) => Boolean(frappe.utils.eval(c)), row.condition), "the row is shown to a multi-app user");
	await context.close();
});

// --- Case 2: Helpdesk only --------------------------------------------------------------------------------

test("Case 2: a Helpdesk-only user goes straight into Helpdesk: no launcher, no ERPNext", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("agent"), PASSWORD);
	assert.match(here(page), /^\/helpdesk/);
	assert.ok(!here(page).startsWith("/nxerp/apps"));
	// the launcher itself is not for them: it sends them to their one app
	await open(page, "/nxerp/apps");
	assert.match(here(page), /^\/helpdesk/);
	// ERPNext is refused server-side, with the friendly page and no hint about what it is
	await open(page, "/desk");
	assert.equal(url(page).pathname, "/nxerp/no-access");
	const text = await visibleText(page);
	assert.ok(!/ERPNext|Helpdesk|NXERP Access/.test(text.replace(/NXERP/g, "")), "the page names no app the user lacks");
	await context.close();
});

test("Case 2: Helpdesk shows no switch-app menu to a single-app user", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("agent"), PASSWORD);
	await open(page, "/helpdesk/home");
	const apps = await page.evaluate(async () => {
		const r = await fetch("/api/method/frappe.apps.get_apps");
		return (await r.json()).message.map((a) => a.name);
	});
	assert.deepEqual(apps, ["helpdesk"]);
	assert.equal(await page.getByText("All applications", { exact: true }).count(), 0);
	await context.close();
});

test("an ERPNext-only user goes straight into ERPNext", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("erp"), PASSWORD);
	assert.match(here(page), /^\/desk/);
	await open(page, "/helpdesk/home");
	assert.equal(url(page).pathname, "/nxerp/no-access");
	await context.close();
});

test("a user with two apps gets the launcher with exactly those two", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("both"), PASSWORD);
	assert.equal(url(page).pathname, "/nxerp/apps");
	assert.deepEqual(await tiles(page), ["erpnext", "helpdesk"]);
	await context.close();
});

test("a user with no application gets the friendly no-access page and can sign out", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("none"), PASSWORD);
	assert.equal(url(page).pathname, "/nxerp/no-access");
	assert.equal(await page.locator("a[data-admin-hint]").count(), 0, "ordinary users see nothing about administration");
	await Promise.all([page.waitForURL(/\/login/, { timeout: 30000 }), page.click('a[href="/logout"]')]);
	assert.equal(url(page).pathname, "/login");
	await context.close();
});

// --- customer portal --------------------------------------------------------------------------------------

test("a customer goes to the customer portal and never sees the launcher or Desk", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("customer"), PASSWORD);
	assert.equal(url(page).pathname, "/helpdesk/my-tickets", `landed on ${here(page)}`);
	await open(page, "/nxerp/apps");
	assert.ok(!here(page).startsWith("/nxerp/apps"), "a customer is not shown the launcher");
	await open(page, "/desk");
	assert.ok(!here(page).startsWith("/desk"), "a customer cannot open Desk");
	await context.close();
});

// --- unauthenticated deep links, expiry, logout -------------------------------------------------------------

test("a deep link while signed out goes to /login and comes back after sign-in", async () => {
	const { context, page } = await session(browser);
	await page.goto(`${BASE}/helpdesk/tickets`, { waitUntil: "domcontentloaded" });
	await page.waitForURL(/\/login/, { timeout: 30000 });
	assert.equal(url(page).pathname, "/login");
	assert.ok(url(page).searchParams.get("redirect-to"), "the return target is carried");
	await page.fill("#login_email", email("agent"));
	await page.fill("#login_password", PASSWORD);
	await Promise.all([page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 45000 }), page.click("section.for-login button[type=submit]")]);
	await page.waitForTimeout(3000);
	assert.match(here(page), /^\/helpdesk/);
	await context.close();
});

test("a deep link to an app the user lacks is not honoured after sign-in", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("agent"), PASSWORD, { redirectTo: "/desk/customer" });
	assert.match(here(page), /^\/helpdesk/, `landed on ${here(page)}`);
	await context.close();
});

test("an expired session sends the user to /login with the page they wanted, and sign-in returns them", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("expiry"), PASSWORD);
	assert.match(here(page), /^\/helpdesk/);
	await fixture("expire_sessions", { user: email("expiry") }); // the server forgets the session, as it does on expiry
	await page.goto(`${BASE}/helpdesk/tickets`, { waitUntil: "domcontentloaded" });
	await page.waitForURL(/\/login/, { timeout: 45000 });
	assert.equal(url(page).pathname, "/login");
	await page.fill("#login_email", email("expiry"));
	await page.fill("#login_password", PASSWORD);
	await Promise.all([page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 45000 }), page.click("section.for-login button[type=submit]")]);
	await page.waitForTimeout(3000);
	assert.match(here(page), /^\/helpdesk/);
	await context.close();
});

test("logging out ends the session: protected pages need a sign-in again", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("both"), PASSWORD);
	await Promise.all([page.waitForURL(/\/login/, { timeout: 30000 }), page.click('a[href="/logout"]')]);
	await page.goto(`${BASE}/nxerp/apps`, { waitUntil: "domcontentloaded" });
	await page.waitForURL(/\/login/, { timeout: 30000 });
	const status = await page.evaluate(async () => (await fetch("/api/method/frappe.auth.get_logged_user")).status);
	assert.ok([401, 403].includes(status), `the API still answered ${status} after logout`);
	await context.close();
});

// --- wrong password, disabled user -------------------------------------------------------------------------

test("a wrong password shows a plain error, stays on /login and shows no stack trace", async () => {
	const { context, page } = await session(browser);
	const message = await failedSignIn(page, email("agent"), "definitely-not-the-password");
	assert.equal(url(page).pathname, "/login");
	assert.match(message, /invalid|incorrect|login/i, `error text was: ${message}`);
	const text = await visibleText(page);
	assert.ok(!/Traceback|frappe\.exceptions|File "/.test(text), "no stack trace on the page");
	await context.close();
});

test("a disabled user cannot sign in and learns nothing more than a wrong password would tell", async () => {
	const { context, page } = await session(browser);
	await failedSignIn(page, email("disabled"), PASSWORD);
	assert.equal(url(page).pathname, "/login");
	const text = await visibleText(page);
	assert.ok(!/Traceback|frappe\.exceptions|File "/.test(text));
	await context.close();
});

// --- tampered redirect-to ------------------------------------------------------------------------------------

for (const payload of EVIL) {
	test(`a tampered redirect-to (${payload}) never leaves the site`, async () => {
		const { context, page } = await session(browser);
		const seen = [];
		page.on("framenavigated", (f) => f === page.mainFrame() && seen.push(f.url()));
		await signIn(page, email("agent"), PASSWORD, { redirectTo: payload });
		await page.waitForTimeout(2500);
		assert.ok(seen.every((u) => u.startsWith(BASE)), `left the site: ${seen.filter((u) => !u.startsWith(BASE)).join(", ")}`);
		assert.match(here(page), /^\/helpdesk/, `landed on ${here(page)}`);
		await context.close();
	});
}

test("a tampered redirect-to on the router itself is ignored for a signed-in user", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("both"), PASSWORD);
	for (const payload of EVIL) {
		const response = await page.request.get(`${BASE}/nxerp/go?redirect-to=${encodeURIComponent(payload)}`, { maxRedirects: 0 });
		const location = response.headers()["location"] || "";
		assert.ok(!/evil\.example|^javascript:/i.test(location), `${payload} -> ${location}`);
		assert.ok(location.startsWith("/") && !location.startsWith("//"), `${payload} -> ${location}`);
	}
	await context.close();
});
