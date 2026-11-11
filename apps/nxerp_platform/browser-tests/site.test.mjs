// The public site (Home, Products, a product page): screenshots at four widths in light and dark, no horizontal
// scroll down to 320px, the Tab key reaches everything with a visible focus indicator, the theme is set before the
// first paint (no flash), text contrast measured from the rendered page, and one journey through the three pages.
//
// Run on its own against a running stack (inside the bench container):
//   E2E_BASE=http://localhost:8000 NXERP_E2E_PASSWORD=... node --test apps/nxerp_platform/browser-tests/site.test.mjs
// or with the rest of the suite through run.sh. Screenshots go to UI_SHOTS (default /tmp/ui-shots), not to the phase 3 folder.
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import test, { after, before } from "node:test";
import { BASE, PASSWORD, email, launch, open, session, signIn } from "./lib.mjs";
import { audit, keyboardWalk } from "./a11y.mjs";

const OUT = process.env.UI_SHOTS || "/tmp/ui-shots";
mkdirSync(OUT, { recursive: true });

const VIEWPORTS = {
	"360x800": { width: 360, height: 800 },
	"768x1024": { width: 768, height: 1024 },
	"1280x800": { width: 1280, height: 800 },
	"1920x1080": { width: 1920, height: 1080 },
};
const SCHEMES = ["light", "dark"];
const PAGES = [
	{ name: "home", path: "/" },
	{ name: "products", path: "/products" },
	{ name: "product-helpdesk", path: "/products/helpdesk" },
	{ name: "product-erpnext", path: "/products/erpnext" },
];

let browser;
before(async () => (browser = await launch()));
after(async () => browser.close());

async function visit(path, { scheme = "light", viewport = VIEWPORTS["1280x800"], who = null, reducedMotion = "reduce" } = {}) {
	const { context, page } = await session(browser, { viewport, colorScheme: scheme, reducedMotion, hasTouch: viewport.width < 500 });
	if (who) await signIn(page, email(who), PASSWORD);
	await open(page, path);
	return { context, page };
}

// Full page: the viewport is grown to the page's height first (the background is fixed, so a plain full-page capture would show a seam).
async function shot(page, name) {
	const viewport = page.viewportSize();
	const height = await page.evaluate(() => Math.max(document.documentElement.scrollHeight, window.innerHeight));
	await page.setViewportSize({ width: viewport.width, height });
	await page.waitForTimeout(150);
	await page.screenshot({ path: `${OUT}/${name}.jpg`, type: "jpeg", quality: 82 });
	await page.setViewportSize(viewport);
}

test("screenshots: every public page at 360, 768, 1280 and 1920 wide, light and dark", async () => {
	for (const p of PAGES) {
		for (const scheme of SCHEMES) {
			for (const [label, viewport] of Object.entries(VIEWPORTS)) {
				const { context, page } = await visit(p.path, { scheme, viewport });
				await shot(page, `${p.name}-${label}-${scheme}`);
				await context.close();
			}
		}
	}
});

test("screenshots: signed-in variants (a holder sees Open, a non-holder sees Get started)", async () => {
	for (const scheme of SCHEMES) {
		for (const label of ["360x800", "1280x800"]) {
			const viewport = VIEWPORTS[label];
			let v = await visit("/nxerp/home", { scheme, viewport, who: "both" });
			await shot(v.page, `home-signed-in-${label}-${scheme}`);
			await v.context.close();
			v = await visit("/products/helpdesk", { scheme, viewport, who: "agent" });
			await shot(v.page, `product-helpdesk-holder-${label}-${scheme}`);
			await v.context.close();
		}
	}
});

test("no horizontal scroll at 320px or at any shown width, signed out and signed in", async () => {
	const widths = [{ width: 320, height: 640 }, ...Object.values(VIEWPORTS)];
	for (const p of PAGES) {
		for (const scheme of SCHEMES) {
			for (const viewport of widths) {
				const { context, page } = await visit(p.path, { scheme, viewport });
				const m = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }));
				assert.ok(m.scroll <= m.inner, `${p.path} ${scheme} ${viewport.width}px: scrollWidth ${m.scroll} > innerWidth ${m.inner}`);
				await context.close();
			}
		}
	}
	for (const who of ["both", "agent"]) {
		for (const path of ["/nxerp/home", "/products", "/products/helpdesk"]) {
			const { context, page } = await visit(path, { viewport: { width: 320, height: 640 }, who });
			const m = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }));
			assert.ok(m.scroll <= m.inner, `signed in (${who}) ${path} at 320px: scrollWidth ${m.scroll} > innerWidth ${m.inner}`);
			await context.close();
		}
	}
});

test("accessibility basics on every page: one h1, landmarks, labels, names, alt text", async () => {
	for (const p of PAGES) {
		for (const scheme of SCHEMES) {
			const { context, page } = await visit(p.path, { scheme });
			// the generic contrast check skips anything over a gradient; the contrast test below measures those
			const problems = (await audit(page)).filter((x) => !x.startsWith("low contrast"));
			assert.deepEqual(problems, [], `${p.path} (${scheme}): ${problems.join(" | ")}`);
			await context.close();
		}
	}
});

