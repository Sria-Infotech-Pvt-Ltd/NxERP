// Accessibility basics, run inside the page: the checks a keyboard or screen-reader user would trip over first.
// Not a substitute for an audit with assistive technology (said so in docs/architecture/routes.md).

/** Returns a list of problems found on the current page. Empty = none of these basics failed. */
export async function audit(page, { skipContrast = [] } = {}) {
	return page.evaluate(
		({ skipContrast }) => {
			const problems = [];
			const visible = (el) => {
				const s = getComputedStyle(el);
				const r = el.getBoundingClientRect();
				return s.visibility !== "hidden" && s.display !== "none" && r.width > 0 && r.height > 0;
			};
			const name = (el) =>
				(el.getAttribute("aria-label") || el.getAttribute("title") || el.textContent || "").trim() ||
				(el.id && document.querySelector(`label[for="${el.id}"]`)?.textContent.trim()) ||
				el.getAttribute("placeholder") ||
				"";

			if (!document.documentElement.lang) problems.push("html has no lang");
			if (!document.title.trim()) problems.push("page has no title");
			const h1 = [...document.querySelectorAll("h1")].filter(visible);
			if (h1.length !== 1) problems.push(`expected one visible h1, found ${h1.length}`);
			if (!document.querySelector("main, [role=main]")) problems.push("no main landmark");

			for (const img of document.querySelectorAll("img")) {
				if (visible(img) && !img.hasAttribute("alt")) problems.push(`image without alt: ${img.getAttribute("src")}`);
			}
			for (const el of document.querySelectorAll("input:not([type=hidden]), select, textarea")) {
				if (!visible(el)) continue;
				const labelled =
					el.getAttribute("aria-label") ||
					el.getAttribute("aria-labelledby") ||
					(el.id && document.querySelector(`label[for="${el.id}"]`)) ||
					el.closest("label");
				if (!labelled) problems.push(`form field without a label: ${el.id || el.name || el.type}`);
			}
			for (const el of document.querySelectorAll("a[href], button")) {
				if (visible(el) && !name(el) && !el.querySelector("img[alt]:not([alt=''])")) {
					problems.push(`control without an accessible name: ${el.outerHTML.slice(0, 80)}`);
				}
			}

			// horizontal scroll at this viewport
			if (document.documentElement.scrollWidth > window.innerWidth + 1) {
				problems.push(`horizontal scroll: ${document.documentElement.scrollWidth} > ${window.innerWidth}`);
			}

			// contrast of text against its effective background (skips text over images and gradients)
			const parse = (c) => {
				const m = c.match(/rgba?\(([^)]+)\)/);
				if (!m) return null;
				const [r, g, b, a = 1] = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
				return { r, g, b, a };
			};
			const lum = ({ r, g, b }) => {
				const f = (v) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
				return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
			};
			const backdrop = (el) => {
				for (let n = el; n; n = n.parentElement) {
					const s = getComputedStyle(n);
					if (s.backgroundImage !== "none") return null; // over an image: cannot be judged here
					const c = parse(s.backgroundColor);
					if (c && c.a > 0.95) return c;
				}
				return parse(getComputedStyle(document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
			};
			const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
			const seen = new Set();
			for (let node; (node = walker.nextNode()); ) {
				const el = node.parentElement;
				if (!el || seen.has(el) || !node.textContent.trim() || !visible(el)) continue;
				if (["SCRIPT", "STYLE", "NOSCRIPT"].includes(el.tagName)) continue;
				if (skipContrast.some((sel) => el.closest(sel))) continue;
				seen.add(el);
				const s = getComputedStyle(el);
				if (parseFloat(s.opacity) < 1) continue;
				const fg = parse(s.color);
				const bg = backdrop(el);
				if (!fg || !bg) continue;
				const [l1, l2] = [lum(fg), lum(bg)].sort((a, b) => b - a);
				const ratio = (l1 + 0.05) / (l2 + 0.05);
				const size = parseFloat(s.fontSize);
				const large = size >= 24 || (size >= 18.66 && parseInt(s.fontWeight, 10) >= 700);
				if (ratio < (large ? 3 : 4.5)) {
					problems.push(
						`low contrast ${ratio.toFixed(2)}:1 for "${node.textContent.trim().slice(0, 30)}" (${s.color} on rgb(${bg.r},${bg.g},${bg.b}))`,
					);
				}
			}
			return problems;
		},
		{ skipContrast },
	);
}

/** Tab through the page: returns the focus order and any focused control with no visible focus indicator. */
export async function keyboardWalk(page, maxStops = 40) {
	const order = [];
	const noIndicator = [];
	await page.evaluate(() => document.activeElement && document.activeElement.blur());
	for (let i = 0; i < maxStops; i++) {
		await page.keyboard.press("Tab");
		const info = await page.evaluate(() => {
			const el = document.activeElement;
			if (!el || el === document.body) return null;
			const s = getComputedStyle(el);
			const outlined = s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0;
			const shadow = s.boxShadow && s.boxShadow !== "none";
			return {
				label: (el.getAttribute("aria-label") || el.textContent || el.id || el.tagName).trim().slice(0, 40),
				tag: el.tagName,
				indicator: outlined || shadow,
			};
		});
		if (!info) break;
		if (order.length > 1 && order[0].label === info.label) break; // wrapped around
		order.push(info);
		if (!info.indicator) noIndicator.push(info.label);
	}
	return { order, noIndicator };
}
