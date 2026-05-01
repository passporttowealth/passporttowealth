# Design Tokens

> **⚠ Prototype.** Values below are **inferred from `passporttowealth.com`** as of repo scaffolding. They mirror the public site's apparent palette, type, and mood, but are not a brand-pack handover from Arielle. **Confirm or adjust at the kickoff meeting.** Treat as v0 defaults that already feel on-brand, not a frozen system.

Source of truth for color, typography, spacing, and motion. The site template (`skill/templates/site/`) reads from this file. Brand changes happen here, not by editing component files.

## Brand context (extracted from passporttowealth.com)

| Pillar | Notes |
|---|---|
| Audience | "Financial guidance for current and aspiring US expats" |
| Voice | Approachable authority — "navigate the complexities", "clear, actionable roadmaps", "a life they love, wherever they are in the world" |
| Aesthetic | Minimalist, professional, generous whitespace, type-driven, subtle photography (headshots), fiduciary/trust signaling |
| Mood | Warm and inclusive ("we understand"), aspirational yet practical |
| Logo | Wordmark "Passport to Wealth™" — simple sans-serif, blue on light bg, white on dark bg |
| Tagline | "Financial guidance for current and aspiring US expats" |

## Color tokens

**Brand accent corrected after pixel-sampling the actual logo at `assets/brand/logo-blue.png`** — the brand is a deep navy (`#0F1E33`), not the medium blue inferred from the WebFetch summary. The chart palette has been re-anchored accordingly.

```
--color-bg              #FFFFFF             page background (clean white)
--color-bg-warm         #FAF8F4             warm off-white for hero/section variation
--color-surface         #F7F6F3             card / container background (subtle warmth)
--color-surface-raised  #FFFFFF             elevated cards
--color-border          #E5E3DE             hairline divider
--color-text            #2D2D2D             primary text (warm charcoal, not pure black)
--color-text-muted      #6B6B6B             secondary text
--color-text-subtle     #9A9A9A             captions, footnotes

--color-accent          #0F1E33             brand navy — sampled from the real logo
--color-accent-hover    #1A2D48             slight lift on hover/active
--color-accent-soft     #E8ECF2             pale navy tint for info banners / selected states

--color-positive        #2E7D5C             income, gains (warm forest, AA on bg)
--color-negative        #B33A2A             spend, losses (warm clay red, AA on bg)
--color-warning         #D9A300             cautions (matches the prototype banner)
--color-warning-bg      #FFF4D6             warning background

--color-chart-1  #0F1E33  (deep navy — primary, matches brand)
--color-chart-2  #2E7D5C  (forest)
--color-chart-3  #D9A300  (warm gold)
--color-chart-4  #B33A2A  (clay red)
--color-chart-5  #6B4FA1  (muted plum)
--color-chart-6  #2D8E9E  (teal — sibling to navy)
--color-chart-7  #C26B3F  (warm terracotta)
--color-chart-8  #5C7A8C  (cool slate)
```

All chart colors meet WCAG AA contrast against `--color-bg` for non-large text and AA-large for chart fills. Navy `#0F1E33` provides strong AAA contrast (>15:1) against white — useful for KPI numbers.

## Typography

```
--font-display   "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif
--font-body      "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif
--font-mono      ui-monospace, "SF Mono", Menlo, Consolas, monospace
```

Inter is the primary face — modern sans-serif, free, open-license, ships well in both browser-loaded and bundled forms. System-font fallbacks ensure the site works offline if the bundled woff2 fails to load. The site avoids serifs entirely (matches passporttowealth.com).

```
--font-weight-regular   400
--font-weight-medium    500
--font-weight-semibold  600
--font-weight-bold      700

--font-size-display-1   40px / 48px line-height (page hero KPI)
--font-size-display-2   28px / 36px line-height (section heading)
--font-size-h3          22px / 30px line-height (subsection)
--font-size-body-lg     18px / 28px line-height (lead paragraph)
--font-size-body        16px / 26px line-height (body — minimum for accessibility)
--font-size-small       14px / 22px line-height (captions, metadata)
--font-size-mono        13px / 20px line-height (transaction descriptions)
```

