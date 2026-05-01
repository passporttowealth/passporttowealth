#!/usr/bin/env python3
"""categorize.py — apply rules.yaml to transactions_normalized.csv.

Implements spec §10. Rule engine + transfer detection. Produces:
  - transactions_tagged.csv (per-row category/subcategory)
  - monthly_actuals.csv (pivot: month × category → amount)

Usage:
    python3 skill/scripts/categorize.py [--json]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import workspace_root, get_logger, write_envelope, output_dir

log = get_logger("categorize")


def load_rules() -> list[dict]:
    """Load rules.yaml from workspace, or fall back to skill's starter."""
    ws = workspace_root()
    user_rules = ws / "rules.yaml"
    starter = Path(__file__).resolve().parent.parent / "templates" / "rules-starter.yaml"
    src = user_rules if user_rules.exists() else starter
    if not src.exists():
        write_envelope("FCB-0401", "categorize", "load_rules", "no rules.yaml found")
        return []

    try:
        import yaml
    except ImportError:
        log.error("pyyaml not installed; cannot load rules")
        return []

    try:
        with src.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
    except Exception as e:
        write_envelope("FCB-0402", "categorize", "load_rules", f"yaml parse error: {e}")
        return []

    if not isinstance(data, list):
        write_envelope("FCB-0403", "categorize", "load_rules", "rules.yaml must be a list")
        return []

    return data


def apply_rules(description: str, rules: list[dict]) -> tuple[str, str]:
    """Return (category, subcategory) for a description. First match wins."""
    for rule in rules:
        pat = rule.get("match", "")
        if not pat:
            continue
        try:
            if re.search(pat, description):
                return rule.get("category", "Uncategorized"), rule.get("subcategory", "")
        except re.error as e:
            log.warning("invalid regex %r: %s", pat, e)
            continue
    return "Uncategorized", ""


def detect_transfers(rows: list[dict]) -> list[dict]:
    """Mark matched transfer pairs as TRANSFER. Spec §10.3.

    Pairs an outflow on account A with an inflow on account B within ±3 days
    and ±2% amount tolerance (after FX conversion if currencies differ — for
    v1 single-currency we just match on amount).
    """
    by_date_account = defaultdict(list)
    for r in rows:
        by_date_account[(r["date"], r["account"])].append(r)

    used = set()
    for i, r in enumerate(rows):
        if i in used or r["amount"] >= 0:
            continue
        # Look for a matching positive amount in another account ±3 days
        d0 = date.fromisoformat(r["date"])
        target_amount = -r["amount"]
        for delta in range(-3, 4):
            d = (d0 + timedelta(days=delta)).isoformat()
            for j, candidate in enumerate(rows):
                if j in used or j == i:
                    continue
                if candidate["account"] == r["account"]:
                    continue
                if candidate["date"] != d:
                    continue
                if candidate["amount"] <= 0:
                    continue
                if abs(candidate["amount"] - target_amount) / target_amount <= 0.02:
                    r["category"] = "TRANSFER"
                    candidate["category"] = "TRANSFER"
                    r["subcategory"] = f"transfer to {candidate['account']}"
                    candidate["subcategory"] = f"transfer from {r['account']}"
                    used.update([i, j])
                    log.info("matched transfer: %s -> %s on %s (amount %s)",
                             r["account"], candidate["account"], r["date"], r["amount"])
                    break
            if i in used:
                break
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    out_dir = output_dir()
    src = out_dir / "transactions_normalized.csv"
    if not src.exists():
        msg = "no transactions_normalized.csv yet — run normalize first"
        print(json.dumps({"error": msg}) if args.json else msg)
        return 1

    rules = load_rules()
    log.info("loaded %d rules", len(rules))

    rows: list[dict] = []
    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            r["amount"] = float(r["amount"])
            cat, sub = apply_rules(r.get("description", ""), rules)
            r["category"] = cat
            r["subcategory"] = sub
            rows.append(r)

    rows = detect_transfers(rows)

    # Write tagged CSV
    out_csv = out_dir / "transactions_tagged.csv"
    fieldnames = ["date", "description", "amount", "currency", "account",
                  "source_file", "source_row", "category", "subcategory"]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Pivot: month × category → amount (sum), excluding EXCLUDE/TRANSFER
    monthly = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["category"] in ("EXCLUDE", "TRANSFER"):
            continue
        month = r["date"][:7]
        monthly[month][r["category"]] += r["amount"]

    out_pivot = out_dir / "monthly_actuals.csv"
    all_cats = sorted({c for m in monthly.values() for c in m})
    with out_pivot.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month"] + all_cats)
        for m in sorted(monthly.keys()):
            w.writerow([m] + [round(monthly[m].get(c, 0), 2) for c in all_cats])

    counts = defaultdict(int)
    for r in rows:
        counts[r["category"]] += 1
    summary = {
        "total_rows": len(rows),
        "categories": dict(counts),
        "rules_used": len(rules),
        "output_csv": str(out_csv),
        "monthly_csv": str(out_pivot),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n✓ Tagged {len(rows)} rows using {len(rules)} rules.")
        print(f"  Top categories by row count:")
        for cat, n in sorted(counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    {n:>5}  {cat}")
        print(f"\n  → {out_csv.name}")
        print(f"  → {out_pivot.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
