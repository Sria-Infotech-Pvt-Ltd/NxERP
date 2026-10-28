// Fails when frappe-ui drifts from what the theme was built against.
import path from "node:path";
import { pathToFileURL } from "node:url";
import { buildModel, resolveRef, frappeUiDir } from "./lib/model.mjs";

const model = await buildModel();
const { lock } = model.src;
const base = model.fui.colors;
const errors = [];

if (model.fui.version !== lock.version) {
  errors.push(
    `frappe-ui is ${model.fui.version} but the theme is locked to ${lock.version} (tokens/frappe-ui.lock.json). Rebuild and review the diff, then update the lock.`
  );
}

const known = new Set([...lock.ownedFamilies, ...lock.inheritedFamilies]);
for (const mode of ["lightMode", "darkMode"]) {
  for (const family of Object.keys(base[mode])) {
    if (!known.has(family))
      errors.push(
        `new frappe-ui color family "${family}" in ${mode}: classify it in tokens/frappe-ui.lock.json`
      );
  }
}

for (const mode of ["light", "dark"]) {
  for (const [category, entries] of Object.entries(
    base.themedVariables[mode]
  )) {
    if (!lock.semanticCategories.includes(category))
      errors.push(`new semantic category "${category}" (${mode})`);
    for (const [name, ref] of Object.entries(entries)) {
      const family = ref.split("/")[1];
      if (
        !known.has(family) &&
        !ref.startsWith("neutral/") &&
        !ref.startsWith("overlay/")
      )
        errors.push(
          `${category}-${name} (${mode}) points at unclassified family "${family}"`
        );
      if (model.semantic[mode][category][name] == null)
        errors.push(`${category}-${name} (${mode}) does not resolve`);
    }
  }
  for (const category of ["surface", "ink", "outline"]) {
    const names = Object.keys(model.semantic[mode][category]).filter((n) =>
      n.startsWith("accent-")
    );
    for (const n of [
      ...Array.from({ length: 10 }, (_, i) => `accent-${i + 1}`),
      ...(category === "ink" ? ["accent-link", "accent-on"] : []),
    ]) {
      if (!names.includes(n))
        errors.push(
          `${category}-${n} missing from the accent family (${mode})`
        );
    }
  }
}

// A variable set in light but not in dark leaks into dark, because our :root block follows frappe-ui's dark block.
for (const k of Object.keys(model.delta.light)) {
  if (k in model.full.dark && !(k in model.delta.dark))
    errors.push(
      `${k} is set for light but missing from dark: it would leak into dark mode`
    );
}

// Our resolver must reproduce frappe-ui's own output when nothing is overridden.
const tokensFile = path.join(frappeUiDir(), "tailwind/tokens.js");
try {
  const { cssVariables } = await import(pathToFileURL(tokensFile).href);
  if (cssVariables) {
    for (const mode of ["light", "dark"]) {
      let drift = 0;
      for (const [cat, entries] of Object.entries(base.themedVariables[mode])) {
        for (const [name, ref] of Object.entries(entries)) {
          if (cssVariables[mode][`--${cat}-${name}`] !== resolveRef(ref, base))
            drift++;
        }
      }
      if (drift)
        errors.push(
          `resolver drift: ${drift} ${mode} tokens differ from frappe-ui cssVariables`
        );
    }
  }
} catch {
  console.warn(
    "coverage: frappe-ui tokens.js not importable here, skipped the resolver cross-check."
  );
}

if (errors.length) {
  console.error(errors.map((e) => `- ${e}`).join("\n"));
  process.exit(1);
}
const count = Object.values(base.themedVariables.light).reduce(
  (n, e) => n + Object.keys(e).length,
  0
);
console.log(
  `coverage: ${count} frappe-ui tokens per mode resolved, accent family complete, frappe-ui ${model.fui.version}.`
);
