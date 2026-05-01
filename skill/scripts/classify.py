#!/usr/bin/env python3
"""classify.py — sort files from inbox/ into the canonical subfolders.

Implements spec §7. Filename heuristics + first-page text-layer keyword
matching for PDFs (no OCR ever). Honors OP-1 (sensitivity check) before any
file open. Produces a JSON report on stdout (with --json) for the agent to
relay to the user.

Usage:
    python3 skill/scripts/classify.py [--dry-run] [--json]

Reads:  $WORKSPACE/inbox/
Writes: moves files into $WORKSPACE/{01..05}_*/ (or stages a report only with --dry-run)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable

# Make _lib importable regardless of how the script is invoked
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    workspace_root, get_logger, write_envelope, is_sensitive,
    SENSITIVE_CONTENT_KEYWORDS,
)

log = get_logger("classify")

BUCKETS = [
    "01_bank_transactions",
    "02_payslips",
    "03_amazon_orders",
    "04_reference_docs",
    "05_other",
]

HEURISTICS = [
    ("01_bank_transactions", r"(?i)(statement|activity|transactions|chase|deutsche|schwab|amex|hsbc|barclays|wells\s*fargo|bank|checking|savings|brokerage)"),
    ("01_bank_transactions", r"(?i)\.(ofx|qfx|qif)$"),
    ("02_payslips", r"(?i)(payslip|paystub|payroll|gehalt|lohn|^va_|^sv_|^lb_)"),
    ("03_amazon_orders", r"(?i)(amazon|order.summary)"),
    ("04_reference_docs", r"(?i)(tax|1099|w-?2|ssn|passport|identity|bescheinigung|steuer|finanzamt|^id_)"),
]

CSV_HEADER_HINTS_BANK = re.compile(
    r"(?i)(date|posting\s*date|description|amount|balance|verwendungszweck|buchungstag|betrag)"
)


def classify_one(path: Path) -> tuple[str, str]:
    name = path.name
    if name.startswith(".") or name == "__MACOSX":
        return ("__skip__", "OS metadata")

    for bucket, pat in HEURISTICS:
        if re.search(pat, name):
            return (bucket, f"filename matches /{pat}/")

    suffix = path.suffix.lower()

    if suffix == ".csv":
        try:
            with path.open(encoding="utf-8", errors="replace") as f:
                for _ in range(20):
                    line = f.readline()
                    if not line:
                        break
                    if line.startswith("#"):
                        continue
                    if CSV_HEADER_HINTS_BANK.search(line):
                        return ("01_bank_transactions", "CSV header looks like bank data")
                    break
        except OSError as e:
            log.warning("couldn't peek CSV %s: %s", path.name, e)

    if suffix == ".pdf":
        text = _read_pdf_text(path)
        if text is None:
            return ("05_other", "PDF has no text layer (would need OCR — opt-in only)")
        for kw in SENSITIVE_CONTENT_KEYWORDS:
            if kw in text:
                return ("04_reference_docs", f"PDF text mentions sensitive keyword ({kw!r})")
        if "Order Placed" in text and "Amazon" in text:
            return ("03_amazon_orders", "PDF text contains Amazon order summary markers")
        if any(s in text for s in ["Statement", "Account Number", "Posting Date", "Beginning Balance"]):
            return ("01_bank_transactions", "PDF text looks like a bank statement")

    if suffix in {".xml", ".ofx", ".qfx", ".qif"}:
        return ("01_bank_transactions", f"{suffix} extension — bank export format")

    return ("05_other", "no rule matched — set aside for you to look at")


def _read_pdf_text(path: Path) -> str | None:
    try:
        import pdfplumber
    except ImportError:
        log.warning("pdfplumber not installed; treating all PDFs as unknown text content")
        return None
    try:
        with pdfplumber.open(str(path)) as pdf:
            if not pdf.pages:
                return None
            return pdf.pages[0].extract_text() or ""
    except Exception as e:
        log.warning("pdfplumber failed on %s: %s", path.name, e)
        return None


def collect_inbox(ws: Path) -> list[Path]:
    inbox = ws / "inbox"
    if not inbox.is_dir():
        return []
    return [p for p in inbox.rglob("*") if p.is_file() and not p.name.startswith(".")]


def ensure_buckets(ws: Path):
    for b in BUCKETS:
        (ws / b).mkdir(parents=True, exist_ok=True)


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="report without moving files")
    p.add_argument("--json", action="store_true", help="emit JSON for the agent to parse")
    args = p.parse_args(argv)

    ws = workspace_root()
    log.info("workspace: %s", ws)
    ensure_buckets(ws)

    inbox_files = collect_inbox(ws)
    if not inbox_files:
        result = {"sorted": [], "ambiguous": [], "skipped": [], "moved": 0, "inbox_empty": True}
        print(json.dumps(result, indent=2) if args.json else "Inbox is empty — nothing to sort.")
        return 0

    report = {"sorted": [], "ambiguous": [], "skipped": [], "moved": 0, "inbox_empty": False}

    for f in inbox_files:
        try:
            bucket, reason = classify_one(f)
        except Exception as e:
            write_envelope("FCB-0101", "classify", "classify_one", f"{e!r} on {f.name}")
            log.exception("classify failed on %s", f.name)
            report["skipped"].append({"file": f.name, "reason": f"classifier error: {e}"})
            continue

        if bucket == "__skip__":
            report["skipped"].append({"file": f.name, "reason": reason})
            continue

        # OP-1 sensitivity gate
        text = _read_pdf_text(f) if f.suffix.lower() == ".pdf" else None
        is_sens, sens_reason = is_sensitive(f, _content_text=text)
        if is_sens and bucket not in {"02_payslips", "04_reference_docs"}:
            log.info("%s reclassified to 04_reference_docs (%s)", f.name, sens_reason)
            bucket = "04_reference_docs"
            reason = f"reclassified for safety: {sens_reason}"

        if bucket == "05_other":
            report["ambiguous"].append({"file": f.name, "reason": reason})
        else:
            report["sorted"].append({"file": f.name, "bucket": bucket, "reason": reason})

        if not args.dry_run:
            dest = ws / bucket / f.name
            if dest.exists():
                stem, suf = dest.stem, dest.suffix
                i = 1
                while dest.exists():
                    dest = ws / bucket / f"{stem} ({i}){suf}"
                    i += 1
            shutil.move(str(f), str(dest))
            report["moved"] += 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\nFound {len(inbox_files)} files. Sorted {len(report['sorted'])}, "
              f"{len(report['ambiguous'])} ambiguous, {len(report['skipped'])} skipped.\n")
        for r in report["sorted"]:
            print(f"  ✓ {r['file']:<40s} → {r['bucket']:<22s} ({r['reason']})")
        for r in report["ambiguous"]:
            print(f"  ? {r['file']:<40s} → 05_other  ({r['reason']})")
        for r in report["skipped"]:
            print(f"  · {r['file']:<40s} skipped  ({r['reason']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
