import { mix, shiftLightness, toOklch, oklchToHex } from "./color.mjs";

const anchorHex = (anchors, name) => {
  if (!anchors[name]) throw new Error(`palette: unknown anchor "${name}"`);
  return anchors[name];
};

function buildGrayRamp(spec, anchors) {
  const out = {};
  for (const [shade, rule] of Object.entries(spec)) {
    if (rule.anchor) out[shade] = anchorHex(anchors, rule.anchor);
    else if (rule.mix)
      out[shade] = mix(
        anchorHex(anchors, rule.mix[0]),
        anchorHex(anchors, rule.mix[1]),
        rule.mix[2]
      );
    else if (rule.shift)
      out[shade] = shiftLightness(
        anchorHex(anchors, rule.shift[0]),
        rule.shift[1]
      );
    else throw new Error(`palette: bad rule for shade ${shade}`);
  }
  return out;
}

// Same hue as the anchor, lightness per stop, chroma scaled and gamut-clipped.
function buildAccentRamp(spec, anchors) {
  const base = anchorHex(anchors, spec.from);
  const { L, C, h } = toOklch(base);
  const out = { [spec.anchorShade]: base };
  for (const [shade, stop] of Object.entries(spec.stops)) {
    out[shade] = oklchToHex({ L: stop.L, C: C * stop.chroma, h });
  }
  return Object.fromEntries(
    Object.entries(out).sort((a, b) => Number(a[0]) - Number(b[0]))
  );
}

export function buildRamps(palette) {
  const { anchors, ramps, neutral } = palette;
  const accent = buildAccentRamp(ramps.accent, anchors);
  return {
    gray: {
      light: buildGrayRamp(ramps.gray.light, anchors),
      dark: buildGrayRamp(ramps.gray.dark, anchors),
    },
    accent: { light: accent, dark: accent },
    neutral: buildGrayRamp(neutral, anchors),
  };
}
