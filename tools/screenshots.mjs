// Visual check of the palette on real pages. Runs INSIDE the bench container against the
// local site, with the Chromium that ships in the bench image:
//
//   docker compose -p nxerp-dev exec -e SHOT_USER=Administrator -e SHOT_PASSWORD=... bench \
//     bash -lc 'cd /tmp && npm i --silent playwright-core && node /workspace/tools/screenshots.mjs'
//
// Writes PNGs to /tmp/shots (copy them out with `docker compose cp`). Never prints credentials.
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire("/tmp/");
const { chromium } = require("playwright-core");

const base = process.env.SHOT_BASE || "http://localhost:8000";
const user = process.env.SHOT_USER;
const password = process.env.SHOT_PASSWORD;
const out = "/tmp/shots";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
	executablePath: "/usr/bin/chromium-headless-shell",
	args: ["--no-sandbox", "--disable-gpu"],
});

async function shoot(page, name, url) {
	await page.goto(base + url, { waitUntil: "networkidle", timeout: 60000 }).catch(() => {});
	await page.waitForTimeout(1500);
	await page.screenshot({ path: `${out}/${name}.png` });
	console.log(`${name}: ${page.url().replace(base, "")}`);
}

// The app prefers the theme saved on the user (User.desk_theme) over the browser setting, so set
// that first (Light/Dark), then run with SHOT_SCHEMES=light or dark.
for (const scheme of (process.env.SHOT_SCHEMES || "light,dark").split(",")) {
	const context = await browser.newContext({
		viewport: { width: 1440, height: 900 },
		colorScheme: scheme,
	});
	const page = await context.newPage();
	if (scheme === "light") await shoot(page, "login", "/login");
	if (user && password) {
		await context.request.post(`${base}/api/method/login`, { form: { usr: user, pwd: password } });
		await shoot(page, `helpdesk-home-${scheme}`, "/helpdesk/home");
		await shoot(page, `helpdesk-tickets-${scheme}`, "/helpdesk/tickets");
		await shoot(page, `desk-${scheme}`, "/desk");
	}
	await context.close();
}
await browser.close();
