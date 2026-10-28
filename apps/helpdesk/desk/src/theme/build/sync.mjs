// Copies the standalone CSS outputs into the apps that serve Frappe Desk and the login pages.
// Usage: node sync.mjs [--check]. NXERP_PUBLIC overrides the platform app target folder
// (default: the sibling nxerp-platform checkout, nxerp/public/css).
import fs from "node:fs";
import path from "node:path";
import { THEME_DIR } from "./lib/model.mjs";

const GENERATED = path.join(THEME_DIR, "generated");
const REPO = path.resolve(THEME_DIR, "../../..");
const TARGETS = [
  {
    dir:
      process.env.NXERP_PUBLIC ||
      path.resolve(REPO, "../nxerp-platform/nxerp/public/css"),
    files: {
      "nxerp-theme.css": "nxerp-theme.css",
      "frappe-desk.css": "nxerp-desk-theme.css",
    },
  },
  {
    dir: path.resolve(REPO, "helpdesk"),
    files: { "theme_tokens.py": "theme_tokens.py" },
  },
];
const check = process.argv.includes("--check");
let stale = 0;

for (const { dir, files } of TARGETS) {
  if (!fs.existsSync(dir)) {
    console.log(`sync: ${dir} not found, skipped.`);
    continue;
  }
  for (const [from, to] of Object.entries(files)) {
    const content = fs.readFileSync(path.join(GENERATED, from), "utf8");
    const file = path.join(dir, to);
    const current = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
    if (current === content) continue;
    if (check) {
      stale++;
      console.error(`stale: ${file}`);
    } else {
      fs.writeFileSync(file, content);
      console.log(`synced ${file}`);
    }
  }
}
if (check && stale) process.exit(1);
console.log(check ? "synced copies are up to date" : "sync done");
