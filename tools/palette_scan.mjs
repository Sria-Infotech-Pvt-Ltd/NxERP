// Palette coverage scan. Runs INSIDE the bench container against the local site and measures the
// colors the browser actually renders on each page, so "the palette is on every page" is a
// measurement and not an opinion.
//
//   docker compose -p nxerp-dev exec -T -e SCAN_USER=... -e SCAN_PASSWORD=... bench \
//     bash -lc 'cd /tmp && npm i --silent playwright-core && node /workspace/tools/palette_scan.mjs [role]'
//
// role: agent (default), settings (every Settings tab), customer, guest, desk. Prints, per page, the visible colors that are neither
// warm neutrals, the amber accent, nor the status colors (red, green); the cool and violet hues
// are the leaks (frappe-ui defaults such as blue/purple that the palette should have replaced).
// Blue is allowed only where `ALLOW_SELECTORS` says it is a category color. Exits 1 on leaks.
// Never prints credentials. Writes screenshots to /tmp/scan.
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire("/tmp/");
const { chromium } = require("playwright-core");

const base = process.env.SCAN_BASE || "http://localhost:8000";
const role = process.argv[2] || "agent";
const user = process.env.SCAN_USER;
const password = process.env.SCAN_PASSWORD;
const ticket = process.env.SCAN_TICKET || "1";
mkdirSync("/tmp/scan", { recursive: true });

const PAGES = {
	guest: ["/login", "/login#forgot", "/helpdesk"],
	agent: [
		"/helpdesk/home",
		"/helpdesk/dashboard",
		"/helpdesk/tickets",
		`/helpdesk/tickets/${ticket}`,
		"/helpdesk/tickets/new",
		"/helpdesk/kb",
		"/helpdesk/customers",
		"/helpdesk/contacts",
		"/helpdesk/agents",
		"/helpdesk/teams",
		"/helpdesk/notifications",
		"/helpdesk/call-logs",
		"/helpdesk/search?q=welcome",
		"/helpdesk/not-a-page",
	],
	customer: ["/helpdesk/my-tickets", "/helpdesk/my-tickets/new", "/helpdesk/kb-public", `/helpdesk/my-tickets/${ticket}`],
	desk: ["/desk", "/desk/user", "/desk/todo", "/desk/customer", "/desk/sales-invoice/new", "/desk/report/Sales%20Register", "/me", "/update-password"],
};

// Elements whose cool hue is an intentional category color, by CSS selector.
const ALLOW_SELECTORS = [];

// Status/tag chips (SLA states, tags) are category colors by design: small pill-shaped div/span
// elements. They are counted and reported separately, never as leaks. Buttons, links, inputs and
// large surfaces in a cool hue are leaks.

const browser = await chromium.launch({
	executablePath: "/usr/bin/chromium-headless-shell",
	args: ["--no-sandbox", "--disable-gpu"],
});

function scan(allow) {
	const parse = (s) => {
		const m = s.match(/rgba?\(([^)]+)\)/) || s.match(/color\(srgb ([^)]+)\)/);
		if (!m) return null;
		const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
		if (s.startsWith("color(")) p.splice(0, 3, ...p.slice(0, 3).map((v) => v * 255));
		return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
	};
	const hsl = ({ r, g, b }) => {
		r /= 255; g /= 255; b /= 255;
		const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
		if (!d) return { h: 0, s: 0, l };
		const s = d / (1 - Math.abs(2 * l - 1));
		let h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
		h = (h * 60 + 360) % 360;
		return { h, s, l };
	};
	const bucket = ({ h, s, l }) => {
		if (s < 0.22 || l > 0.97 || l < 0.04) return "neutral";
		if (h >= 20 && h < 70) return "warm"; // amber, sand, taupe
		if (h < 20 || h >= 340) return "red";
		if (h >= 70 && h < 170) return "green";
		if (h >= 170 && h < 265) return "cool";
		return "violet";
	};
	const out = [];
	const visible = (el) => {
		const r = el.getBoundingClientRect();
		const cs = getComputedStyle(el);
		return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none" && +cs.opacity > 0;
	};
	for (const el of document.querySelectorAll("body *")) {
		if (!visible(el)) continue;
		if (allow.some((sel) => el.closest(sel))) continue;
		const cs = getComputedStyle(el);
		const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
		const props = [["background-color", cs.backgroundColor]];
		if (hasText) props.push(["color", cs.color]);
		if (parseFloat(cs.borderTopWidth) > 0) props.push(["border", cs.borderTopColor]);
		if (el instanceof SVGElement) {
			props.push(["fill", cs.fill], ["stroke", cs.stroke]);
		}
		const cls0 = typeof el.className === "string" ? el.className : "";
		const chip =
			["DIV", "SPAN"].includes(el.tagName) &&
			/inline-flex|inline-block/.test(cls0) &&
			/rounded/.test(cls0) &&
			(el.textContent || "").trim().length <= 30;
		for (const [prop, value] of props) {
			const c = parse(value || "");
			if (!c || c.a < 0.08) continue;
			const b = bucket(hsl(c));
			if (b !== "cool" && b !== "violet") continue;
			const cls = (typeof el.className === "string" ? el.className : "").split(/\s+/).filter(Boolean).slice(0, 3).join(".");
			out.push({ chip, b, prop, value, el: el.tagName.toLowerCase() + (cls ? "." + cls : ""), text: (el.textContent || "").trim().slice(0, 28) });
		}
	}
	return out;
}