test("keyboard: the skip link comes first, every control is reachable with Tab and shows a focus indicator", async () => {
	for (const p of PAGES) {
		const { context, page } = await visit(p.path);
		const { order, noIndicator } = await keyboardWalk(page, 60);
		assert.match(order[0].label, /skip/i, `${p.path}: the first stop is the skip link`);
		assert.deepEqual(noIndicator, [], `${p.path}: no visible focus indicator on: ${noIndicator.join(", ")}`);
		const reachable = new Set(order.map((o) => o.label));
		const visible = await page.$$eval("a[href], button", (nodes) =>
			nodes
				.filter((n) => n.getClientRects().length && getComputedStyle(n).visibility !== "hidden")
				.map((n) => (n.getAttribute("aria-label") || n.textContent || "").trim().slice(0, 40)),
		);
		for (const label of visible) assert.ok(reachable.has(label), `${p.path}: "${label}" is not reachable with Tab`);
		await context.close();
	}
});

test("touch targets are at least 44px on the header and the calls to action", async () => {
	for (const viewport of [VIEWPORTS["360x800"], VIEWPORTS["1280x800"]]) {
		for (const p of PAGES) {
			const { context, page } = await visit(p.path, { viewport });
			const small = await page.$$eval(".nxp-header a, .nxp-header button, .nxp-cta", (nodes) =>
				nodes
					.filter((n) => n.getClientRects().length)
					.map((n) => ({ label: (n.getAttribute("aria-label") || n.textContent || "").trim().slice(0, 30), h: n.getBoundingClientRect().height, w: n.getBoundingClientRect().width }))
					.filter((n) => n.h < 43.5 || n.w < 43.5),
			);
			assert.deepEqual(small, [], `${p.path} at ${viewport.width}px: ${JSON.stringify(small)}`);
			await context.close();
		}
	}
});

test("theme: data-theme is set before the first paint and never flips; light, dark and system all render", async () => {
	const cases = [
		{ stored: null, scheme: "dark", expect: "dark" },
		{ stored: null, scheme: "light", expect: "light" },
		{ stored: "light", scheme: "dark", expect: "light" },
		{ stored: "dark", scheme: "light", expect: "dark" },
		{ stored: "system", scheme: "dark", expect: "dark" },
	];
	for (const c of cases) {
		for (const p of PAGES) {
			const context = await browser.newContext({ viewport: VIEWPORTS["1280x800"], colorScheme: c.scheme });
			const page = await context.newPage();
			await page.addInitScript((stored) => {
				try {
					if (stored) localStorage.setItem("theme", stored);
				} catch (e) {}
				window.__themeLog = [];
				window.__firstPaint = null;
				// observe the document, not <html>: this script runs before <html> exists
				new MutationObserver(() => window.__themeLog.push({ t: performance.now(), v: document.documentElement.getAttribute("data-theme") })).observe(
					document,
					{ attributes: true, subtree: true, attributeFilter: ["data-theme"] },
				);
				new PerformanceObserver((list) => {
					for (const e of list.getEntries()) if (window.__firstPaint === null) window.__firstPaint = e.startTime;
				}).observe({ type: "paint", buffered: true });
			}, c.stored);
			await page.goto(BASE + p.path, { waitUntil: "load" });
			await page.waitForTimeout(400);
			const r = await page.evaluate(() => ({ log: window.__themeLog, paint: window.__firstPaint, now: document.documentElement.getAttribute("data-theme") }));
			const label = `${p.path} stored=${c.stored} scheme=${c.scheme}`;
			assert.equal(r.now, c.expect, `${label}: final theme`);
			assert.ok(r.log.length >= 1, `${label}: data-theme was never set`);
			assert.deepEqual([...new Set(r.log.map((x) => x.v))], [c.expect], `${label}: the theme flipped: ${JSON.stringify(r.log)}`);
			if (r.paint !== null) assert.ok(r.log[0].t <= r.paint, `${label}: data-theme (${r.log[0].t}) was set after the first paint (${r.paint})`);
			await context.close();
		}
	}
});

test("the theme toggle switches, remembers the choice and carries it to the next page", async () => {
	const { context, page } = await visit("/", { scheme: "light" });
	assert.equal(await page.getAttribute("html", "data-theme"), "light");
	await page.click("#nxp-theme-toggle");
	assert.equal(await page.getAttribute("html", "data-theme"), "dark");
	assert.equal(await page.evaluate(() => localStorage.getItem("theme")), "dark");
	await page.goto(BASE + "/products", { waitUntil: "domcontentloaded" });
	assert.equal(await page.getAttribute("html", "data-theme"), "dark");
	await page.click("#nxp-theme-toggle");
	assert.equal(await page.getAttribute("html", "data-theme"), "light");
	await context.close();
});