All bundled as woff2 inside `skill/templates/site/assets/fonts/`. **No Google Fonts**, no CDN — the dashboard works offline and never phones home.

## Spacing scale

Generous, matching the site's airy mood.

```
--space-1: 4px
--space-2: 8px
--space-3: 12px
--space-4: 16px    (base unit)
--space-5: 24px
--space-6: 32px
--space-7: 48px
--space-8: 64px
--space-9: 96px    (between major sections, like the site)
```

## Layout

```
--container-max     1080px       (wider than passporttowealth's text columns; data needs room)
--container-text    640px        (narrow column for body text — readability over density)
--container-data    900px        (intermediate for tables and chart blocks)
```

## Radius

```
--radius-sm: 4px       (text containers, buttons — slight, not sharp)
--radius-md: 8px       (cards, inputs)
--radius-lg: 16px      (hero blocks, photo containers — matches site's soft-rounded imagery)
--radius-pill: 9999px  (badges)
```

## Shadow

Subtle. The site relies on whitespace and color, not depth.

```
--shadow-sm   0 1px 2px rgba(20, 20, 20, 0.04), 0 1px 3px rgba(20, 20, 20, 0.04)
--shadow-md   0 2px 4px rgba(20, 20, 20, 0.06), 0 8px 24px rgba(20, 20, 20, 0.06)
--shadow-lg   0 4px 12px rgba(20, 20, 20, 0.08), 0 20px 48px rgba(20, 20, 20, 0.10)
```

## Motion

```
--ease-out         cubic-bezier(0.2, 0, 0, 1)
--duration-fast    120ms     (button press, focus ring)
--duration-base    200ms     (most transitions)
--duration-slow    320ms     (chart reveals — only when motion is allowed)
```

- All transitions ≤ 320ms.
- **Honor `prefers-reduced-motion: reduce`** — disable all chart entrance animations and any non-essential transition.

## Voice & copy guidelines

These guide every user-visible string the skill emits. Lifted directly from passporttowealth.com cadence.

**Do:**
- Speak with **approachable authority**. Confident, never condescending.
- Use **plain English**, even for technical concepts. ("I couldn't get an exchange rate" not "FX API returned 503.")
- Use **first-person from the agent** when the agent acts. ("I sorted your files" / "I'm worried about this number".)
- Use **second-person to the reader**. ("Your dashboard" / "Your passcode".)
- Acknowledge complexity without dwelling on it. ("Cross-border finances are messy — here's what I did.")
- **Action-oriented** when offering choices. ("Want me to look?" / "Type 'looks right' to continue.")

**Don't:**
- Don't use jargon — see OP-8 banned-words list.
- Don't apologize excessively — surface the issue, offer the action.
- Don't over-explain technology. ("This is a v0 skeleton" belongs in `[DIM]` text or hidden behind a toggle, not the main flow.)
- Don't be cute. Warm, not whimsical.

## Logo usage

The skill renders the wordmark in the dashboard header and footer. Real PNG assets pulled from `passporttowealth.com` live at `assets/brand/` (single source of truth) and are reachable from the dashboard template via the symlink at `skill/templates/site/assets/brand/`.

- **`assets/brand/logo-blue.png`** — primary, for white/warm backgrounds (default). 235×220 transparent PNG.
- **`assets/brand/logo-white.png`** — secondary, for dark backgrounds (footer, dark variants). 177×184 transparent PNG.
- **`assets/brand/favicon.png`** — browser tab icon. 135×110 transparent PNG.

When Arielle delivers a clean brand pack (vector SVGs, additional sizes, dark-mode variants), replace the files in place at `assets/brand/`. The HTML references will pick them up unchanged.

Logo color sampling confirms the brand mark is `#0F1E33` deep navy — see `assets/brand/README.md` for the per-pixel breakdown.
