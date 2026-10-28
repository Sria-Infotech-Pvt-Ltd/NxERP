// docs/runbooks/login-recovery.md, executed: the kill-switch, an Administrator password reset and a break-glass
// System Manager, each with the exact bench command the runbook gives, then checked in a real browser.
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import test, { after, before } from "node:test";
import { ADMIN_PASSWORD, BASE, PASSWORD, SITE, email, fixture, here, launch, open, session, setConfig, shot, signIn, tiles, url, waitForConfig } from "./lib.mjs";

let browser;
before(async () => (browser = await launch()));
after(async () => {
	setConfig("nxerp_stock_login", 0);
	await browser.close();
});

const bench = (command, env = {}) =>
	execSync(`cd /home/frappe/frappe-bench && bench --site ${SITE} ${command} 2>&1`, { encoding: "utf-8", env: { ...process.env, ...env } });

test("runbook 1: the kill-switch serves Frappe's own login, people still land through the router, and it can be put back", async () => {
	bench("set-config -p nxerp_stock_login 1");
	const { context, page } = await session(browser);
	try {
		const stock = await waitForConfig(async () => {
			await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
			return (await page.locator(".nx-shell").count()) === 0 && (await page.locator("#login_email").count()) === 1;
		});
		assert.ok(stock, "the stock Frappe login was not served");
		await shot(page, "recovery-stock-login");
		await page.fill("#login_email", "Administrator");
		await page.fill("#login_password", ADMIN_PASSWORD);
		await Promise.all([page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 45000 }), page.keyboard.press("Enter")]);
		await page.waitForTimeout(3000);
		assert.equal(url(page).pathname, "/nxerp/apps", `landed on ${here(page)}: the router still decides`);
		assert.deepEqual(await tiles(page), ["erpnext", "helpdesk"]);
	} finally {
		bench("set-config -p nxerp_stock_login 0");
	}
	await context.clearCookies();
	const back = await waitForConfig(async () => {
		await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
		return (await page.locator(".nx-shell").count()) === 1;
	});
	assert.ok(back, "the NXERP login did not come back after the switch was cleared");
	await context.close();
});

test("runbook 2: set-admin-password replaces the Administrator password; the old one stops working", async () => {
	const NEW = `${PASSWORD}-recovered-7!`;
	const login = async (pwd) => {
		const r = await fetch(`${BASE}/api/method/login`, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ usr: "Administrator", pwd }) });
		return r.status;
	};
	try {
		bench(`set-admin-password "$E2E_NEW"`, { E2E_NEW: NEW });
		assert.equal(await login(NEW), 200, "the new password signs in");
		assert.notEqual(await login(ADMIN_PASSWORD), 200, "the old password is refused");
	} finally {
		bench(`set-admin-password "$E2E_OLD"`, { E2E_OLD: ADMIN_PASSWORD });
	}
	assert.equal(await login(ADMIN_PASSWORD), 200, "the original password is restored for the other suites");
});

test("runbook 4: add-system-manager makes a working administrator (Frappe gives it every role)", async () => {
	const user = "nxt-e2e-breakglass@example.test";
	bench(`add-system-manager ${user} --first-name Recovery --password "$E2E_PW"`, { E2E_PW: PASSWORD });
	try {
		const { context, page } = await session(browser);
		await signIn(page, user, PASSWORD);
		assert.equal(url(page).pathname, "/nxerp/apps", `landed on ${here(page)}`);
		assert.deepEqual(await tiles(page), ["erpnext", "helpdesk"]);
		await context.close();
	} finally {
		await fixture("delete_user", { user });
	}
});

test("a System Manager with no app grant gets the friendly page and the way to grant access", async () => {
	const { context, page } = await session(browser);
	await signIn(page, email("sysmgr"), PASSWORD);
	assert.equal(url(page).pathname, "/nxerp/no-access", "a System Manager holds no application by default");
	assert.equal(await page.locator("a[data-admin-hint]").count(), 1);
	await Promise.all([page.waitForURL(/\/desk\/user/, { timeout: 90000 }), page.click("a[data-admin-hint]")]);
	assert.match(here(page), /^\/desk\/user/, "the administrator can reach the place where access is granted");
	await context.close();
});