test("contrast: text against its effective background, measured from the rendered page", async () => {
	const rows = [];
	for (const p of PAGES) {
		for (const scheme of SCHEMES) {
			const { context, page } = await visit(p.path, { scheme });
			const result = await page.evaluate(measureContrast, { page: p.name, scheme });
			rows.push(...result);
			await context.close();
		}
	}
	writeFileSync(`${OUT}/contrast.json`, JSON.stringify(rows, null, 1));
	const failing = rows.filter((r) => r.ratio < r.min);
	assert.deepEqual(
		failing.map((r) => `${r.page} ${r.scheme} "${r.text}" ${r.ratio} < ${r.min}`),
		[],
	);
});

test("journey: Home, then Products, then a product page, then Sign in", async () => {
	const { context, page } = await visit("/");
	assert.equal(await page.locator("h1").count(), 1);
	assert.match(await page.locator("h1").innerText(), /business applications/i);
	await page.getByRole("link", { name: "Explore products" }).first().click();
	await page.waitForURL(/\/products$/);
	assert.equal(await page.locator("a.nxp-tile").count(), 2, "exactly the two installed products");
	await page.locator('a.nxp-tile[data-product="helpdesk"]').click();
	await page.waitForURL(/\/products\/helpdesk$/);
	assert.match(await page.locator("h1").innerText(), /Sria Helpdesk/);
	assert.equal(await page.locator(".nxp-checks li").count(), 4);
	assert.equal(await page.locator(".nxp-steps li").count(), 3);
	await page.getByRole("link", { name: "Log in" }).click();
	await page.waitForURL(/\/login/);
	assert.ok(await page.locator("#login_email").count(), "the stock login form is there");
	await context.close();
});

/** Runs in the page. Returns one row per text element: the measured ratio and the minimum it must reach. */
function measureContrast({ page, scheme }) {
	const parse = (c) => {
		let m = c.match(/^rgba?\(([^)]+)\)/);
		if (m) {
			const [r, g, b, a = 1] = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
			return { r, g, b, a };
		}
		m = c.match(/^color\(srgb ([^)]+)\)/);
		if (m) {
			const [r, g, b, a = 1] = m[1].split(/[ \/]+/).filter(Boolean).map(Number);
			return { r: r * 255, g: g * 255, b: b * 255, a };
		}
		return null;
	};
	const token = (name) => {
		const probe = document.createElement("i");
		probe.style.color = `var(${name})`;
		document.body.appendChild(probe);
		const c = parse(getComputedStyle(probe).color);
		probe.remove();
		return c;
	};
	const over = (top, bottom) => {
		const a = top.a + bottom.a * (1 - top.a);
		const mix = (t, b) => (t * top.a + b * bottom.a * (1 - top.a)) / a;
		return { r: mix(top.r, bottom.r), g: mix(top.g, bottom.g), b: mix(top.b, bottom.b), a };
	};
	const lum = ({ r, g, b }) => {
		const f = (v) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
		return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
	};
	const ratio = (x, y) => {
		const [hi, lo] = [lum(x), lum(y)].sort((p, q) => q - p);
		return (hi + 0.05) / (lo + 0.05);
	};
	const base = token("--surface-base");
	const glass = { ...token("--surface-elevation-1"), a: 0.64 }; // the lowest opacity of the glass gradient
	const backdrop = (el) => {
		const layers = [];
		for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
			const s = getComputedStyle(n);
			const c = parse(s.backgroundColor);
			if (c && c.a > 0) layers.push(c);
			if (c && c.a >= 0.99) break;
			if (s.backgroundImage !== "none" && n.matches(".nxp-card, .nxp-panel, .nxp-tile")) layers.push(glass);
		}
		let acc = { ...base, a: 1 };
		for (const layer of layers.reverse()) acc = over(layer, acc);
		return acc;
	};
	const rows = [];
	const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
	const seen = new Set();
	for (let node; (node = walker.nextNode()); ) {
		const el = node.parentElement;
		if (!el || seen.has(el) || !node.textContent.trim() || ["SCRIPT", "STYLE"].includes(el.tagName)) continue;
		if (!el.getClientRects().length || el.closest(".nxp-sr-only, .nxp-skip")) continue;
		seen.add(el);
		const s = getComputedStyle(el);
		const size = parseFloat(s.fontSize);
		const large = size >= 24 || (size >= 18.66 && parseInt(s.fontWeight, 10) >= 700);
		const bg = backdrop(el);
		// the gradient title is painted with two tokens; measure both ends
		const fgs = s.webkitTextFillColor === "rgba(0, 0, 0, 0)" ? [token("--ink-gray-9"), token("--surface-accent-8")] : [parse(s.color)];
		for (const fg of fgs) {
			if (!fg) continue;
			const text = fg.a < 1 ? over(fg, bg) : fg;
			rows.push({ page, scheme, text: node.textContent.trim().slice(0, 32), size, weight: s.fontWeight, ratio: Math.round(ratio(text, bg) * 100) / 100, min: large ? 3 : 4.5 });
		}
	}
	return rows;
}
