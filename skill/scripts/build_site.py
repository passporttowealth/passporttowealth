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
    """Compute everything the dashboard needs to render. Spec §12."""
    by_month_in = defaultdict(float)
    by_month_out = defaultdict(float)
    by_category = defaultdict(float)
    by_month_cat = defaultdict(lambda: defaultdict(float))
    rows_for_table = []
    accounts = set()
    currency = "USD"
    for r in rows:
        if r.get("currency"):
            currency = r["currency"]
        accounts.add(r["account"])
        if r["category"] in ("EXCLUDE", "TRANSFER"):
            continue
        month = r["date"][:7]
        if r["amount"] >= 0:
            by_month_in[month] += r["amount"]
        else:
            by_month_out[month] += -r["amount"]
        if r["category"] != "Income":
            by_category[r["category"]] += abs(r["amount"])
            by_month_cat[month][r["category"]] += abs(r["amount"])
        rows_for_table.append(r)

    months = sorted(by_month_in.keys() | by_month_out.keys())
    income = sum(by_month_in.values())
    spend = sum(by_month_out.values())
    net = income - spend

    # 3-month rolling average of net cashflow (income - spend, per month)
    net_per_month = [round(by_month_in.get(m, 0) - by_month_out.get(m, 0), 2) for m in months]
    rolling_3mo = []
    for i in range(len(net_per_month)):
        window = net_per_month[max(0, i - 2):i + 1]
        rolling_3mo.append(round(sum(window) / len(window), 2) if window else None)

    # Top categories used in the monthly stacked chart (top N + "Other")
    top_n = 7
    cat_totals_sorted = sorted(by_category.items(), key=lambda x: -x[1])
    top_categories_for_monthly = [c for c, _ in cat_totals_sorted[:top_n]] + ["Other"]
    monthly_by_category = {}
    for m in months:
        cell = {}
        for c, _ in cat_totals_sorted[:top_n]:
            cell[c] = round(by_month_cat[m].get(c, 0), 2)
        other = sum(v for c, v in by_month_cat[m].items()
                    if c not in {c2 for c2, _ in cat_totals_sorted[:top_n]})
        cell["Other"] = round(other, 2)
        monthly_by_category[m] = cell

    rows_for_table.sort(key=lambda r: r["date"], reverse=True)
    return {
        "currency": currency,
        "months": months,
        "by_month_in": [round(by_month_in.get(m, 0), 2) for m in months],
        "by_month_out": [round(by_month_out.get(m, 0), 2) for m in months],
        "cashflow_3mo_avg": rolling_3mo,
        "category_totals": [(c, round(a, 2)) for c, a in cat_totals_sorted],
        "monthly_by_category": monthly_by_category,
        "top_categories_for_monthly": top_categories_for_monthly,
        "accounts": sorted(accounts),
        "kpis": {
            "income_total": round(income, 2),
            "spend_total": round(spend, 2),
            "net_total": round(net, 2),
            "income_avg_per_month": round(income / max(len(months), 1), 2),
            "spend_avg_per_month": round(spend / max(len(months), 1), 2),
            "net_avg_per_month": round(net / max(len(months), 1), 2),
            "savings_rate_pct": round(net / income * 100, 1) if income else None,
            "n_months": len(months),
        },
        "transactions": [
            {"date": r["date"], "description": r["description"][:60],
             "amount": round(r["amount"], 2), "category": r["category"],
             "account": r["account"]}
            for r in rows_for_table[:500]
        ],
        "insights": _generate_insights(rows_for_table, by_category, by_month_in, by_month_out, months, currency),
        "methodology": _build_methodology(rows, currency),
    }


def _generate_insights(table_rows, by_category, by_month_in, by_month_out, months, currency) -> list[str]:
    """Auto-generated factual insights. NEVER advisory — that's the advisor's job.
    Each item is plain English with optional <strong> spans."""
    insights = []
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency + " ")

    def m(v): return f"{sym}{abs(v):,.0f}" if v >= 0 else f"-{sym}{abs(v):,.0f}"

    # 1. Top spend category
    if by_category:
        top_cat, top_amt = max(by_category.items(), key=lambda x: x[1])
        total_spend = sum(by_category.values())
        if total_spend:
            pct = top_amt / total_spend * 100
            insights.append(
                f"Your biggest spending category is <strong>{top_cat}</strong> at {m(top_amt)} "
                f"— that's {pct:.0f}% of everything you spent."
            )

    # 2. Largest single transaction
    if table_rows:
        biggest = max(table_rows, key=lambda r: abs(r["amount"]))
        insights.append(
            f"Your largest single transaction was <strong>{m(biggest['amount'])}</strong> "
            f"on {biggest['date']} — \"{biggest['description'][:40]}\" ({biggest['account']})."
        )

    # 3. Recurring subscriptions
    subs_rows = [r for r in table_rows if r["category"] == "Subscriptions"]
    if subs_rows:
        subs_total = sum(abs(r["amount"]) for r in subs_rows)
        n_subs = len(subs_rows)
        per_month = subs_total / max(len(months), 1)
        insights.append(
            f"You have <strong>{n_subs} subscription charges</strong> in this period — "
            f"about {m(per_month)} per month going to recurring services."
        )

    # 4. Income trend, first vs second half
    if len(months) >= 4:
        half = len(months) // 2
        first_half = sum(by_month_in[m] for m in months[:half])
        second_half = sum(by_month_in[m] for m in months[half:])
        if first_half > 0 and second_half > 0:
            change = (second_half - first_half) / first_half * 100
            direction = "up" if change > 0 else "down"
            insights.append(
                f"Your income was <strong>{abs(change):.0f}% {direction}</strong> in the second half "
                f"of this period vs. the first half ({m(second_half)} vs. {m(first_half)})."
            )

    # 5. Highest spend month vs avg
    if by_month_out:
        avg_out = sum(by_month_out.values()) / len(by_month_out)
        peak_m, peak_v = max(by_month_out.items(), key=lambda x: x[1])
        if avg_out > 0:
            ratio = (peak_v - avg_out) / avg_out * 100
            if ratio > 15:
                insights.append(
                    f"Your highest-spend month was <strong>{peak_m}</strong> at {m(peak_v)}, "
                    f"about {ratio:.0f}% above your monthly average."
                )

    # 6. Best savings month
    if months:
        nets = {m: by_month_in.get(m, 0) - by_month_out.get(m, 0) for m in months}
        best_m, best_v = max(nets.items(), key=lambda x: x[1])
        if best_v > 0:
            insights.append(
                f"You saved the most in <strong>{best_m}</strong>: {m(best_v)} that month."
            )

    return insights


