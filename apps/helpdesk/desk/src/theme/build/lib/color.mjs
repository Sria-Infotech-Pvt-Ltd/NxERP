// OKLCH <-> sRGB helpers. Plain Node, no dependencies.

const toLinear = (c) =>
  c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
const fromLinear = (c) =>
  c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

export function hexToRgb(hex) {
  let h = hex.replace("#", "");
  if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join("");
  const n = (i) => parseInt(h.slice(i, i + 2), 16) / 255;
  return { r: n(0), g: n(2), b: n(4), a: h.length === 8 ? n(6) : 1 };
}

export function rgbToHex({ r, g, b }) {
  const byte = (c) =>
    Math.round(clamp(c, 0, 1) * 255)
      .toString(16)
      .padStart(2, "0");
  return `#${byte(r)}${byte(g)}${byte(b)}`;
}

export function rgbToOklab({ r, g, b }) {
  const [lr, lg, lb] = [r, g, b].map(toLinear);
  const l = Math.cbrt(
    0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
  );
  const m = Math.cbrt(
    0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
  );
  const s = Math.cbrt(
    0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb
  );
  return {
    L: 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    a: 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    b: 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  };
}

function oklabToLinear({ L, a, b }) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return {
    r: 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    g: -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    b: -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  };
}

const inGamut = ({ r, g, b }) =>
  [r, g, b].every((c) => c >= -0.0005 && c <= 1.0005);

export function oklabToHex(lab) {
  const lin = oklabToLinear(lab);
  return rgbToHex({
    r: fromLinear(clamp(lin.r, 0, 1)),
    g: fromLinear(clamp(lin.g, 0, 1)),
    b: fromLinear(clamp(lin.b, 0, 1)),
  });
}

export const oklchToOklab = ({ L, C, h }) => ({
  L,
  a: C * Math.cos((h * Math.PI) / 180),
  b: C * Math.sin((h * Math.PI) / 180),
});

export function oklabToOklch({ L, a, b }) {
  const C = Math.hypot(a, b);
  const h = C < 1e-6 ? 0 : ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360;
  return { L, C, h };
}

// Lowers chroma until the color fits sRGB, so a derived ramp never clips hue.
export function oklchToHex({ L, C, h }) {
  let lo = 0;
  let hi = C;
  if (inGamut(oklabToLinear(oklchToOklab({ L, C, h }))))
    return oklabToHex(oklchToOklab({ L, C, h }));
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2;
    if (inGamut(oklabToLinear(oklchToOklab({ L, C: mid, h })))) lo = mid;
    else hi = mid;
  }
  return oklabToHex(oklchToOklab({ L, C: lo, h }));
}

// Accepts #rgb/#rrggbb/#rrggbbaa and oklch(L C H [/ alpha]). Returns null for anything else.
export function parseColor(value) {
  if (typeof value !== "string") return null;
  const v = value.trim();
  if (v.startsWith("#"))
    return { ...hexToRgb(v), hex: v.length === 9 ? v.slice(0, 7) : v };
  const m = v.match(
    /^oklch\(\s*([\d.]+)%?\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+%?))?\s*\)$/
  );
  if (!m) return null;
  const hex = oklchToHex({
    L: parseFloat(m[1]),
    C: parseFloat(m[2]),
    h: parseFloat(m[3]),
  });
  return {
    ...hexToRgb(hex),
    hex,
    alpha: m[4] ? parseFloat(m[4]) / (m[4].endsWith("%") ? 100 : 1) : 1,
  };
}

export function mix(hexA, hexB, t) {
  const a = rgbToOklab(hexToRgb(hexA));
  const b = rgbToOklab(hexToRgb(hexB));
  return oklabToHex({
    L: a.L + (b.L - a.L) * t,
    a: a.a + (b.a - a.a) * t,
    b: a.b + (b.b - a.b) * t,
  });
}

export function shiftLightness(hex, dL) {
  const c = oklabToOklch(rgbToOklab(hexToRgb(hex)));
  return oklchToHex({ ...c, L: clamp(c.L + dL, 0, 1) });
}

export const toOklch = (hex) => oklabToOklch(rgbToOklab(hexToRgb(hex)));

export function luminance(hex) {
  const { r, g, b } = hexToRgb(hex);
  const [lr, lg, lb] = [r, g, b].map(toLinear);
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

export function contrast(hexA, hexB) {
  const [hi, lo] = [luminance(hexA), luminance(hexB)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
