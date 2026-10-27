// Shared helpers for the Playwright suite. Runs INSIDE the bench container (see run.sh), against the dev site,
// with the Chromium that ships in the bench image. Credentials come from the environment and are never printed.
import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire("/tmp/");
export const { chromium } = require("playwright-core");

export const BASE = process.env.E2E_BASE || "http://localhost:8001";
export const SITE = process.env.E2E_SITE || "nxerp-e2e.localhost";
export const PASSWORD = process.env.NXERP_E2E_PASSWORD;
export const ADMIN_PASSWORD = process.env.NXERP_ADMIN_PASSWORD;
export const SHOTS = process.env.E2E_SHOTS || "/tmp/e2e-shots";
mkdirSync(SHOTS, { recursive: true });

export const email = (key) => `nxt-e2e-${key}@example.test`;
export const url = (page) => new URL(page.url());
export const here = (page) => url(page).pathname + url(page).search;

export async function launch() {
	return chromium.launch({
		executablePath: "/usr/bin/chromium-headless-shell",
		args: ["--no-sandbox", "--disable-gpu"],
	});
}

export async function session(browser, options = {}) {
	const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, ...options });
	const page = await context.newPage();
	return { context, page };
}

/** Fill the real login form and submit it. Resolves once the browser has left /login. */
export async function signIn(page, user, password, { redirectTo } = {}) {
	const query = redirectTo === undefined ? "" : `?redirect-to=${encodeURIComponent(redirectTo)}`;
	await page.goto(`${BASE}/login${query}`, { waitUntil: "domcontentloaded" });
	await page.fill("#login_email", user);
	await page.fill("#login_password", password);
	await Promise.all([
		page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 45000 }),
		page.click("section.for-login button[type=submit]"),
	]);
	await settle(page);
}

/** The login form, submitted, expecting to STAY on /login. Returns the visible error text. */
export async function failedSignIn(page, user, password) {
	await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
	await page.fill("#login_email", user);
	await page.fill("#login_password", password);
	await page.click("section.for-login button[type=submit]");
	await page.waitForTimeout(2500);
	return (await page.locator("section.for-login .login-error-banner, .login-error-banner:visible").allInnerTexts()).join(" ").trim();
}

/** Navigate and wait for the document, then for the app (Desk and the Helpdesk SPA keep loading after `load`). */
export async function open(page, path) {
	await page.goto(BASE + path, { waitUntil: "domcontentloaded", timeout: 90000 });
	await settle(page);
	await page.waitForTimeout(1500); // client-side redirects inside the SPA / Desk
	await settle(page);
}

export async function settle(page) {
	await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
}

export async function tiles(page) {
	return page.$$eval("a.nxp-tile[data-app]", (nodes) => nodes.map((n) => n.dataset.app));
}

export async function shot(page, name) {
	await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

const shellQuote = (text) => text.split("'").join(String.fromCharCode(39, 92, 39, 39)); // ' -> '\'' inside '...'

/** Site config is read by each web worker for up to 60 s (frappe/config.py ttl=60): set, then wait it out. */
export function setConfig(key, value) {
	const json = shellQuote(JSON.stringify(value));
	execSync(`cd /home/frappe/frappe-bench && bench --site ${SITE} set-config -p ${key} '${json}'`, { stdio: "pipe" });
}

export async function waitForConfig(check, { timeoutMs = 90000, everyMs = 3000 } = {}) {
	const deadline = Date.now() + timeoutMs;
	for (;;) {
		if (await check()) return true;
		if (Date.now() > deadline) return false;
		await new Promise((r) => setTimeout(r, everyMs));
	}
}

/** Call a function in nxerp.tests.e2e_fixtures on the site; returns its printed output. */
export function fixture(fn, kwargs = {}) {
	const json = shellQuote(JSON.stringify(kwargs));
	return execSync(
		`cd /home/frappe/frappe-bench && bench --site ${SITE} execute nxerp.tests.e2e_fixtures.${fn} --kwargs '${json}' 2>&1`,
		{ encoding: "utf-8", env: process.env },
	);
}
