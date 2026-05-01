#!/usr/bin/env python3
"""
Generate the Finance Clarity demo kit deterministically.

Single-currency (USD), 12 months exactly (Jan–Dec 2025). Two accounts so
transfer detection still has something to chew on. Synthetic merchants chosen
to overlap with skill/templates/rules-starter.yaml so categorization produces
a meaningful spend-by-category breakdown out of the box.

Produces, in demo-kit/data/:
  - demo_checking_2025.csv          (12 months, USD, primary checking)
  - demo_brokerage_2025.csv         (12 months, USD, small brokerage account)
  - duplicate_q3_checking.csv       (deliberate dupe to test the deduper)
  - paystub_jan_2025.pdf            (text-layer PDF — should trip OP-1 by content)
  - tax_assessment_2024.pdf         (text-layer PDF — should trip OP-1 by content)
  - amazon_orders_2025.pdf          (text-layer PDF — Amazon order summary, OK to read)
  - mystery_scan.pdf                (image-only PDF — should land in 05_other/)

Run:
    python3 demo-kit/build_demo.py

Outputs are committed to the repo so testers don't need to run this. Re-run
only when the demo data needs to change.

Copyright © 2026 Passport to Wealth. All rights reserved. Synthetic data only.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "data"
OUT.mkdir(parents=True, exist_ok=True)

random.seed(42)  # deterministic outputs

# ── Demo persona — clearly fictional ──────────────────────────────────────────
PERSONA = {
    "name": "Alex Demo",
    "address": "Sample Street 1, San Francisco, CA 94102",
    "ssn_us": "000-00-0000",
    "checking_account": "****-****-****-0000",
    "brokerage_account": "Brokerage acct ending 0000",
}

YEAR = 2025
START = date(YEAR, 1, 1)
END = date(YEAR, 12, 31)

# ── Checking account — primary (USD, MM/DD dates, debits negative) ───────────
CHK_HEADER = ["Posting Date", "Description", "Amount", "Type", "Balance"]


def gen_checking():
    rows = []
    balance = 8_400.00

    # Bi-weekly salary on the 15th and last of each month
    salary_amount = 2_950.00  # net per check, ~$76,700/yr

    # Monthly recurring debits (description, abs_amount, day-of-month)
    monthly_recurring = [
        ("RENT - PARK STREET PROPERTIES",   2_650.00,  1),
        ("PG&E ELECTRIC AUTOPAY",              94.20,  3),
        ("AT&T MOBILITY",                      85.00,  5),
        ("COMCAST XFINITY INTERNET",           69.99,  7),
        ("BLUE SHIELD CA HEALTH PREMIUM",     412.00, 10),
        ("STATE FARM AUTO INSURANCE",         148.00, 12),
        ("NETFLIX.COM",                        17.99, 14),
        ("SPOTIFY USA",                        11.99, 14),
        ("APPLE.COM/BILL",                     34.99, 16),
        ("ANTHROPIC CLAUDE PRO",               20.00, 18),
        ("EQUINOX FITNESS",                   215.00, 20),
        ("AMAZON.COM*PRIME MEMBERSHIP",        14.99, 22),
        ("NYTIMES DIGITAL SUBSCRIPTION",       17.00, 25),
    ]

    sporadic_pool = [
        ("WHOLE FOODS MKT 12345 SF",           148.20),
        ("TRADER JOE'S #154 SF",                72.40),
        ("SAFEWAY STORE 0998",                  92.10),
        ("STARBUCKS STORE 09221",                6.50),
        ("PHILZ COFFEE 24TH ST",                 5.95),
        ("RESTAURANT FOREIGN CINEMA",          112.00),
        ("BURMA SUPERSTAR SF",                  86.40),
        ("CHIPOTLE 0298",                       14.20),
        ("UBER *EATS",                          38.20),
        ("DOORDASH SUSHI ROKU",                 64.50),
        ("UBER *TRIP SAN FRANCISCO",            22.50),
        ("LYFT *RIDE",                          18.40),
        ("CHEVRON 0099",                        45.30),
        ("SHELL OIL 12345",                     52.80),
        ("AMAZON.COM*A2K9P3RT0",                84.50),
        ("TARGET 00012345",                     68.20),
        ("CVS/PHARMACY #02184",                 28.50),
        ("WALGREENS #04456",                    34.10),
        ("HOME DEPOT 0099",                    142.00),
        ("DR MARTINEZ DENTAL CLINIC",          240.00),
        ("AIRBNB * HMTRPDQRS9",                312.00),
        ("UNITED AIRLINES TKT",                428.00),
        ("HERTZ RENT A CAR LAX",               184.00),
        ("BART TICKETS",                         9.20),
        ("ZARA US 1234",                        92.00),
        ("REI CO-OP MOUNTAIN VIEW",            156.00),
    ]

    # Special: one explicit transfer to brokerage each quarter (will pair with
    # a corresponding inflow on the brokerage side, testing transfer detection)
    quarterly_transfers = [(YEAR, m, 18) for m in (3, 6, 9, 12)]

    for month in range(1, 13):
        month_start = date(YEAR, month, 1)
        last_dom = _last_dom(month_start)

        # Salary — 15th and last business day
        for day in (15, last_dom):
            d = month_start.replace(day=day)
            jitter = round(random.uniform(-50, 50), 2)
            rows.append({"date": d, "desc": "PAYROLL DEPOSIT EXAMPLE CORP", "amount": salary_amount + jitter})

        # Recurring debits
        for desc, amt, dom in monthly_recurring:
            d = month_start.replace(day=min(dom, last_dom))
            jitter = round(random.uniform(-0.05, 0.05) * amt, 2)
            rows.append({"date": d, "desc": desc, "amount": -round(amt + jitter, 2)})

        # 14–22 sporadic charges per month
        for _ in range(random.randint(14, 22)):
            d = month_start + timedelta(days=random.randint(0, last_dom - 1))
            desc, amt = random.choice(sporadic_pool)
            jitter = round(random.uniform(-0.20, 0.40) * amt, 2)
            rows.append({"date": d, "desc": desc, "amount": -round(amt + jitter, 2)})

        # Quarterly transfer to brokerage
        if (YEAR, month, 18) in quarterly_transfers:
            rows.append({
                "date": month_start.replace(day=18),
                "desc": "TRANSFER TO BROKERAGE ACCT 0000",
                "amount": -2_000.00,
            })

    rows.sort(key=lambda r: r["date"])

    # Compute running balance and write CSV
    out = OUT / "demo_checking_2025.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([f"# Statement for: {PERSONA['name']}"])
        w.writerow([f"# Account: Demo Checking — {PERSONA['checking_account']}"])
        w.writerow(["# Currency: USD"])
        w.writerow(["# Convention: debits negative, credits positive"])
        w.writerow(["# Date format: MM/DD/YYYY"])
        w.writerow(CHK_HEADER)
        for r in rows:
            balance += r["amount"]
            w.writerow([
                r["date"].strftime("%m/%d/%Y"),
                r["desc"],
                f"{r['amount']:.2f}",
                "DEBIT" if r["amount"] < 0 else "CREDIT",
                f"{balance:.2f}",
            ])
    return out


# ── Brokerage account — small (USD, dividends + transfers in) ────────────────
BRK_HEADER = ["Date", "Action", "Symbol", "Description", "Quantity", "Price", "Amount"]


def gen_brokerage():
    rows = []
    # Quarterly transfers in (paired with checking outflows above)
    for month in (3, 6, 9, 12):
        d = date(YEAR, month, 19)  # 1 day after the checking outflow — realistic settlement lag
        rows.append({
            "date": d, "action": "Transfer In", "symbol": "",
            "description": "INCOMING TRANSFER FROM CHECKING 0000",
            "qty": "", "price": "", "amount": 2_000.00,
        })
    # Quarterly dividend
    for month in (1, 4, 7, 10):
        d = date(YEAR, month, 12)
        rows.append({
            "date": d, "action": "Cash Dividend", "symbol": "VTI",
            "description": "VANGUARD TOTAL STOCK MKT ETF — DIVIDEND",
            "qty": "", "price": "", "amount": round(random.uniform(34, 52), 2),
        })
    # A handful of buys (these should be EXCLUDEd by categorization)
    for month in (3, 6, 9, 12):
        d = date(YEAR, month, 21)
        rows.append({
            "date": d, "action": "Buy", "symbol": "VTI",
            "description": "BUY VTI",
            "qty": "8", "price": str(round(random.uniform(245, 275), 2)),
            "amount": -round(random.uniform(1_950, 2_050), 2),
        })

    rows.sort(key=lambda r: r["date"])

    out = OUT / "demo_brokerage_2025.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([f"# Statement for: {PERSONA['name']}"])
        w.writerow([f"# Account: {PERSONA['brokerage_account']}"])
        w.writerow(["# Currency: USD"])
        w.writerow(["# Convention: debits negative, credits positive"])
        w.writerow(["# Date format: MM/DD/YYYY"])
        w.writerow(BRK_HEADER)
        for r in rows:
            w.writerow([
                r["date"].strftime("%m/%d/%Y"),
                r["action"], r["symbol"], r["description"],
                r["qty"], r["price"], f"{r['amount']:.2f}",
            ])
    return out


# ── Duplicate — for dedupe.py to catch ────────────────────────────────────────
def gen_duplicate(checking_path):
    """Save Q3 only of the checking CSV under a different filename."""
    src = checking_path.read_text(encoding="utf-8").splitlines(keepends=True)
    out_lines = []
    for line in src:
        if line.startswith("#") or line.startswith("Posting Date"):
            out_lines.append(line)
            continue
        try:
            mm, dd, yyyy = line.split(",")[0].split("/")
            if yyyy == str(YEAR) and mm in ("07", "08", "09"):
                out_lines.append(line)
        except (ValueError, IndexError):
            continue
    out = OUT / "duplicate_q3_checking.csv"
    out.write_text("".join(out_lines), encoding="utf-8")
    return out


# ── PDFs ─────────────────────────────────────────────────────────────────────
def gen_paystub_pdf():
    out = OUT / "paystub_jan_2025.pdf"
    c = canvas.Canvas(str(out), pagesize=letter)
    c.setFont("Helvetica-Bold", 14); c.drawString(72, 720, "EXAMPLE CORP")
    c.setFont("Helvetica", 11)
    c.drawString(72, 700, "Pay Stub — Pay Period: 01/01/2025 – 01/15/2025")
    c.drawString(72, 680, f"Employee: {PERSONA['name']}")
    c.drawString(72, 665, f"Social Security Number: {PERSONA['ssn_us']}")
    c.drawString(72, 650, "Employee ID: A-12345")
    c.line(72, 640, 540, 640)
    c.drawString(72, 620, "Gross Pay (this period):       $3,200.00")
    c.drawString(72, 605, "Federal Income Tax Withheld:    $-380.00")
    c.drawString(72, 590, "State Income Tax Withheld:      $-160.00")
    c.drawString(72, 575, "Social Security Tax:            $-198.40")
    c.drawString(72, 560, "Medicare:                        $-46.40")
    c.drawString(72, 545, "Health Insurance Premium:       $-205.00")
    c.drawString(72, 530, "401(k) Contribution:            $-260.00")
    c.line(72, 520, 540, 520)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, 500, "Net Pay:                       $1,950.20")
    c.line(72, 490, 540, 490)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(72, 470, "DEMO DATA — synthetic paystub for Finance Clarity testing.")
    c.drawString(72, 455, "Not a real pay stub. Not a real person.")
    c.save()
    return out


def gen_tax_pdf():
    out = OUT / "tax_assessment_2024.pdf"
    c = canvas.Canvas(str(out), pagesize=letter)
    c.setFont("Helvetica-Bold", 14); c.drawString(72, 720, "Internal Revenue Service")
    c.setFont("Helvetica", 11)
    c.drawString(72, 700, "Form 1099-INT — Interest Income")
    c.drawString(72, 680, f"Recipient: {PERSONA['name']}")
    c.drawString(72, 665, f"Recipient SSN: {PERSONA['ssn_us']}")
    c.drawString(72, 650, "Tax Year: 2024")
    c.line(72, 640, 540, 640)
    c.drawString(72, 620, "Box 1: Interest Income            $234.18")
    c.drawString(72, 605, "Box 2: Early Withdrawal Penalty     $0.00")
    c.drawString(72, 590, "Box 4: Federal Income Tax Withheld  $0.00")
    c.line(72, 570, 540, 570)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(72, 550, "DEMO DATA — synthetic tax document for Finance Clarity testing.")
    c.save()
    return out


def gen_amazon_orders_pdf():
    out = OUT / "amazon_orders_2025.pdf"
    c = canvas.Canvas(str(out), pagesize=letter)
    c.setFont("Helvetica-Bold", 14); c.drawString(72, 720, "Amazon — Your Orders")
    c.setFont("Helvetica", 10); c.drawString(72, 700, f"Account: {PERSONA['name']}")
    y = 680
    orders = [
        ("2025-02-14", "Order #112-3456789-0000001", "Ergonomic Office Chair",     "$284.50"),
        ("2025-03-22", "Order #112-3456789-0000002", "USB-C Hub 7-in-1",           "$39.99"),
        ("2025-04-08", "Order #112-3456789-0000003", "Stainless French Press",     "$28.20"),
        ("2025-05-19", "Order #112-3456789-0000004", "Air Purifier (small room)",  "$129.00"),
        ("2025-07-01", "Order #112-3456789-0000005", "Children's books (set of 6)","$32.40"),
        ("2025-09-13", "Order #112-3456789-0000006", "Camping headlamp",            "$24.99"),
    ]
    c.line(72, y, 540, y); y -= 18
    for date_s, num, item, total in orders:
        c.drawString(72, y, f"Order Placed: {date_s}")
        c.drawString(280, y, num)
        c.drawString(460, y, total); y -= 14
        c.setFont("Helvetica-Oblique", 9); c.drawString(85, y, item)
        c.setFont("Helvetica", 10); y -= 22
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(72, 100, "DEMO DATA — synthetic order history for Finance Clarity testing.")
    c.save()
    return out


def gen_mystery_scan_pdf():
    """Image-only PDF (no text layer) — should land in 05_other/ per the no-OCR rule."""
    out = OUT / "mystery_scan.pdf"
    c = canvas.Canvas(str(out), pagesize=letter)
    c.setFillGray(0.85); c.rect(72, 100, 468, 600, stroke=0, fill=1)
    c.setFillGray(0.5);  c.rect(120, 200, 372, 400, stroke=0, fill=1)
    c.save()
    return out


# ── Helpers ──────────────────────────────────────────────────────────────────
def _last_dom(d: date) -> int:
    next_month = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (next_month - timedelta(days=1)).day


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating demo kit into", OUT)
    chk = gen_checking()
    brk = gen_brokerage()
    dup = gen_duplicate(chk)
    pay = gen_paystub_pdf()
    tax = gen_tax_pdf()
    az = gen_amazon_orders_pdf()
    scan = gen_mystery_scan_pdf()
    for p in [chk, brk, dup, pay, tax, az, scan]:
        size_kb = p.stat().st_size / 1024
        print(f"  ✓ {p.name}  ({size_kb:.1f} KB)")
    print("\nDemo kit ready. Drag the contents of demo-kit/data/ into your")
    print("workspace's inbox/ folder to test the pipeline end-to-end.")
