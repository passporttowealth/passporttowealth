#!/usr/bin/env python3
"""dedupe.py — hash + content dedupe across the sorted bank folder.

Implements spec §8. Two-pass:
  1. Whole-file SHA-256 — exact duplicates → keep shortest path, move others
     to inbox/.duplicates/ (recoverable).
  2. CSV content hash on parsed rows — same data, different filename → flag.

Usage:
    python3 skill/scripts/dedupe.py [--json]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import workspace_root, get_logger, file_sha256, read_csv_with_comments

log = get_logger("dedupe")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    ws = workspace_root()
    bank_dir = ws / "01_bank_transactions"
    if not bank_dir.is_dir():
        msg = "no 01_bank_transactions folder yet — run classify first"
        print(json.dumps({"error": msg}) if args.json else msg)
        return 0

    files = sorted(p for p in bank_dir.iterdir() if p.is_file())
    if not files:
        msg = "no bank files to dedupe"
        print(json.dumps({"dedup_exact": [], "dedup_content_overlap": []}) if args.json else msg)
        return 0

    # Pass 1: exact-file SHA dedupe
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_hash[file_sha256(f)].append(f)

    dup_dir = ws / "inbox" / ".duplicates"
    exact_dups = []
    for h, group in by_hash.items():
        if len(group) > 1:
            group.sort(key=lambda p: (len(p.name), p.name))
            keeper = group[0]
            for victim in group[1:]:
                dup_dir.mkdir(parents=True, exist_ok=True)
                dest = dup_dir / victim.name
                shutil.move(str(victim), str(dest))
                exact_dups.append({"kept": keeper.name, "moved": victim.name, "reason": "identical SHA-256"})
                log.info("exact dupe: kept %s, moved %s", keeper.name, victim.name)

    # Pass 2: content-level overlap on CSVs
    overlaps = []
    csv_files = [p for p in bank_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv"]
    csv_sigs: list[tuple[Path, set[tuple]]] = []
    for f in csv_files:
        try:
            _hdr, rows = read_csv_with_comments(f)
            sig = {tuple(r.get(k, "") for k in sorted(r.keys())) for r in rows}
            csv_sigs.append((f, sig))
        except Exception as e:
            log.warning("could not parse %s: %s", f.name, e)

    for i, (a, sig_a) in enumerate(csv_sigs):
        for b, sig_b in csv_sigs[i+1:]:
            if not sig_a or not sig_b:
                continue
            common = sig_a & sig_b
            if not common:
                continue
            smaller = min(len(sig_a), len(sig_b))
            pct = len(common) / smaller * 100
            if pct >= 50:
                overlaps.append({
                    "file_a": a.name, "file_b": b.name,
                    "shared_rows": len(common), "smaller_total": smaller,
                    "overlap_pct": round(pct, 1),
                })
                log.info("content overlap: %s ↔ %s = %.1f%%", a.name, b.name, pct)

    report = {"dedup_exact": exact_dups, "dedup_content_overlap": overlaps}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if exact_dups:
            print(f"\nRemoved {len(exact_dups)} exact duplicates:")
            for d in exact_dups:
                print(f"  · kept {d['kept']}, moved {d['moved']}")
        if overlaps:
            print(f"\nFound {len(overlaps)} pairs of files that overlap on row content:")
            for o in overlaps:
                print(f"  · {o['file_a']} ↔ {o['file_b']}  (shared {o['shared_rows']} of {o['smaller_total']} rows = {o['overlap_pct']}%)")
            print("Tell the user about these — they need a judgement call (keep both & dedupe row-by-row, keep only the longer one, or keep both as-is).")
        if not exact_dups and not overlaps:
            print("No duplicates found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
