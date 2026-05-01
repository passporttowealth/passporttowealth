# Calculator Interface

> **⚠ Prototype.** Calculator choice is configured in `config.yaml` per workspace. Until picked, the slot renders a placeholder card.

The dashboard has one **Calculator slot**. Only one calculator ships per workspace in v1 — anything more moves to a future sprint.

## Plug-in contract

Every calculator implements:

```
calculator/
  manifest.yaml          ← name, description, required inputs, output keys
  inputs.html            ← form fragment populated into the slot
  compute.py             ← pure function: dict[str, Any] -> dict[str, Any]
  render.html            ← output fragment with named slots for compute() outputs
  README.md              ← what the calculator does, in plain English
```

`build_site.py` reads `manifest.yaml`, validates the required inputs against the user's data (e.g. "needs ≥12 months of transactions"), and either renders the calculator or shows a "needs more data" card explaining what's missing.

## Candidate calculators

The current shortlist:

- **FIRE number** — savings × multiplier vs. inputs (annual spend, retirement age).
- **FX risk** — exposure breakdown across currencies, what-if shocks.
- **Retirement projection** — contributions + growth assumptions over horizon.
- **Emergency fund** — months of expenses covered, gap-to-target.
- **Buy-vs-rent** — break-even comparison given rent, price, rates, taxes.

Decision criteria: useful for the target cross-border audience, demoable in a short live session, fits the local-first / privacy-first architecture.

## Default until kickoff decision

`type: "placeholder"` in `config.yaml` — slot renders:

> "Your advisor will turn this into your chosen visual tool."

This way the dashboard publishes successfully even if no calculator is configured (acceptance criterion §20.12).
