// Fails when any part of the palette is not under version control or is matched by an ignore rule.
// A blanket `build/` or `lib/` rule once kept the whole generator out of git; this makes that
// impossible to repeat unnoticed. Run by `yarn theme:check`, CI and pre-commit.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { THEME_DIR } from "./lib/model.mjs";

const REPO = path.resolve(THEME_DIR, "../../..");
const git = (...args) => {
  try {
    return execFileSync("git", ["-C", REPO, ...args], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  } catch (e) {
    return e.stdout || "";
  }
};

// Everything the palette needs: the whole theme folder (including build/ and lib/), the login
// theme assets, the Tailwind wiring and the backend persistence of the theme choice.
const ROOTS = [
  "hd-frontend/src/theme",
  "hd-frontend/tailwind.config.js",
  "hd-frontend/src/index.css",
  "helpdesk/api/theme.py",
  "helpdesk/theme_tokens.py",
];
// Required even if the folder listing above somehow missed them.
const REQUIRED = [
  "hd-frontend/src/theme/build/generate.mjs",
  "hd-frontend/src/theme/build/sync.mjs",
  "hd-frontend/src/theme/build/lib/model.mjs",
  "hd-frontend/src/theme/tokens/palette.json",
  "hd-frontend/src/theme/tokens/semantic.json",
  "hd-frontend/src/theme/generated/tailwind-theme.mjs",
  "hd-frontend/src/theme/generated/nxerp-theme.css",
  "hd-frontend/src/theme/generated/frappe-desk.css",
  "helpdesk/theme_tokens.py",
];

if (!fs.existsSync(path.join(REPO, ".git"))) {
  console.log("tracked: not a git checkout, skipped.");
  process.exit(0);
}

const onDisk = [];
const walk = (rel) => {
  const abs = path.join(REPO, rel);
  if (!fs.existsSync(abs)) return;
  if (fs.statSync(abs).isDirectory()) {
    for (const name of fs.readdirSync(abs)) walk(path.posix.join(rel, name));
  } else {
    onDisk.push(rel);
  }
};
ROOTS.forEach(walk);

const tracked = new Set(git("ls-files", "-z", "--", ...ROOTS).split("\0").filter(Boolean));
const problems = [];

for (const file of REQUIRED) {
  if (!fs.existsSync(path.join(REPO, file))) problems.push(`missing: ${file}`);
}
for (const file of onDisk) {
  const ignored = git("check-ignore", "-v", "--no-index", file).trim();
  if (ignored) problems.push(`ignored by git: ${file}  (${ignored.split("\t")[0]})`);
  else if (!tracked.has(file)) problems.push(`untracked: ${file}  (git add it)`);
}

if (problems.length) {
  console.error(problems.map((p) => `tracked: ${p}`).join("\n"));
  console.error(
    "\nThe palette must be fully committed and never ignored. Fix the .gitignore (exceptions go last) and `git add` the files.",
  );
  process.exit(1);
}
console.log(`tracked: all ${onDisk.length} palette files are tracked and none is ignored.`);
