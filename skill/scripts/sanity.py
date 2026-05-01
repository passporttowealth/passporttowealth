#!/usr/bin/env python3
"""sanity.py — hard floors + interactive gate. Spec §11.

Runs OP-12 hard floors first; surfaces violations. Writes
sanity_confirmed.json on user "looks right" so the site builder will run.

Usage:
    python3 skill/scripts/sanity.py [--json] [--auto-confirm]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import workspace_root, get_logger, output_dir, write_envelope, fmt_money

log = get_logger("sanity")


def load_tagged() -> list[dict]:
    src = output_dir() / "transactions_tagged.csv"
    if not src.exists():
        return []
    rows = []
    with src.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r["amount"] = float(r["amount"])
            rows.append(r)
    return rows


def compute_summary(rows: list[dict]) -> dict:
    if not rows:
        return {}
    dates = sorted(r["date"] for r in rows)
    by_month_cat = defaultdict(lambda: defaultdict(float))
    by_month_in = defaultdict(float)
    by_month_out = defaultdict(float)
    n_transfers = 0
    transfer_total = 0.0
    n_uncat = 0
    by_account = defaultdict(int)
    by_currency = set()
    big5 = []
    for r in rows:
        m = r["date"][:7]
        cat = r["category"]
        by_account[r["account"]] += 1
        by_currency.add(r["currency"])
        if cat == "TRANSFER":
            n_transfers += 1
            transfer_total += abs(r["amount"])
            continue
        if cat == "EXCLUDE":
            continue
        if cat == "Uncategorized":
            n_uncat += 1
        by_month_cat[m][cat] += r["amount"]
        if r["amount"] >= 0:
            by_month_in[m] += r["amount"]
        else:
            by_month_out[m] += -r["amount"]
        big5.append(r)

    big5.sort(key=lambda r: -abs(r["amount"]))
    months = sorted(by_month_in.keys() | by_month_out.keys())

    n_relevant = sum(1 for r in rows if r["category"] not in ("TRANSFER", "EXCLUDE"))
    income_avg = sum(by_month_in.values()) / max(len(months), 1)
    spend_avg = sum(by_month_out.values()) / max(len(months), 1)
    net_avg = income_avg - spend_avg
    savings_rate = (net_avg / income_avg * 100) if income_avg > 0 else None

    # Top 10 categories by absolute spend
    cat_totals = defaultdict(float)
    for m in by_month_cat.values():
        for c, a in m.items():
            cat_totals[c] += abs(a)
    top10 = sorted(cat_totals.items(), key=lambda x: -x[1])[:10]

    return {
        "rows_total": len(rows),
        "rows_relevant": n_relevant,
        "rows_uncategorized": n_uncat,
        "rows_transfers": n_transfers,
        "transfers_total_abs": round(transfer_total, 2),
        "currencies": sorted(by_currency),
        "accounts": dict(by_account),
        "date_range": [dates[0], dates[-1]],
        "n_months": len(months),
        "income_avg_per_month": round(income_avg, 2),
        "spend_avg_per_month": round(spend_avg, 2),
        "net_avg_per_month": round(net_avg, 2),
        "savings_rate_pct": round(savings_rate, 1) if savings_rate is not None else None,
        "top_10_categories": [(c, round(a, 2)) for c, a in top10],
        "biggest_5_transactions": [
            {"date": r["date"], "description": r["description"][:60],
             "amount": round(r["amount"], 2), "account": r["account"], "category": r["category"]}
            for r in big5[:5]
        ],
    }


def hard_floors(summary: dict) -> list[dict]:
    """OP-12. Return list of violation dicts."""
    violations = []
    sr = summary.get("savings_rate_pct")
    if sr is not None and not (-50 <= sr <= 90):
        violations.append({
            "floor": "savings_rate",
            "value": sr,
            "message": f"Savings rate is {sr}%, outside the typical range [-50%, +90%]. "
                       "Often this means I miscounted a transfer between two of your "
                       "accounts as income or spending.",
        })
    n_rel = summary.get("rows_relevant", 0)
    if n_rel > 0:
        uncat_pct = summary.get("rows_uncategorized", 0) / n_rel * 100
        if uncat_pct >= 50:
            violations.append({
                "floor": "uncategorized_pct",
                "value": round(uncat_pct, 1),
                "message": f"{uncat_pct:.1f}% of your transactions don't have a category yet. "
                           "Worth fixing the rules first — your dashboard will be more useful.",
            })
    # Transfer dominance
    rel_total = max(summary.get("income_avg_per_month", 0) +
                    summary.get("spend_avg_per_month", 0), 1) * summary.get("n_months", 1)
    transfer_pct = (summary.get("transfers_total_abs", 0) / rel_total * 100) if rel_total else 0
    if transfer_pct >= 40:
        violations.append({
            "floor": "transfers_pct",
            "value": round(transfer_pct, 1),
            "message": f"About {transfer_pct:.1f}% of all the money I see is moving between "
                       "your own accounts. That's high — I might be missing a real expense or "
                       "counting one twice.",
        })
    return violations


def write_confirmed(summary: dict, ack_violations: list = None):
    """Write sanity_confirmed.json so build_site.py will run."""
    payload = {
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "totals_hash": hashlib.sha256(
            json.dumps(summary, sort_keys=True, default=str).encode()
        ).hexdigest(),
        "row_count": summary.get("rows_total"),
        "acknowledged_violations": ack_violations or [],
    }
    out = output_dir() / "sanity_confirmed.json"
    out.write_text(json.dumps(payload, indent=2))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--auto-confirm", action="store_true",
                   help="skip the interactive gate (CI / fixture runs only)")
    args = p.parse_args(argv)

    rows = load_tagged()
    if not rows:
        msg = "no transactions_tagged.csv yet — run categorize first"
        print(json.dumps({"error": msg}) if args.json else msg)
        return 1

    summary = compute_summary(rows)
    violations = hard_floors(summary)

    if args.json:
        print(json.dumps({"summary": summary, "violations": violations}, indent=2, default=str))
    else:
        cur = (summary.get("currencies") or ["USD"])[0]
        print("\n=== Quick check before I build your dashboard ===\n")
        print(f"Period covered: {summary['date_range'][0]} through {summary['date_range'][1]} "
              f"({summary['n_months']} months)")
        print(f"Accounts: {', '.join(summary['accounts'].keys())}")
        print(f"\nMonthly totals (in {cur}):")
        print(f"  Income (avg/month):    {fmt_money(summary['income_avg_per_month'], cur)}")
        print(f"  Spend  (avg/month):    {fmt_money(-summary['spend_avg_per_month'], cur)}")
        print(f"  Net    (avg/month):    {fmt_money(summary['net_avg_per_month'], cur)}")
        print(f"\nTop 10 categories by spend:")
        for c, a in summary["top_10_categories"]:
            print(f"  {fmt_money(a, cur):>14}  {c}")
        print(f"\nLargest 5 single transactions:")
        for r in summary["biggest_5_transactions"]:
            print(f"  {r['date']}  {fmt_money(r['amount'], cur):>12}  {r['description']:<40}  "
                  f"({r['account']}, {r['category']})")
        print(f"\nTransfers excluded:    {summary['rows_transfers']} "
              f"({fmt_money(summary['transfers_total_abs'], cur)})")
        print(f"Uncategorized rows:    {summary['rows_uncategorized']} of {summary['rows_relevant']} "
              f"({summary['rows_uncategorized'] / max(summary['rows_relevant'], 1) * 100:.1f}%)")

        if violations:
            print("\n" + "=" * 60)
            print("⚠ Some sanity floors tripped — please look at these first:")
            print("=" * 60)
            for v in violations:
                print(f"\n  • {v['floor']}: {v['value']}")
                print(f"    {v['message']}")

    if args.auto_confirm:
        if violations:
            print("\n[--auto-confirm with floor violations — writing acknowledgement and continuing]")
        write_confirmed(summary, ack_violations=[v["floor"] for v in violations])
        print("✓ Sanity gate confirmed (auto).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
