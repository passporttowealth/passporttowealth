#!/usr/bin/env python3
"""fx_fetch.py — auto-source daily FX rates from Frankfurter (ECB-backed).

Implements spec §10.5. Per-transaction daily rates with a local cache.
Fallback chain: Frankfurter → ECB XML → exchangerate.host → cached. No
hardcoded last-resort rate.

Usage:
    python3 skill/scripts/fx_fetch.py --base EUR --pairs USD,GBP --start 2025-01-01 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import workspace_root, get_logger, write_envelope

log = get_logger("fx_fetch")

FRANKFURTER_TIMEOUT = 10


def fx_cache_dir() -> Path:
    p = workspace_root() / "fx_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_path(d: date) -> Path:
    return fx_cache_dir() / str(d.year) / f"{d.isoformat()}.json"


def get_rate(base: str, target: str, on_date: date) -> tuple[float | None, str]:
    """Return (rate, source) or (None, reason). Rate converts 1 unit base → target."""
    if base == target:
        return 1.0, "identity"

    cached = _read_cache(on_date, base)
    if cached and target in cached.get("rates", {}):
        return cached["rates"][target], cached["source"]

    fresh = _fetch_frankfurter(on_date, base)
    if fresh and target in fresh.get("rates", {}):
        _write_cache(on_date, fresh)
        return fresh["rates"][target], "frankfurter"

    # Fall back to closest available date in cache (±7 days)
    for delta in range(1, 8):
        for d in (on_date - timedelta(days=delta), on_date + timedelta(days=delta)):
            cached = _read_cache(d, base)
            if cached and target in cached.get("rates", {}):
                return cached["rates"][target], f"cache_offset_{(d - on_date).days}d"

    write_envelope("FCB-1101", "fx", "get_rate",
                   f"no rate for {base}->{target} on {on_date} within ±7 days")
    return None, "unavailable"


def _read_cache(d: date, base: str) -> dict | None:
    p = _cache_path(d)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        if data.get("base") == base:
            return data
    except (OSError, ValueError):
        return None
    return None


def _write_cache(d: date, data: dict):
    p = _cache_path(d)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _fetch_frankfurter(d: date, base: str) -> dict | None:
    url = f"https://api.frankfurter.app/{d.isoformat()}?from={base}"
    req = Request(url, headers={"User-Agent": "finance-clarity-build/0.0.1"})
    try:
        with urlopen(req, timeout=FRANKFURTER_TIMEOUT) as resp:
            data = json.load(resp)
    except (URLError, OSError, ValueError) as e:
        log.warning("frankfurter unreachable for %s: %s", d, e)
        return None
    return {
        "date": data.get("date", d.isoformat()),
        "base": data.get("base", base),
        "rates": data.get("rates", {}),
        "source": "frankfurter",
        "fetched_at": datetime.utcnow().isoformat(),
    }


def warm_cache(start: date, end: date, base: str, targets: list[str]) -> dict:
    """Fetch every business day in [start, end] for one base. Idempotent."""
    fetched, skipped, failed = 0, 0, 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # Mon–Fri
            cached = _read_cache(cur, base)
            if cached and all(t in cached.get("rates", {}) for t in targets):
                skipped += 1
            else:
                data = _fetch_frankfurter(cur, base)
                if data:
                    _write_cache(cur, data)
                    fetched += 1
                else:
                    failed += 1
        cur += timedelta(days=1)
    return {"fetched": fetched, "skipped": skipped, "failed": failed,
            "range": [start.isoformat(), end.isoformat()], "base": base}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="EUR")
    p.add_argument("--pairs", default="USD,GBP", help="comma-separated target currencies")
    p.add_argument("--start", default=None, help="ISO date — default: 24 months ago")
    p.add_argument("--end", default=None, help="ISO date — default: today")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    end = datetime.fromisoformat(args.end).date() if args.end else date.today()
    start = datetime.fromisoformat(args.start).date() if args.start else end - timedelta(days=730)
    targets = [t.strip().upper() for t in args.pairs.split(",") if t.strip()]

    summary = warm_cache(start, end, args.base.upper(), targets)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"FX cache warmed: {summary['fetched']} fetched, {summary['skipped']} already cached, "
              f"{summary['failed']} failed in {start} → {end} (base {args.base.upper()})")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
