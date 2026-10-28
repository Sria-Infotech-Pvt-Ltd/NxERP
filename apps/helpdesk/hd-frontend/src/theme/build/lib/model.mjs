import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { buildRamps } from "./ramps.mjs";
import { parseColor } from "./color.mjs";

export const THEME_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../.."
);
const readJSON = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const clone = (o) => JSON.parse(JSON.stringify(o));

export function frappeUiDir() {
  return (
    process.env.FRAPPE_UI_DIR ||
    path.resolve(THEME_DIR, "../../node_modules/frappe-ui")
  );
}

// rc.1 ships tokens as ES modules; older builds ship generated JSON.
export async function loadFrappeUi() {
  const dir = frappeUiDir();
  if (!fs.existsSync(path.join(dir, "package.json"))) {
    throw new Error(
      `frappe-ui not found at ${dir}. Run "yarn install" or set FRAPPE_UI_DIR.`
    );
  }
  const version = readJSON(path.join(dir, "package.json")).version;
  const esm = path.join(dir, "tailwind/tokens/colors.js");
  const json = path.join(dir, "tailwind/generated/colors.json");
  const effectsEsm = path.join(dir, "tailwind/tokens/effects.js");
  const colors = fs.existsSync(esm)
    ? (await import(pathToFileURL(esm).href)).default
    : readJSON(json);
  const effects = fs.existsSync(effectsEsm)
    ? (await import(pathToFileURL(effectsEsm).href)).default
    : readJSON(path.join(dir, "tailwind/generated/effects.json"));
  return { dir, version, colors, effects };
}

export function loadSources() {
  const t = path.join(THEME_DIR, "tokens");
  return {
    palette: readJSON(path.join(t, "palette.json")),
    semantic: readJSON(path.join(t, "semantic.json")),
    contrast: readJSON(path.join(t, "contrast.json")),
    lock: readJSON(path.join(t, "frappe-ui.lock.json")),
  };
}

export function resolveRef(ref, data) {
  const [mode, a, b] = ref.split("/");
  if (mode === "lightMode" || mode === "darkMode" || mode === "overlay")
    return data[mode][a]?.[b] ?? null;
  if (mode === "neutral") return data.neutral[a] ?? null;
  return null;
}

function resolveThemed(data, themed) {
  const out = {};
  for (const [category, entries] of Object.entries(themed)) {
    out[category] = {};
    for (const [name, ref] of Object.entries(entries))
      out[category][name] = resolveRef(ref, data);
  }
  return out;
}

const toVars = (semantic) =>
  Object.fromEntries(
    Object.entries(semantic).flatMap(([cat, entries]) =>
      Object.entries(entries).map(([n, v]) => [`--${cat}-${n}`, v])
    )
  );

function primitiveVars(data) {
  const light = {};
  const dark = {};
  for (const [fam, shades] of Object.entries(data.lightMode))
    for (const [s, v] of Object.entries(shades)) light[`--${fam}-${s}`] = v;
  for (const [fam, shades] of Object.entries(data.darkMode))
    for (const [s, v] of Object.entries(shades)) dark[`--dark-${fam}-${s}`] = v;
  return { light, dark };
}

// "white" is the page white; "ink" is charcoal in both modes, for text sitting on an accent fill.
const ACCENT_REFS = { white: "neutral/white", ink: "lightMode/gray/950" };

function accentTokens(semantic, mode) {
  const ramp = mode === "light" ? "lightMode" : "darkMode";
  const out = {};
  for (const [category, byMode] of Object.entries(semantic.accent)) {
    out[category] = {};
    for (const [name, shade] of Object.entries(byMode[mode])) {
      out[category][`accent-${name}`] =
        ACCENT_REFS[shade] ?? `${ramp}/accent/${shade}`;
    }
  }
  return out;
}