def _build_methodology(rows, currency) -> list[list[str]]:
    """Plain-English methodology entries [(label, value), ...] for the
    'How was this dashboard built?' section."""
    by_source = defaultdict(int)
    by_account = defaultdict(int)
    for r in rows:
        by_source[r["source_file"]] += 1
        by_account[r["account"]] += 1

    rules_path = workspace_root() / "rules.yaml"
    if not rules_path.exists():
        rules_path = SKILL_ROOT / "templates" / "rules-starter.yaml"
    rules_count = 0
    if rules_path.exists():
        try:
            import yaml
            rules_count = len(yaml.safe_load(rules_path.read_text()) or [])
        except Exception:
            rules_count = 0

    transferred = sum(1 for r in rows if r["category"] == "TRANSFER")
    excluded = sum(1 for r in rows if r["category"] == "EXCLUDE")
    uncat = sum(1 for r in rows if r["category"] == "Uncategorized")

    sanity_path = output_dir() / "sanity_confirmed.json"
    sanity_note = "Not yet confirmed."
    if sanity_path.exists():
        try:
            data = json.loads(sanity_path.read_text())
            ack = data.get("acknowledged_violations") or []
            if ack:
                sanity_note = f"Confirmed at {data.get('confirmed_at', '?')}; user acknowledged warnings: {', '.join(ack)}."
            else:
                sanity_note = f"Confirmed at {data.get('confirmed_at', '?')}; all hard floors passed."
        except Exception:
            pass

    items = [
        ["Total transactions ingested", f"{len(rows):,} rows"],
        ["Source files", ", ".join(f"{n} ({c})" for n, c in by_source.items())],
        ["Accounts", ", ".join(f"{n} ({c})" for n, c in by_account.items())],
        ["Reporting currency", currency],
        ["FX source", "European Central Bank reference rates (via Frankfurter API). Used for any non-reporting-currency conversions; per-transaction date."],
        ["Categorization rules", f"{rules_count} rules from rules.yaml"],
        ["Self-transfers detected and excluded", f"{transferred} rows ({transferred // 2} pairs)"],
        ["Other excluded rows", f"{excluded} (work expenses, brokerage buys, payments between own cards, etc.)"],
        ["Uncategorized rows", f"{uncat} (shown as 'Uncategorized' on the dashboard; add rules to rules.yaml to fix)"],
        ["Sanity checks", sanity_note],
        ["Sensitive-content gate (OP-1)", "Paystubs and tax documents are skipped by default. Their content is never read unless the user opts in per file."],
    ]
    return items


def render_index(template: str, agg: dict, generated_at: datetime) -> str:
    """Substitute {{ DATA }} and other named placeholders in the template."""
    cur = agg["currency"]
    kpis = agg["kpis"]

    def fm(v):
        return fmt_money(v, cur)

    payload_json = json.dumps(agg, default=str)

    date_from = agg["months"][0] if agg["months"] else "—"
    date_to = agg["months"][-1] if agg["months"] else "—"

    replacements = {
        "{{ DASHBOARD_TITLE }}":   "Your Finance Dashboard · Passport to Wealth",
        "{{ DASHBOARD_HEADLINE }}": "Your Finance Dashboard",
        "{{ GENERATED_AT_ISO }}":  generated_at.isoformat(),
        "{{ GENERATED_AT_HUMAN }}": generated_at.strftime("%B %d, %Y"),
        "{{ DATE_FROM }}":         date_from,
        "{{ DATE_TO }}":           date_to,
        "{{ N_MONTHS }}":          str(kpis["n_months"]),
        "{{ N_ACCOUNTS }}":        str(len(agg["accounts"])),
        "{{ CURRENCY }}":          cur,
        "{{ KPI_INCOME }}":        fm(kpis["income_total"]),
        "{{ KPI_SPEND }}":         fm(kpis["spend_total"]),
        "{{ KPI_NET }}":           fm(kpis["net_total"]),
        "{{ KPI_INCOME_AVG }}":    fm(kpis["income_avg_per_month"]),
        "{{ KPI_SPEND_AVG }}":     fm(kpis["spend_avg_per_month"]),
        "{{ KPI_NET_AVG }}":       fm(kpis["net_avg_per_month"]),
        "{{ KPI_SAVINGS_RATE }}":  (f"{kpis['savings_rate_pct']}%"
                                    if kpis["savings_rate_pct"] is not None else "—"),
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
    rendered = render_index(template, agg, generated_at=datetime.now(timezone.utc))
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
