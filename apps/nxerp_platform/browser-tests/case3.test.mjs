// Case 3: a user with Helpdesk plus a third application. No third app ships, so this registers a clearly
// marked TEST-ONLY entry through site config (honoured only when the site has allow_tests on; see
// apps/nxerp_platform/nxerp/registry.py) and removes it afterwards. The stand-in app is the page /nxerp/test-app.
import assert from "node:assert/strict";
import test, { after, before } from "node:test";
import { ADMIN_PASSWORD, BASE, PASSWORD, email, here, launch, session, shot, signIn, tiles, url, setConfig, waitForConfig } from "./lib.mjs";

const TEST_APP = {
	key: "test-projects",
	title: "Test Projects",
	route: "/nxerp/test-app",
	access_role: "NXERP Access: Test Projects",
	order: 30,
};

let browser;
before(async () => {
	browser = await launch();
	setConfig("nxerp_test_apps", [TEST_APP]);
	// web workers read site config for up to 60 s (frappe/config.py): wait until the server shows the entry
	const { context, page } = await session(browser);
	const seen = await waitForConfig(async () => {
		await context.clearCookies();
		await page.request.post(`${BASE}/api/method/login`, { form: { usr: email("manager"), pwd: PASSWORD } });
		const apps = await page.request.get(`${BASE}/api/method/frappe.apps.get_apps`);
		return apps.ok() && JSON.stringify(await apps.json()).includes("test-projects");
	});
	await context.close();
	assert.ok(seen, "the test-only app never appeared (site config cache)");
});
after(async () => {
	setConfig("nxerp_test_apps", []);
	await browser.close();
});

test("Case 3: Helpdesk plus the third app: the launcher lists exactly those two, with their own names", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("manager"), PASSWORD);
	assert.equal(url(page).pathname, "/nxerp/apps");
	assert.deepEqual(await tiles(page), ["helpdesk", "test-projects"]);
	const names = await page.$$eval("a.nxp-tile .nxp-tile-title", (n) => n.map((x) => x.textContent.trim()));
	assert.deepEqual(names, ["Helpdesk", "Test Projects"]);
	assert.equal(await page.locator('a.nxp-tile[data-app="erpnext"]').count(), 0, "a Helpdesk manager is not an ERPNext user");
	await shot(page, "launcher-case3-desktop");
	await context.close();
});

test("Case 3: the third app's tile leads to it, and only holders of its role may open it", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("manager"), PASSWORD);
	await Promise.all([page.waitForURL(/\/nxerp\/test-app/), page.click('a.nxp-tile[data-app="test-projects"]')]);
	assert.match(await page.locator("h1").innerText(), /Test Projects/);
	await context.close();

	const other = await session(browser);
	await signIn(other.page, email("agent"), PASSWORD);
	assert.equal(await tiles(other.page).then((t) => t.length), 0, "a single-app user is not on the launcher");
	await other.page.goto(`${BASE}/nxerp/test-app`, { waitUntil: "domcontentloaded" });
	assert.equal(url(other.page).pathname, "/nxerp/no-access");
	await other.context.close();

	const guest = await session(browser);
	await guest.page.goto(`${BASE}/nxerp/test-app`, { waitUntil: "domcontentloaded" });
	assert.equal(url(guest.page).pathname, "/login");
	await guest.context.close();
});

test("Case 3: Administrator sees every app, including the test-only one, and it is marked as such in its own page", async () => {
	const { context, page } = await session(browser);
	await signIn(page, "Administrator", ADMIN_PASSWORD);
	assert.deepEqual(await tiles(page), ["erpnext", "helpdesk", "test-projects"]);
	await context.close();
});
