# Test Fixtures

> **⚠ Prototype.** Fixtures are not yet built. CI workflow (`.github/workflows/ci.yml`) is stubbed but inert until at least one fixture lands.

Three pre-built unsorted "client folders" of **fully synthetic** financial data that exercise the skill end-to-end. CI runs them on every PR.

## Required fixtures

| Fixture | Profile | What it exercises |
|---|---|---|
| `fixture-us-single-currency/` | Single US household, USD only, ~12 months | Baseline happy path |
| `fixture-eu-dual-currency/` | Berlin couple, EUR + USD, ~15 months | FX, sign conventions, multi-language merchants |
| `fixture-cross-border-complex/` | UK national in DE working US contracts, EUR + USD + GBP | Stress: multi-currency, multi-account, complex transfers, edge merchants |

## What each fixture must include (per spec acceptance criteria §20)

Each fixture should deliberately trip:

- A misclassified-sensitive-PDF case (acceptance #10) — a payslip filename that would land in `01_bank_transactions/` if classified by name only.
- A 10x-off pipeline case (acceptance #11) — a duplicate transfer that, without dedupe, would inflate income 10×.
- A missing-calculator case (acceptance #12) — `config.yaml` has `calculator.type: placeholder`.
- An iCloud-relocation prompt case (acceptance #14) — but this is environmental, not a fixture concern.
- An ambiguous-classification case — a few files with no filename pattern and an empty PDF text layer.
- At least one currency-detection ambiguity (e.g. a CSV with no currency column, account name not in the standard list).
- At least one date-format ambiguity (only days ≤ 12 in a partial-month sample).

## Source

Derive from `finance_ops/custom-build/demo/generate_demo.py` (existing demo data generator), extended with the edge cases above. Synthetic only — never derive from real client data, even in obfuscated form.
