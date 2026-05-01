#!/usr/bin/env python3
"""build_site.py — populate the site template with the user's data. Spec §12.

Refuses to run unless sanity_confirmed.json is present and recent (OP-4).
Reads transactions_tagged.csv + monthly_actuals.csv, writes a populated
site/ folder ready to publish.

Usage:
    python3 skill/scripts/build_site.py [--out DIR] [--force]
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import workspace_root, get_logger, output_dir, fmt_money

log = get_logger("build_site")

SKILL_ROOT = Path(__file__).resolve().parent.parent  # skill/
TEMPLATE_DIR = SKILL_ROOT / "templates" / "site"
SANITY_MAX_AGE_SECS = 3600  # 1 hour per spec §11


def check_sanity_gate() -> dict:
    """OP-4: refuse to run without a recent sanity_confirmed.json."""
    p = output_dir() / "sanity_confirmed.json"
    if not p.exists():
        return {"ok": False, "reason": "sanity_confirmed.json missing — run sanity gate first"}
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        return {"ok": False, "reason": f"sanity_confirmed.json unreadable: {e}"}
    confirmed_at = datetime.fromisoformat(data["confirmed_at"])
    if confirmed_at.tzinfo is None:
        confirmed_at = confirmed_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - confirmed_at).total_seconds()
    if age > SANITY_MAX_AGE_SECS:
        return {"ok": False, "reason": f"sanity confirmation is {age / 60:.0f} minutes old "
                                       f"(>{SANITY_MAX_AGE_SECS / 60:.0f}); re-run sanity gate"}
    return {"ok": True, "data": data}


def load_tagged() -> list[dict]:
    src = output_dir() / "transactions_tagged.csv"
    rows = []
    with src.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r["amount"] = float(r["amount"])
            rows.append(r)
    return rows


def aggregate(rows: list[dict]) -> dict:
    """Compute everything the dashboard needs to render."""
    by_month_in = defaultdict(float)
    by_month_out = defaultdict(float)
    by_category = defaultdict(float)
    rows_for_table = []
    currency = "USD"
    for r in rows:
        if r.get("currency"):
            currency = r["currency"]
        if r["category"] in ("EXCLUDE", "TRANSFER"):
            continue
        month = r["date"][:7]
        if r["amount"] >= 0:
            by_month_in[month] += r["amount"]
        else:
            by_month_out[month] += -r["amount"]
        by_category[r["category"]] += abs(r["amount"])
        rows_for_table.append(r)

    months = sorted(by_month_in.keys() | by_month_out.keys())
    income = sum(by_month_in.values())
    spend = sum(by_month_out.values())
    net = income - spend

    rows_for_table.sort(key=lambda r: r["date"], reverse=True)
    return {
        "currency": currency,
        "months": months,
        "by_month_in": [round(by_month_in.get(m, 0), 2) for m in months],
        "by_month_out": [round(by_month_out.get(m, 0), 2) for m in months],
        "category_totals": sorted(
            ((c, round(a, 2)) for c, a in by_category.items() if c != "Income"),
            key=lambda x: -x[1],
        ),
        "kpis": {
            "income_total": round(income, 2),
            "spend_total": round(spend, 2),
            "net_total": round(net, 2),
            "savings_rate_pct": round(net / income * 100, 1) if income else None,
            "n_months": len(months),
        },
        "transactions": [
            {"date": r["date"], "description": r["description"][:60],
             "amount": round(r["amount"], 2), "category": r["category"],
             "account": r["account"]}
            for r in rows_for_table[:500]
        ],
    }


def render_index(template: str, agg: dict, generated_at: str) -> str:
    """Substitute {{ DATA }} and other named placeholders in the template."""
    cur = agg["currency"]
    kpis = agg["kpis"]

    def fm(v):
        return fmt_money(v, cur)

    payload_json = json.dumps(agg, default=str)

    replacements = {
        "{{ DASHBOARD_TITLE }}": "Your Finance Clarity Dashboard",
        "{{ GENERATED_AT }}": generated_at,
        "{{ KPI_INCOME }}": fm(kpis["income_total"]),
        "{{ KPI_SPEND }}": fm(kpis["spend_total"]),
        "{{ KPI_NET }}": fm(kpis["net_total"]),
        "{{ KPI_SAVINGS_RATE }}": (f"{kpis['savings_rate_pct']}%"
                                    if kpis["savings_rate_pct"] is not None else "—"),
        "{{ KPI_MONTHS }}": str(kpis["n_months"]),
        "{{ DASHBOARD_DATA_JSON }}": payload_json,
    }
    out = template
    for k, v in replacements.items():
        out = out.replace(k, v)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=None, help="output dir (default: workspace/site)")
    p.add_argument("--force", action="store_true", help="bypass sanity gate (CI / fixtures only)")
    args = p.parse_args(argv)

    if not args.force:
        gate = check_sanity_gate()
        if not gate["ok"]:
            print(f"✗ {gate['reason']}", file=sys.stderr)
            return 1

    rows = load_tagged()
    if not rows:
        print("✗ no transactions to render", file=sys.stderr)
        return 1

    agg = aggregate(rows)

    out_dir = Path(args.out) if args.out else (workspace_root() / "site")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy template files (HTML, assets) into out_dir
    if not TEMPLATE_DIR.exists():
        print(f"✗ template dir missing: {TEMPLATE_DIR}", file=sys.stderr)
        return 1
    for src in TEMPLATE_DIR.iterdir():
        dst = out_dir / src.name
        if src.is_symlink():
            # Resolve the symlink target and copy its real contents.
            real = src.resolve()
            if real.is_dir():
                shutil.copytree(real, dst, dirs_exist_ok=True, symlinks=False)
            else:
                shutil.copy2(real, dst)
        elif src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=False)
        else:
            shutil.copy2(src, dst)

    # Render index.html
    template = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")
    rendered = render_index(template, agg, generated_at=datetime.now(timezone.utc).isoformat())
    (out_dir / "index.html").write_text(rendered, encoding="utf-8")

    # Copy supporting CSVs into downloads/
    dl_dir = out_dir / "downloads"
    dl_dir.mkdir(exist_ok=True)
    for fn in ("transactions_tagged.csv", "monthly_actuals.csv"):
        src = output_dir() / fn
        if src.exists():
            shutil.copy2(src, dl_dir / fn)
    rules_src = workspace_root() / "rules.yaml"
    if rules_src.exists():
        shutil.copy2(rules_src, dl_dir / "rules.yaml")

    print(f"✓ Site built at {out_dir}")
    print(f"  Open {out_dir / 'index.html'} in your browser to see it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
