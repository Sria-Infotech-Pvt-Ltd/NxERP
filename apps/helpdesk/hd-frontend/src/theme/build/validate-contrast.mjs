// Fails when a declared text/surface pair drops under its minimum contrast in either mode.
import { buildModel, flatSemantic, toHex } from "./lib/model.mjs";
import { contrast } from "./lib/color.mjs";

const model = await buildModel();
const { pairs } = model.src.contrast;
let failures = 0;
let checked = 0;

for (const mode of ["light", "dark"]) {
  const tokens = flatSemantic(model.semantic, mode);
  const colorOf = (name) => {
    if (name === "focus-ring")
      return model.full[mode]["--focus-outline-default"]
        ?.match(/#[0-9a-f]{6,8}/i)?.[0]
        .slice(0, 7);
    return toHex(tokens[name]);
  };
  for (const { fg, on, min, modes } of pairs) {
    if (modes && !modes.includes(mode)) continue;
    const fgHex = colorOf(fg);
    for (const bg of on) {
      const bgHex = colorOf(bg);
      checked++;
      if (!fgHex || !bgHex) {
        failures++;
        console.error(`[${mode}] cannot resolve ${fg} or ${bg}`);
        continue;
      }
      const ratio = contrast(fgHex, bgHex);
      if (ratio < min) {
        failures++;
        console.error(
          `[${mode}] ${fg} ${fgHex} on ${bg} ${bgHex}: ${ratio.toFixed(
            2
          )} < ${min}`
        );
      }
    }
  }
}

if (failures) {
  console.error(`\n${failures} of ${checked} contrast checks failed.`);
  process.exit(1);
}
console.log(`contrast: ${checked} checks passed in light and dark.`);
