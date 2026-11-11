# UI contract for NXDESK screens

Status: written in Phase 1 (2026-11-11). **Read this before building any screen in Phase 2 or 3.** It is the design contract of the
NXDESK plan, adapted to the class names, tokens and screens that exist. Where this file and a screenshot disagree, the running
launcher, no-access page and login are the source of truth: open them in light and dark first.

Goal: every new screen looks as if it was always part of the product: modern, professional, sleek, and consistent with the
screens that exist. Nothing may look odd, unstyled, off-palette or off-scale.

## Sources of truth

| What | File |
| --- | --- |
| Platform pages (launcher, no-access, public site) | `apps/nxerp_platform/nxerp/public/css/nxerp-platform.css` (do not change), plus `nxerp-site.css` (Phase 1 additions) |
| Their markup and the pre-paint theme script | `www/nxerp/apps.html`, `www/nxerp/no-access.html`, `templates/includes/nxdesk/head.html` |
| The split-shell login | `public/nxerp_login/css/nxerp-login.css`, `www/login.html` |
| Tokens | `public/css/nxerp-theme.css`: **generated, never edited by hand** (`yarn theme:build` in `apps/helpdesk/hd-frontend`) |
| How the palette is defined | `apps/helpdesk/hd-frontend/src/theme/README.md` (anchors: paper, sand, taupe, amber, umber, charcoal) |

Baseline screenshots (before Phase 1, 1440x900, light and dark): `docs/evidence/ui/phase1/baseline/`.

## 1. Two page families. Reuse them. Do not invent a third look.

**A. Platform pages** (the launcher, no-access, and the public site: `/`, `/products`, `/products/<key>`, `/get-started`, request-access).
Body `nxp-body`; floating glass header `nxp-header`; content `nxp-main` (max 68rem); intro `nxp-intro` with `nxp-eyebrow`, `nxp-title`,
`nxp-sub`; tile grid `nxp-grid` of `nxp-tile` (with `nxp-mark`, `nxp-tile-body`, `nxp-tile-title`, `nxp-tile-cta`, `nxp-arrow`); `nxp-button`;
`nxp-link`; `nxp-footer`. Warm mesh background with a slow aurora, a hairline grid and film grain come from `.nxp-body` itself: a page gets
them by using the class. A pointer spotlight on tiles comes from the small script in `templates/includes/nxdesk/scripts.html`.

Phase 1 additions (`nxerp-site.css`, additive only; a test proves it never redefines a platform selector):

| Class | Use |
| --- | --- |
| `nxp-wordmark`, `nxp-wordmark-mark` | typographic platform wordmark: NX Inter 700, tracking -.03em, an amber square |
| `nxp-nav`, `nxp-navlink` | header navigation (44px targets); `aria-current="page"` gets an amber underline |
| `nxp-toggle` (+ `nxp-moon`, `nxp-sun`) | the theme toggle, 2.75rem circle, same look as the login's `nx-theme-toggle` |
| `nxp-cta` + `nxp-cta--primary` / `nxp-button` / `nxp-cta--ghost`, `nxp-cta--sm` | the three buttons (see 4) |
| `nxp-hero`, `nxp-site`, `nxp-section-head`, `nxp-h2` | hero (title up to 3.8rem), vertical rhythm, section headings |
| `nxp-card`, `nxp-icon`, `nxp-steps`, `nxp-step-no` | small glass cards and the three-step row |
| `nxp-split`, `nxp-split-copy`, `nxp-lead`, `nxp-panel`, `nxp-checks`, `nxp-check` | the two-column product page and its "At a glance" panel |
| `nxp-category`, `nxp-tile-tagline`, `nxp-foot-nav`, `nxp-foot-link`, `nxp-sr-only` | category sections, tile tagline, footer links, visually hidden text |

**B. Split shell** (`/signup`, `/welcome/<key>`, the app-branded `/login`): `nx-shell`, `nx-hero` (charcoal, hairline grid, orbit art), `nx-panel`,
`nx-card`, `nx-top` with the theme toggle and `nx-lang`. Everything in `nxerp-login.css` is scoped under `.nx-shell`. Phase 2 and 3 reuse it as is.

## 2. Colour

Only tokens from `nxerp-theme.css`: `--brand-paper`, `--brand-sand`, `--brand-taupe`, `--brand-amber`, `--brand-umber`, `--brand-charcoal`;
`--surface-*`, `--ink-*`, `--outline-*`, `--accent-*`, `--surface-accent-*`, `--ink-accent-*`; `--red-*` for errors only. **Never write a hex,
`rgb()`, `hsl()` or a colour name.** (The only literals in the platform are icon and grain data-URIs, which cannot read variables; each carries a
comment.) `test_site_assets.py` fails the build on a literal in the public site's CSS or templates.

