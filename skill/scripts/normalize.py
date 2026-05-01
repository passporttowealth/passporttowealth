#!/usr/bin/env python3
"""normalize.py — produce transactions_normalized.csv from sorted bank files.

Implements spec §9. Canonical schema:
    date, description, amount, currency, account, source_file, source_row

Where:
  - date is ISO 8601 (YYYY-MM-DD)
  - amount is signed decimal, NEGATIVE = money out
  - account is a stable alias derived from the file (later overridden by user via §7.7)

Per-file detection (currency, sign convention, date format) writes to
normalize_report.yaml so refreshes are deterministic.

Usage:
    python3 skill/scripts/normalize.py [--json]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import workspace_root, get_logger, write_envelope, output_dir, read_csv_with_comments

log = get_logger("normalize")

# Map raw bank columns → canonical names (case-insensitive, longest match first)
DESC_COLS = ("description", "verwendungszweck", "narrative", "memo", "details")
AMOUNT_COLS = ("amount", "betrag", "value")
DATE_COLS = ("date", "posting date", "buchungstag", "transaction date", "trans date")


def _find_col(row_keys, candidates):
    lk = {k.lower().strip(): k for k in row_keys}
    for c in candidates:
        if c in lk:
            return lk[c]
    return None


def _detect_date_format(samples: list[str]) -> str:
    """Return one of: '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%m/%d/%Y'. Best-effort."""
    has_dot = any("." in s for s in samples)
    has_slash = any("/" in s for s in samples)
    if has_dot:
        return "%d.%m.%Y"
    if has_slash:
        # day > 12 anywhere → DD/MM
        for s in samples:
            parts = s.split("/")
            if len(parts) == 3:
                try:
                    if int(parts[0]) > 12:
                        return "%d/%m/%Y"
                except ValueError:
                    continue
        return "%m/%d/%Y"
    return "%Y-%m-%d"


def _parse_amount(s: str) -> float:
    s = s.strip().replace(" ", "")
    # Handle German "1.234,56" → 1234.56 or US "1,234.56" → 1234.56
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):  # German style
            s = s.replace(".", "").replace(",", ".")
        else:                              # US thousands
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        # ambiguous — assume German decimal comma if 2 digits after
        if re.match(r"^-?\d+,\d{2}$", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    return float(s)


def _detect_currency(file_path: Path, header_text: str) -> str:
    blob = (header_text + " " + file_path.name).lower()
    if "eur" in blob: return "EUR"
    if "gbp" in blob or "sterling" in blob: return "GBP"
    if "chf" in blob: return "CHF"
    if "usd" in blob: return "USD"
    return "USD"  # default for v1 (US-first audience)


def _detect_account_alias(file_path: Path, header_text: str) -> str:
    """Cheap pre-aliasing — user gets to override at the first sanity gate (§7.7)."""
    name = file_path.stem
    blob = header_text.lower()
    if "broker" in name.lower() or "broker" in blob:
        return "Brokerage"
    if "savings" in name.lower():
        return "Savings"
    if "credit" in name.lower() or "card" in name.lower():
        return "Credit Card"
    if "checking" in name.lower() or "current" in name.lower():
        return "Checking"
    return name.replace("_", " ").title()


def _read_first_n_lines(path: Path, n: int = 6) -> str:
    out = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for _ in range(n):
            line = f.readline()
            if not line:
                break
            out.append(line)
    return "".join(out)


def normalize_one(path: Path) -> tuple[list[dict], dict]:
    """Return (normalized_rows, per_file_report)."""
    header_text = _read_first_n_lines(path, 6)
    currency = _detect_currency(path, header_text)
    account = _detect_account_alias(path, header_text)

    hdr, rows = read_csv_with_comments(path)
    if not rows:
        return [], {"file": path.name, "row_count": 0, "currency": currency, "account": account}

    desc_col = _find_col(hdr, DESC_COLS)
    amount_col = _find_col(hdr, AMOUNT_COLS)
    date_col = _find_col(hdr, DATE_COLS)
    if not (desc_col and amount_col and date_col):
        write_envelope("FCB-0301", "normalize", "find_columns",
                       f"missing canonical columns in {path.name}: have {hdr}")
        return [], {"file": path.name, "error": "missing canonical columns", "header": hdr}

    # Detect date format from a sample
    date_samples = [r[date_col] for r in rows[:20] if r.get(date_col)]
    date_fmt = _detect_date_format(date_samples)

    # Brokerage accounts behave differently from checking/credit:
    #   - Most rows are positive (transfers in + dividends + interest).
    #   - Negative rows are buys (already correctly signed: outflow).
    # The "debits-positive" heuristic mis-flips them. Detect brokerage
    # by account alias OR by the presence of an Action / Symbol column
    # and skip the inversion.
    is_brokerage = (
        account.lower().startswith("broker")
        or _find_col(hdr, ("action", "symbol", "quantity")) is not None
    )

    if is_brokerage:
        sign_factor = 1.0
        debits_positive = False  # already correctly signed; no inversion
    else:
        # Detect sign convention from amount distribution.
        amounts = []
        for r in rows[:60]:
            try:
                amounts.append(_parse_amount(r[amount_col]))
            except (ValueError, KeyError):
                continue
        pos_count = sum(1 for a in amounts if a > 0)
        neg_count = sum(1 for a in amounts if a < 0)
        # In our canonical schema debits are NEGATIVE. If the source uses
        # debits-positive convention (most rows positive), invert.
        debits_positive = pos_count > neg_count * 1.3
        sign_factor = -1.0 if debits_positive else 1.0

    out_rows = []
    for i, r in enumerate(rows, start=1):
        try:
            d = datetime.strptime(r[date_col], date_fmt).date().isoformat()
        except (ValueError, KeyError):
            continue
        try:
            amt = _parse_amount(r[amount_col]) * sign_factor
        except (ValueError, KeyError):
            continue
        desc = (r.get(desc_col) or "").strip()
        out_rows.append({
            "date": d,
            "description": desc,
            "amount": round(amt, 2),
            "currency": currency,
            "account": account,
            "source_file": path.name,
            "source_row": i,
        })

    return out_rows, {
        "file": path.name,
        "row_count": len(out_rows),
        "currency": currency,
        "account": account,
        "date_format": date_fmt,
        "debits_positive": debits_positive,
    }


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    ws = workspace_root()
    out_dir = output_dir()
    bank_dir = ws / "01_bank_transactions"
    if not bank_dir.is_dir():
        msg = "no 01_bank_transactions folder yet — run classify first"
        print(json.dumps({"error": msg}) if args.json else msg)
        return 1

    files = sorted(p for p in bank_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    if not files:
        msg = "no CSVs in 01_bank_transactions/ to normalize"
        print(json.dumps({"error": msg}) if args.json else msg)
        return 1

    all_rows = []
    reports = []
    for f in files:
        try:
            rows, report = normalize_one(f)
        except Exception as e:
            write_envelope("FCB-0302", "normalize", "normalize_one", f"{e!r} on {f.name}")
            log.exception("normalize failed on %s", f.name)
            continue
        all_rows.extend(rows)
        reports.append(report)

    out_csv = out_dir / "transactions_normalized.csv"
    fieldnames = ["date", "description", "amount", "currency", "account", "source_file", "source_row"]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    out_report = out_dir / "normalize_report.yaml"
    out_report.write_text(json.dumps(reports, indent=2), encoding="utf-8")

    summary = {
        "total_rows": len(all_rows),
        "files": reports,
        "output_csv": str(out_csv),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n✓ Normalized {len(all_rows)} rows from {len(files)} files into {out_csv.name}\n")
        for r in reports:
            print(f"  · {r['file']}: {r.get('row_count', 0)} rows, "
                  f"{r.get('currency', '?')}, "
                  f"date={r.get('date_format', '?')}, "
                  f"debits_positive={r.get('debits_positive', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
