# Demo Kit

> **⚠ Synthetic data only.** Not a real person, not real accounts, not real transactions. Fictional persona "Alex Demo" with all-zero account numbers and SSN. Safe to use, share, and inspect.

A self-contained set of dummy financial files you can drop into a fresh workspace's `inbox/` folder to test the entire Finance Clarity pipeline end-to-end — without using your own real finances.

## What's inside

| File | Format | What it covers |
|---|---|---|
| `demo_checking_2025.csv` | USD checking account, 12 months | ~400 transactions: salary, recurring bills, groceries, restaurants, transport, subscriptions, quarterly transfers to brokerage. Merchant patterns chosen to overlap with `skill/templates/rules-starter.yaml`. |
| `demo_brokerage_2025.csv` | USD brokerage account, 12 months | Quarterly transfers in (paired with checking outflows — tests the transfer detector), quarterly dividends, a few stock buys (should be EXCLUDEd by categorization). |
| `duplicate_q3_checking.csv` | Same data as Q3 of the checking file | Tests the deduper. After ingest, the skill should keep the longer file and flag the duplicate. |
| `paystub_jan_2025.pdf` | Text-layer PDF | Tests OP-1 sensitive-content detection. Contains "Gross Pay", "Net Pay", "Social Security Number" — the skill should refuse to read it without per-file consent. |
| `tax_assessment_2024.pdf` | Text-layer PDF | Tests OP-1 detection by content — contains "Internal Revenue Service" and "1099-INT". Should also be skipped by default. |
| `amazon_orders_2025.pdf` | Text-layer PDF | An OK-to-read PDF. Six order summaries that the skill should be able to parse and use to attribute the `SPLIT_AMAZON` token in categorization. |
| `mystery_scan.pdf` | Image-only PDF (no text layer) | Tests the no-OCR rule. Should land in `05_other/` with a "couldn't read this" note rather than being silently OCRed. |

## How to use

### Option 1 — drop into a fresh workspace (recommended)

1. Install the workspace per `docs/advisor-onboarding.md` (or run the installer at `installer/Welcome.command` / `Welcome.bat`).
2. Open the workspace: double-click `START-HERE` on your Desktop.
3. The skill greets you and a Finder window opens at `inbox/`.
4. Open `demo-kit/data/` in another Finder window.
5. Select all files in `demo-kit/data/` and drag them into the `inbox/` window.
6. In the Terminal, type: `build my report`.

The skill will walk through sort → dedupe → privacy gate → normalize → categorize → sanity check → publish, exactly as it would for real client data.

### Option 2 — use the build script to regenerate

If the demo data needs to change (new merchants in the rules-starter, different scenarios, more edge cases), edit `build_demo.py` and re-run:

```bash
python3 demo-kit/build_demo.py
```

Outputs are deterministic (seeded RNG), so re-running with no edits produces byte-identical files.

## What you should see at each stage

| Stage | Expected outcome |
|---|---|
| **Sort** | 7 files found. ~5 routed correctly (1 brokerage CSV + 2 checking CSVs + 3 PDFs). The mystery scan should be flagged "I couldn't read this — set aside." |
| **Dedupe** | The Q3 duplicate is identified; the skill keeps the longer checking file and drops or flags the duplicate. |
| **Privacy gate** | Skill announces it's skipping `paystub_jan_2025.pdf` and `tax_assessment_2024.pdf` by default. You can opt to include them per file. |
| **Normalize** | Skill detects USD, MM/DD dates, debits-negative — confirms with you in plain English. |
| **Categorize** | ~85% of transactions should categorize automatically using the starter rules. The transfer pairs (checking → brokerage) should be detected and EXCLUDEd from spend totals. Brokerage `Buy` rows should be EXCLUDEd. |
| **Sanity gate** | Should pass all hard floors (savings rate, transfers %, etc.) for this data. Top 10 categories should make sense. |
| **Build** | A dashboard renders with: ~$70k income, ~$60k spend, recurring subscriptions visible, quarterly transfer pattern visible. |
| **Publish** | If you have publishing-host credentials configured, publishes behind a generated passcode. If not, builds locally only. |

## What this kit is NOT

- **Not a multi-currency test.** Single-currency (USD) by design. For multi-currency / EU bank format / DD-vs-MM date detection, see the CI test fixtures in `skill/references/test-fixtures/` (TBD per backlog).
- **Not a stress test.** ~412 transactions across 12 months. Real households often have 3–5x that volume. Performance testing is separate.
- **Not a malicious-input test.** Doesn't include adversarial PDFs, encoding edge cases, or files designed to exploit parser bugs. Those belong in security testing, not the demo kit.
- **Not a substitute for real data validation.** Once the demo runs cleanly, the next test is on a real client folder under supervision — that's where bank-format edge cases actually surface.

## Refreshing the kit

If you change `skill/templates/rules-starter.yaml` and want the demo to match the new rules:

1. Update merchant names in `build_demo.py` to overlap with the new patterns.
2. Re-run: `python3 demo-kit/build_demo.py`.
3. Commit the changes (both `build_demo.py` and the regenerated files in `data/`).
