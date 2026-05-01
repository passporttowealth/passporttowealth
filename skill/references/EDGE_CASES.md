# Edge Cases — Bank-format quirks observed in the wild

> **⚠ Prototype.** Living document. Add a row every time the pipeline trips on a new bank format.

A reference for `normalize.py` (and to a lesser extent `classify.py`). Each row is a bank/format with the gotcha that bit us, the detection heuristic, and the workaround.

## Format

| Bank | Account type | Format | Quirk | Detection | Handling |
|---|---|---|---|---|---|
| _example_ | _Joint Checking_ | _CSV_ | _Debits as positive numbers_ | _Salary row is positive → debits-positive_ | _Multiply amount column by -1 during normalization_ |

## Known cases

| Bank | Account type | Format | Quirk | Detection | Handling |
|---|---|---|---|---|---|
| Deutsche Bank | EUR Checking | XML / CSV | DD/MM dates; "Umsatzart" column needed for transaction direction | German column headers; presence of "BLZ" | See `normalize.py` (TBD) |
| Chase | USD Credit Card | CSV | Debits-positive convention; "Posting Date" column | Header has "Posting Date,Description,Amount" | Multiply amount by -1 to align with bank-style "negative = money out" |
| Charles Schwab | USD Brokerage | CSV | Wide format with running balance; mixed cash + securities | Header has "Symbol" and "Quantity" columns | Filter to cash-only rows for cashflow analytics |
| (more to come) |  |  |  |  |  |

## Anti-patterns to watch for

- **Pending vs cleared transactions** — same transaction may appear twice across statements; `dedupe.py` content-level matching catches it.
- **Refund / chargeback rows** — original positive, refund negative, or vice-versa depending on bank.
- **Joint account double-counting** — a transaction visible to both partners might be exported twice if both partners contribute exports.
- **Multi-currency in one statement** — rare but happens; treat as separate accounts when normalizing.
- **Statement renames mid-history** — same account, statement filename changes (e.g. card number rolled). Account aliasing (spec §7.7) helps here.
