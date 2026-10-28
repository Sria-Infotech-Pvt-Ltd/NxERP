// The three pages the platform owns (login, launcher, no-access): screenshots at desktop and phone widths in
// light and dark, plus accessibility basics (labels, landmarks, contrast, keyboard order, focus visibility,
// no horizontal scroll). Screenshots land in docs/evidence/phase3/.
import assert from "node:assert/strict";
import test, { after, before } from "node:test";
import { PASSWORD, email, launch, open, session, shot, signIn } from "./lib.mjs";
import { audit, keyboardWalk } from "./a11y.mjs";

const VIEWPORTS = { desktop: { width: 1440, height: 900 }, phone: { width: 390, height: 844 } };
let browser;
before(async () => (browser = await launch()));
after(async () => browser.close());

async function visit(name, who, path) {
	for (const scheme of ["light", "dark"]) {
		for (const [label, viewport] of Object.entries(VIEWPORTS)) {
			const { context, page } = await session(browser, { viewport, colorScheme: scheme, hasTouch: label === "phone" });
			if (who) await signIn(page, who, PASSWORD);
			await open(page, path);
			await shot(page, `${name}-${label}-${scheme}`);
			await context.close();
		}
	}
}

test("screenshots: login, launcher and no-access at desktop and phone width, light and dark", async () => {
	await visit("login", null, "/login");
	await visit("launcher", email("both"), "/nxerp/apps");
	await visit("no-access", email("none"), "/nxerp/no-access");
});

const PAGES = [
	{ name: "login", who: null, path: "/login", skipContrast: [".nx-hero"] },
	{ name: "launcher", who: email("both"), path: "/nxerp/apps", skipContrast: [] },
	{ name: "no-access", who: email("none"), path: "/nxerp/no-access", skipContrast: [] },
];

for (const p of PAGES) {
	for (const scheme of ["light", "dark"]) {
		for (const [label, viewport] of Object.entries(VIEWPORTS)) {
			test(`accessibility basics: ${p.name} (${label}, ${scheme})`, async () => {
				const { context, page } = await session(browser, { viewport, colorScheme: scheme, hasTouch: label === "phone" });
				if (p.who) await signIn(page, p.who, PASSWORD);
				await open(page, p.path);
				const problems = await audit(page, { skipContrast: p.skipContrast });
				assert.deepEqual(problems, [], `${p.name}: ${problems.join(" | ")}`);
				await context.close();
			});
		}
	}
	test(`keyboard: ${p.name} can be used with the Tab key and focus is always visible`, async () => {
		const { context, page } = await session(browser);
		if (p.who) await signIn(page, p.who, PASSWORD);
		await open(page, p.path);
		const { order, noIndicator } = await keyboardWalk(page);
		assert.ok(order.length >= 2, `only ${order.length} focus stops`);
		assert.deepEqual(noIndicator, [], `no visible focus indicator on: ${noIndicator.join(", ")}`);
		if (p.name !== "login") assert.match(order[0].label, /skip/i, "the first stop is the skip link");
		await context.close();
	});
}
