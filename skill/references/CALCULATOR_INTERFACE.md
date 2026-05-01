# Calculator Interface

> **⚠ Prototype.** Calculator choice itself is a kickoff decision (per `engagement/kickoff-agenda.md` §4). Until picked, the slot renders a placeholder card.

The dashboard has one **Calculator slot**. Only one calculator ships in v1 — the Sprint 1 scope per `engagement/project-overview.md`. Anything else moves to Sprint 2.

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

## Candidates from kickoff

Per `engagement/kickoff-agenda.md` §4, candidates are:

- **FIRE number** — savings × multiplier vs. inputs (annual spend, retirement age).
- **FX risk** — exposure breakdown across currencies, what-if shocks.
- **Retirement projection** — contributions + growth assumptions over horizon.
- **Emergency fund** — months of expenses covered, gap-to-target.
- **Buy-vs-rent** — break-even comparison given rent, price, rates, taxes.

Decision criteria: useful for cross-border audience, demoable to ~35 advisors, fits local-first / privacy-first architecture.

## Default until kickoff decision

`type: "placeholder"` in `config.yaml` — slot renders:

> "Your advisor will turn this into your chosen visual tool."

This way the dashboard publishes successfully even if no calculator is configured (acceptance criterion §20.12).