// The blue family is the app's primary accent, so it follows the accent family. Light solid fills
// (surface-blue-6..8) carry the light ink-base, so they sit on darker bronze steps.
function blueAliasTokens(semantic, mode) {
  const ramp = mode === "light" ? "lightMode" : "darkMode";
  const solid = mode === "light" ? semantic.blueAlias.solidLight : {};
  const out = {};
  for (const [category, entries] of Object.entries(accentTokens(semantic, mode))) {
    out[category] = {};
    for (const [token, ref] of Object.entries(entries)) {
      const name = token.replace("accent-", "");
      if (name === "on") continue;
      const bronze = category === "surface" && solid[name];
      out[category][`blue-${name}`] = bronze ? `${ramp}/accent/${bronze}` : ref;
    }
  }
  return out;
}

function extend(base, ramps, semantic) {
  const data = clone(base);
  data.lightMode.gray = ramps.gray.light;
  data.darkMode.gray = ramps.gray.dark;
  data.lightMode.accent = ramps.accent.light;
  data.darkMode.accent = ramps.accent.dark;
  Object.assign(data.neutral, ramps.neutral);
  for (const mode of ["light", "dark"]) {
    for (const layer of [
      accentTokens(semantic, mode),
      blueAliasTokens(semantic, mode),
    ]) {
      for (const [category, entries] of Object.entries(layer))
        Object.assign(data.themedVariables[mode][category], entries);
    }
  }
  const raised = data.themedVariables.light.surface;
  for (const name of ["elevation-1", "elevation-2", "elevation-3"])
    raised[name] = `neutral/${semantic.elevation.light}`;
  return data;
}

function focusVars(ramps, semantic, mode) {
  const f = semantic.focus[mode];
  return {
    [`--focus-outline-${f.name}`]: `${f.width} solid ${
      ramps.accent[mode][f.shade]
    }`,
  };
}

export async function buildModel() {
  const fui = await loadFrappeUi();
  const src = loadSources();
  const ramps = buildRamps(src.palette);
  const base = fui.colors;
  const data = extend(base, ramps, src.semantic);

  const semantic = {
    light: resolveThemed(data, data.themedVariables.light),
    dark: resolveThemed(data, data.themedVariables.dark),
  };
  const baseSemantic = {
    light: resolveThemed(base, base.themedVariables.light),
    dark: resolveThemed(base, base.themedVariables.dark),
  };
  const prim = primitiveVars(data);
  const basePrim = primitiveVars(base);

  const full = {};
  const baseline = {};
  for (const mode of ["light", "dark"]) {
    const focus = focusVars(ramps, src.semantic, mode);
    full[mode] = { ...toVars(semantic[mode]), ...prim[mode], ...focus };
    baseline[mode] = { ...toVars(baseSemantic[mode]), ...basePrim[mode] };
  }

  // Only variables our palette changes or adds, so the Tailwind layer stays small and reviewable.
  const delta = { light: {}, dark: {} };
  for (const mode of ["light", "dark"]) {
    for (const [k, v] of Object.entries(full[mode]).sort(([a], [b]) =>
      a.localeCompare(b)
    )) {
      if (baseline[mode][k] !== v) delta[mode][k] = v;
    }
  }
  // Our :root block follows frappe-ui's dark block, so a variable we set in light would leak into dark
  // unless dark sets it too, even when dark's value is stock (e.g. a transparent sidebar).
  for (const k of Object.keys(delta.light)) {
    if (k in full.dark && !(k in delta.dark)) delta.dark[k] = full.dark[k];
  }
  delta.dark = Object.fromEntries(
    Object.entries(delta.dark).sort(([a], [b]) => a.localeCompare(b))
  );

  return {
    fui,
    src,
    ramps,
    data,
    semantic,
    baseSemantic,
    full,
    baseline,
    delta,
  };
}

export const toHex = (value) => {
  const c = parseColor(value);
  return c && (c.alpha === undefined || c.alpha === 1) ? c.hex : null;
};

export const flatSemantic = (semantic, mode) => {
  const out = {};
  for (const [cat, entries] of Object.entries(semantic[mode]))
    for (const [n, v] of Object.entries(entries)) out[`${cat}-${n}`] = v;
  return out;
};
