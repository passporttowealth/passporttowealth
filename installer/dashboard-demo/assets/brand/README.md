# Brand assets

> **Copyright © 2026 Passport to Wealth. All rights reserved.** These files are the property of Passport to Wealth, mirrored from the live site (`passporttowealth.com`) for use in this product. They may not be redistributed, modified for derivative use, or used to brand other services. See `LICENSE` at the repo root.

Canonical brand files for the project.

**⚠ Three copies exist** — keep them in sync when you update any file here:

1. `assets/brand/` (this directory — canonical)
2. `installer/assets/brand/` (bundled into the landing-page publish)
3. `skill/templates/site/assets/brand/` (bundled into the user dashboard)

Why three copies and not one symlink? The here-now publish script walks files with `find -type f`, which silently skips symlinks. We previously used symlinks here, and the live landing-page logo 404'd because the symlinked PNGs never made it into the publish bundle. The `test_landing_page_assets_resolve_in_publish_bundle` test guards against this for the landing page — if you re-introduce a symlink under `installer/`, the test fails.

If you update any file here, run:

```bash
cp assets/brand/{favicon.png,logo-blue.png,logo-white.png,README.md} installer/assets/brand/
cp assets/brand/{favicon.png,logo-blue.png,logo-white.png,README.md} skill/templates/site/assets/brand/
```

## What's in here

| File | Source | Use |
|---|---|---|
| `logo-blue.png` | passporttowealth.com header (logo on light bg) | Primary wordmark — use on white / warm-off-white backgrounds. 235×220, transparent PNG. |
| `logo-white.png` | passporttowealth.com header (logo on dark bg) | Secondary wordmark — use on dark backgrounds (footers, dark-mode variants). 177×184, transparent PNG. |
| `favicon.png` | passporttowealth.com `<link rel="icon">` | Browser tab icon for the dashboard and the installer landing page. 135×110, transparent PNG. |

## Color extracted from `logo-blue.png`

Pixel sampling against the dominant non-transparent regions of the wordmark:

```
Top dominant colors (R,G,B → hex):
  rgb(14,26,48)  → #0E1A30   (29 px)
  rgb(17,28,50)  → #111C32   (24 px)
  rgb(18,29,51)  → #121D33   (22 px)
  rgb(13,25,47)  → #0D192F   (22 px)
  rgb(18,30,51)  → #121E33   (20 px)
```

→ **Brand accent: `#0F1E33`** (a deep navy, not a bright blue). `DESIGN_TOKENS.md` is set to this. Earlier inference of `#0066CC` was wrong.

## What's NOT in here (intentionally)

- **Hero stock photo** from the homepage (iStock-licensed) — out of scope for redistribution.
- **Headshots** — personal photo; only embed with her explicit permission and only where contextually appropriate (advisor bio sections, not the client dashboard).
- **Custom typography files** (woff2 etc.) — Inter (used as default in the dashboard) is bundled separately under `skill/templates/site/assets/fonts/` (not yet populated; placeholder).

## When Arielle delivers a real brand pack

Replace the files in this directory, then run the two `cp` commands at the top of this README to propagate the new files into the publish bundles. Both `installer/index.html` and `skill/templates/site/` reference them by stable path, so swapping the file is the only change needed beyond the copy. If the new pack adds icon SVGs or new logo variants, add them here, document above, and propagate them too.

If the wordmark changes shape or color, also re-derive the accent color and update `skill/references/DESIGN_TOKENS.md` accordingly.
