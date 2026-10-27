// First-run flow on a FRESH site (nothing set up, no users): the NXERP login, Administrator's first sign-in,
// the setup wizard, and what the person who finishes the wizard sees. Runs first; it completes the wizard so the
// other suites run on a properly set-up site.
import assert from "node:assert/strict";
import test, { after, before } from "node:test";
import { ADMIN_PASSWORD, BASE, PASSWORD, email, fixture, here, launch, open, session, shot, signIn, tiles, url } from "./lib.mjs";

let browser;
before(async () => (browser = await launch()));
after(async () => browser.close());

const OWNER = email("owner");

test("a fresh site serves the NXERP login", async () => {
	const { context, page } = await session(browser);
	await open(page, "/login");
	assert.equal(url(page).pathname, "/login");
	assert.ok(await page.locator(".nx-shell").count(), "the NXERP login is served");
	assert.equal(await page.locator("#login_email").count(), 1);
	await context.close();
});

test("Administrator's first sign-in goes to the setup wizard, not the launcher", async () => {
	const { context, page } = await session(browser);
	await signIn(page, "Administrator", ADMIN_PASSWORD);
	await page.waitForTimeout(4000);
	assert.match(here(page), /^\/desk/, `landed on ${here(page)}`);
	assert.ok(!here(page).startsWith("/nxerp/apps"), "the launcher must wait until setup is done");
	await shot(page, "first-run-setup-wizard");
	await context.close();
});

test("completing the setup wizard unlocks the launcher for Administrator", { timeout: 900000 }, async () => {
	const { context, page } = await session(browser);
	await signIn(page, "Administrator", ADMIN_PASSWORD);
	await page.waitForTimeout(3000);
	const csrf = await page.evaluate(() => window.frappe && frappe.csrf_token);
	assert.ok(csrf, "a desk page with a CSRF token");
	const args = {
		language: "en",
		country: "India",
		timezone: "Asia/Kolkata",
		currency: "INR",
		company_name: "E2E Test Company",
		company_abbr: "ETC",
		chart_of_accounts: "Standard",
		fy_start_date: "2026-04-01",
		fy_end_date: "2027-03-31",
		full_name: "E2E Owner",
		email: OWNER,
		password: PASSWORD,
	};
	const done = await page.request.post(`${BASE}/api/method/frappe.desk.page.setup_wizard.setup_wizard.setup_complete`, {
		headers: { "X-Frappe-CSRF-Token": csrf },
		form: { args: JSON.stringify(args) },
		timeout: 420000, // the wizard creates the company, chart of accounts and defaults
	});
	assert.ok(done.ok(), `setup_complete answered ${done.status()}`);
	let complete = false;
	for (let i = 0; i < 80 && !complete; i++) {
		await new Promise((r) => setTimeout(r, 5000));
		complete = /SETUP=1/.test(fixture("setup_state"));
	}
	assert.ok(complete, "the setup wizard did not finish within the time allowed");

	await context.clearCookies();
	await signIn(page, "Administrator", ADMIN_PASSWORD);
	assert.equal(url(page).pathname, "/nxerp/apps", "Administrator reaches the launcher once the site is set up");
	assert.deepEqual(await tiles(page), ["erpnext", "helpdesk"]);
	await context.close();
});

test("the person who finished the wizard (Frappe gives them every role) reaches the launcher with both apps", async () => {
	const { context, page } = await session(browser);
	await signIn(page, OWNER, PASSWORD);
	assert.equal(url(page).pathname, "/nxerp/apps", `landed on ${here(page)}`);
	assert.deepEqual(await tiles(page), ["erpnext", "helpdesk"]);
	await shot(page, "first-run-owner-launcher");
	await context.close();
});
