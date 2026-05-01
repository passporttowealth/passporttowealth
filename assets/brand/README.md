# Brand assets

> **Copyright © 2026 Passport to Wealth. All rights reserved.** These files are the property of Passport to Wealth, mirrored from the live site (`passporttowealth.com`) for use in this product. They may not be redistributed, modified for derivative use, or used to brand other services. See `LICENSE` at the repo root.

Canonical brand files. Both the installer landing page (`installer/`) and the dashboard template (`skill/templates/site/`) reference these — single source of truth, no copies that can drift.

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

Replace these files in place. Both `installer/index.html` and `skill/templates/site/` reference them by stable path, so swapping the file is the only change needed. If the new pack adds icon SVGs or new logo variants, add them here and document above.

If the wordmark changes shape or color, also re-derive the accent color and update `skill/references/DESIGN_TOKENS.md` accordingly.