Amber is the single accent. A fill is `--surface-accent-6` or `--brand-amber` with text in `--ink-accent-on` (charcoal). Amber is never text on a light
surface and never carries white text (contrast 2.0:1). Coloured text and links use `--ink-accent-link`. **No product gets its own colour**
(the registry has no colour field, and a test keeps it that way). Blue is not "primary".

## 3. Type

"NX Inter" only (self-hosted variable font, `public/nxerp_login/fonts/inter-latin.woff2`). No new font, font host or Google Fonts. Titles weight 650,
tracking -.02em; eyebrows .72rem, weight 800, uppercase, tracking .12em; body about 1.05rem/1.55, weight 450; small text gets a little extra tracking.
Yellowtail stays the login tagline only. Sentence case everywhere. Fluid sizes with `clamp()`.

## 4. Shape and depth (copy these values)

- Header: radius 1rem, glass blur, hairline border, amber underline glow (`.nxp-header`).
- Tiles, cards, panels: radius 1.25rem, 1px `--outline-gray-2` border, two-layer soft shadow; only tiles lift 4px on hover with an amber border.
- Primary button `nxp-cta nxp-cta--primary`: amber fill, charcoal text, weight 700, inset highlight and amber glow, hover `brightness(1.04)` and a 1px lift, active press,
  3px focus ring with 3px offset in `--surface-accent-6` (the platform pages' existing outline). Copied from `.btn-primary` in `nxerp-login.css`.
- Secondary `nxp-button nxp-cta` (`--surface-gray-9` fill). Ghost `nxp-cta nxp-cta--ghost`: text, outline on hover. Minimum height 2.75rem (44px).
- Status pill: 999px radius, tinted from tokens. Inputs: the login form's field look.

## 5. Motion

Only `nxp-rise` (0.5s, staggered 70ms through `--i`), tile hover and the aurora. Honour `prefers-reduced-motion` exactly as `nxerp-platform.css` does
(`nxerp-site.css` repeats the pattern for its additions). No animation library, no scroll-jacking, nothing that shifts layout after load.

## 6. Light and dark

Both, on every screen. Use the pre-paint script in `templates/includes/nxdesk/head.html` (localStorage key `theme`: `light`, `dark`, `system`) so `data-theme` is set
before the first paint, and carry the theme toggle on every public page. Logos swap by theme through `branding.py` (typographic wordmark until the owner supplies files).

## 7. Icons

Inline SVG, 24px viewBox, stroke 1.8 (2 for arrows, 2.4 for check marks), round caps and joins, `currentColor`. No emoji, no icon font, no external set.

## 8. Layout

Mobile first, fluid, content width `.nxp-main` (68rem). The header's 520px behaviour is the model for small screens; Phase 1 also hides "Get started" below 420px (the hero and product pages carry it).
No horizontal scroll at 320px. Touch targets at least 44px. Use the spacing already in the CSS.

## 9. Copy

Short, calm, sentence case. No exclamation marks, no emoji, no superlatives, no claim we cannot prove (no customer counts, awards, certifications, uptime figures).
Follow the existing microcopy ("Choose an application", "Open application"). Registry copy limits so cards never overflow: **tagline at most 60 characters, summary at most 180,
at most 4 features of at most 6 words** (enforced by `tests/test_registry.py`).

## 10. Accessibility

Skip link; one `h1` per page; landmark regions; visible focus (the existing 3px outline); a label on every control; errors announced with `aria-live`; colour never the only signal;
text contrast at least WCAG AA using only pairings the existing screens already use; every flow completable with the keyboard alone. `browser-tests/site.test.mjs` checks the
skip link, Tab reachability, focus indicators, 44px targets, 320px overflow and measured contrast.

## 11. Assets and names

There is no NXDESK logo file. **Do not draw, trace or imitate a logo.** `nxerp/branding.py` is the one place for the platform name, tagline, light and dark logo paths and the support link;
while the logo paths are empty the pages render the typographic wordmark. Product logos come from the registry. Display names (ADR-008): NXDESK (platform), NXERP (ERP product),
Sria Helpdesk (support product); Royal HRMS is not installed and is never shown.

## 12. Leave alone

Generated files (`nxerp-theme.css`, `nxerp-desk-theme.css`), and the look of the launcher, no-access page and login except where a brief says to change it. Prove "unchanged"
with before and after screenshots (`docs/evidence/ui/<phase>/`).

## Visual QA loop

Playwright screenshots of every new or changed screen at 360x800, 768x1024, 1280x800 and 1920x1080 in light and dark under `docs/evidence/ui/<phase>/`; compare each with the baseline launcher
and login; fix drift in radius, spacing, type scale, shadow, border colour and icon style; at most three rounds per screen, then list what still looks off.
`apps/nxerp_platform/browser-tests/site.test.mjs` is the template for a new screen's browser test.