let leaks = 0;
let chips = 0;
let pages = 0;
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
if (role !== "guest" && user && password) {
	await context.request.post(`${base}/api/method/login`, { form: { usr: user, pwd: password } });
}
async function report(label) {
	let all = [];
	for (let attempt = 0; attempt < 4; attempt++) {
		// Desk keeps a realtime socket open, so "network idle" never settles there: settle by time
		if (!process.env.SCAN_FAST) await page.waitForLoadState("networkidle").catch(() => {});
		try {
			all = await page.evaluate(scan, ALLOW_SELECTORS);
			break;
		} catch {
			await page.waitForTimeout(1500); // a client-side redirect was still in flight
		}
	}
	const found = all.filter((f) => !f.chip);
	chips += all.length - found.length;
	const name = label.replace(/[^a-z0-9]+/gi, "_");
	await page.screenshot({ path: `/tmp/scan/${role}${name}.png` }).catch(() => console.log("   (screenshot failed)"));
	const groups = new Map();
	for (const f of found) {
		const k = `${f.b} ${f.prop} ${f.value} ${f.el}`;
		const g = groups.get(k) || { ...f, n: 0 };
		g.n++;
		groups.set(k, g);
	}
	leaks += groups.size;
	pages++;
	console.log(`${label}: ${found.length} off-palette uses, ${groups.size} distinct`);
	for (const g of [...groups.values()].sort((x, y) => y.n - x.n).slice(0, 12)) {
		console.log(`   ${g.b.padEnd(6)} ${g.prop.padEnd(16)} ${g.value.padEnd(26)} x${String(g.n).padEnd(3)} ${g.el}  "${g.text}"`);
	}
}

if (role === "settings") {
	// Every Settings tab of the Helpdesk agent app, plus the first "new/add" form on each tab.
	const TABS = ["Profile", "Preferences", "Email Accounts", "Email Notifications", "General", "Agents", "Invite Agents", "Teams", "SLA Policies", "Business Holidays", "Assignment Rules", "Field Dependencies", "Saved Replies", "Telephony", "ERPNext"];
	await page.goto(base + "/helpdesk/home", { waitUntil: "networkidle" }).catch(() => {});
	await page.waitForTimeout(1500);
	await page.locator("text=Administrator").first().click();
	await page.locator("text=Settings").first().click();
	await page.waitForTimeout(1200);
	const dialog = page.locator('[role="dialog"]').first();
	for (const tab of TABS) {
		const item = dialog.getByText(tab, { exact: true }).first();
		if (!(await item.count())) { console.log(`${tab}: tab not found`); continue; }
		await item.click().catch(() => {});
		await page.waitForTimeout(900);
		await report(`settings/${tab}`);
		// the content pane starts right of the sidebar (x > 440); sidebar items must not match
		let add = null;
		for (const btn of await dialog.getByRole("button").all()) {
			const box = await btn.boundingBox();
			const label = ((await btn.innerText().catch(() => "")) || "").trim();
			if (box && box.x > 440 && /^(\+\s*)?(new|add|create|invite|connect|edit)/i.test(label)) { add = btn; break; }
		}
		if (add) {
			await add.click({ timeout: 3000 }).catch(() => {});
			await page.waitForTimeout(900);
			await report(`settings/${tab}/new`);
			await page.keyboard.press("Escape");
			await page.waitForTimeout(400);
			if (!(await dialog.isVisible().catch(() => false))) {
				await page.locator("text=Administrator").first().click();
				await page.locator("text=Settings").first().click();
				await page.waitForTimeout(1000);
			}
		}
	}
} else {
	for (const path of PAGES[role]) {
		await page.goto(base + path, { waitUntil: process.env.SCAN_FAST ? "domcontentloaded" : "networkidle", timeout: 60000 }).catch(() => {});
		await page.waitForTimeout(process.env.SCAN_FAST ? 6000 : 1500);
		await report(`${path} -> ${page.url().replace(base, "")}`);
	}
}
await browser.close();
console.log(`
${role}: ${pages} views scanned; off-palette leaks (distinct): ${leaks}; status/tag chips in category colors (not leaks): ${chips}`);
process.exit(leaks ? 1 : 0);
