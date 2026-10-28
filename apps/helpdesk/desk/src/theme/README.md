# Theme

One palette, defined as data, generated into every surface. Anchors come from
octet.design `course-landing-color-palette-1732775208`: paper, sand, taupe, amber, umber, charcoal.

## Change a color

1. Edit `tokens/palette.json` (anchors, ramp rules) or `tokens/semantic.json` (accent shades, focus, chart, email).
2. `yarn theme:build` regenerates `generated/` and syncs the NXERP copies.
3. `yarn theme:check` must pass: generated files fresh, every frappe-ui token covered, contrast above the minimums in `tokens/contrast.json`.
4. `yarn theme:audit` must pass: no hex, `rgb()` or raw Tailwind palette class in `desk/src`.

Never edit `generated/`. Frappe-ui `rc.1` is the version the tokens are locked to (`tokens/frappe-ui.lock.json`).
A new frappe-ui release fails `theme:check` until the diff is reviewed and the lock updated.

## How it fits together

| Tier | What | Where |
| --- | --- | --- |
| Primitives | `gray` (warm neutral) and `accent` (amber) ramps replace frappe-ui's gray. Other families (red, green, blue, ...) are inherited. | `tokens/palette.json` |
| Semantic | frappe-ui's own `surface-*`, `ink-*`, `outline-*` mapping is inherited, so every existing class recolors. `accent-*` mirrors the blue structure. | `tokens/semantic.json` |
| Roles | Chart series and UI colors, email colors, focus ring. | `tokens/semantic.json` |

`tailwind.config.js` applies `generated/tailwind-theme.mjs` as `theme.extend` plus a top-level plugin, listed first among
the user plugins. Tailwind emits user plugins after preset plugins, so our variables follow frappe-ui's and the same
selectors resolve in our favor. Do not turn it into a second preset: any preset listed after frappe-ui's breaks
frappe-ui's own `@apply` rules (`rounded-4` stops resolving).

## Using colors

- Neutral UI: `bg-surface-gray-*`, `text-ink-gray-*`, `border-outline-gray-*`.
- Brand emphasis: `bg-surface-accent-6 text-ink-accent-on` for a fill, `text-ink-accent-link` or `text-ink-accent-5` for text.
  Amber is never text on a light surface and never carries white text (2.0:1). `ink-accent-on` is charcoal in both modes.
- Fixed colors that must not flip, such as text on a photo scrim: `text-paper`, `bg-charcoal`.
- Blue stays a category color (tags, statuses). Do not use it for "primary".
- Charts: `useChartTheme()`. ECharts cannot read CSS variables, so it hands back resolved values and redraws on a mode change.
- Content saved into stored or sent HTML cannot use CSS variables. Use `tokens.email` from `generated/tokens.ts`.

## Modes

`useAppTheme()` wraps frappe-ui's `useColorScheme()`. It keeps light, dark and system, and also saves the choice on the user
(`helpdesk.api.theme.set_desk_theme`) so Frappe Desk and other devices agree. `desk/index.html` sets `data-theme`
before first paint; the server value wins when logged in.

## Other surfaces

- Frappe Desk (ERPNext, Framework): `generated/frappe-desk.css`, synced to the platform app (`nxerp-platform/nxerp/public/css/nxerp-desk-theme.css`) and loaded by its `app_include_css` hook, so the palette follows the platform, not one app.
- Login: owned by the NXERP platform app (`nxerp/www/login.*`), which loads `nxerp-theme.css` (synced into its `public/css`) then its own `nxerp-login.css`.
- `yarn theme:build` also copies the generated CSS into `../../nxerp-platform/nxerp/public/css` (`src/theme/build/sync.mjs`). Set `NXERP_PUBLIC` to change the target.

## Known gaps

- The NXERP logo files are blue and navy. They are brand assets and were not recolored.
- `assets/custom_icons`, `assets/icons` and `components/desk/global/CustomIcons.vue` are unreferenced and allowlisted in `tokens/audit-allow.json`. The audit fails if anything starts importing them.
- frappe-ui's `Tree` uses blue for drop targets. Helpdesk does not render it.
