"""Shared utilities used by every script in the skill pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Workspace layout ──────────────────────────────────────────────────────────
def workspace_root() -> Path:
    """Return the workspace root.

    Order of resolution:
      1. $FCB_WORKSPACE if set (used by tests)
      2. ~/Documents/my-finances if it exists
      3. cwd if it has an inbox/ folder
      4. cwd as last resort
    """
    if "FCB_WORKSPACE" in os.environ:
        return Path(os.environ["FCB_WORKSPACE"]).resolve()
    candidate = Path.home() / "Documents" / "my-finances"
    if candidate.is_dir():
        return candidate
    cwd = Path.cwd()
    if (cwd / "inbox").is_dir():
        return cwd
    return cwd


def output_dir() -> Path:
    p = workspace_root() / "pipeline" / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p


def errors_dir() -> Path:
    p = output_dir() / "errors"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Logging (OP-7 redacted) ───────────────────────────────────────────────────
_REDACT_PATTERNS = [
    re.compile(r"\b\d{6,}\b"),                           # 6+ contiguous digits → likely account number
    re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),              # SSN-shaped
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]+\b"),            # Anthropic key shape
    re.compile(r"\bhn_(live|test)_[A-Za-z0-9_-]+\b"),    # publishing-host key shape
]


def _redact(s: str) -> str:
    for pat in _REDACT_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    return s


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return _redact(msg)


def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(f"fcb.{name}")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fh = logging.FileHandler(output_dir() / "run.log", encoding="utf-8")
    fh.setFormatter(_RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(_RedactingFormatter("%(levelname)s: %(message)s"))
    log.addHandler(fh)
    log.addHandler(sh)
    log.propagate = False
    return log


# ── Error envelopes (spec §17.2) ──────────────────────────────────────────────
SKILL_VERSION = "0.0.1-stub"
ENVELOPE_SCHEMA_V = 1


def write_envelope(
    code: str,
    category: str,
    step: str,
    message: str,
    workflow: str = "build",
    extra_context: dict | None = None,
) -> Path:
    """Write a structured error envelope to pipeline/output/errors/."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    fn = errors_dir() / f"{ts}-{code}.json"
    envelope: dict[str, Any] = {
        "v": ENVELOPE_SCHEMA_V,
        "ts": datetime.now(timezone.utc).isoformat(),
        "client_id": _client_id(),
        "advisor_id": "passporttowealth",
        "skill_version": SKILL_VERSION,
        "platform": _platform_string(),
        "runtime": f"Python {sys.version.split()[0]}",
        "correlation_id": _correlation_id(),
        "error": {
            "code": code,
            "category": category,
            "step": step,
            "message": _redact(message),
            "user_visible_message": "Something didn't work. I've written a report.",
        },
        "context": {"workflow": workflow, **(extra_context or {})},
    }
    fn.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return fn


_CORRELATION_ID = None


def _correlation_id() -> str:
    global _CORRELATION_ID
    if _CORRELATION_ID is None:
        _CORRELATION_ID = hashlib.sha256(
            f"{os.getpid()}-{time.time()}".encode()
        ).hexdigest()[:16]
    return _CORRELATION_ID


def _client_id() -> str:
    """Stable hash of the workspace path. No PII, no account info."""
    return hashlib.sha256(str(workspace_root()).encode()).hexdigest()[:16]


def _platform_string() -> str:
    import platform as _p
    return f"{_p.system()} {_p.release()} ({_p.machine()})"


# ── Sensitivity gate (OP-1, content + filename) ───────────────────────────────
SENSITIVE_FILENAME_PATTERNS = re.compile(
    r"(?i)(payslip|paystub|payroll|payslip|tax|1099|w-?2|ssn|passport"
    r"|identity|steuer|lohn|bescheinigung|gehalt|sozialvers)"
)
SENSITIVE_CONTENT_KEYWORDS = [
    "Brutto", "Netto", "Net Pay", "Gross Pay", "Social Security Number",
    "Tax Identification", "Steuer-ID", "Internal Revenue Service",
    "Finanzamt", "1099", "W-2", "YTD Earnings", "Lohnsteuer",
    "Sozialversicherung", "Form 1040",
]


def is_sensitive(path: Path, _content_text: str | None = None) -> tuple[bool, str]:
    """Return (is_sensitive, reason). Filename check is fast; content check
    is invoked only if a text sample is provided."""
    name = path.name
    if SENSITIVE_FILENAME_PATTERNS.search(name):
        return True, f"filename matches sensitive pattern ({name!r})"
    parent = path.parent.name
    if parent in {"02_payslips", "04_reference_docs"}:
        return True, f"located in sensitive folder ({parent})"
    if _content_text:
        for kw in SENSITIVE_CONTENT_KEYWORDS:
            if kw in _content_text:
                return True, f"content contains sensitive keyword ({kw!r})"
    return False, ""


# ── Hashing ───────────────────────────────────────────────────────────────────
def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Progress (B9.5) ──────────────────────────────────────────────────────────
# Long-running operations (FX fetch, asset copy) need ongoing-progress signals
# so the user doesn't think the pipeline got stuck. Stdlib-only helper that
# prints a single line updated in place via carriage return. Writes to STDERR
# (so --json stdout stays clean for tests/agents) and is a no-op when stderr
# isn't a TTY (CI, captured output, redirected logs) — prevents \r spam in
# captured logs and keeps `subprocess.run(... capture_output=True)` clean.

def progress(label: str, current: int, total: int, width: int = 24) -> None:
    """Print a single-line progress bar that updates in place.

    Args:
        label:   short description, e.g. "FX rates"
        current: 1-indexed completed count
        total:   total work units; if 0, no-op (avoids div-by-zero)
        width:   bar width in chars (default 24)

    Goes to stderr. Auto-prints a trailing newline when current >= total so
    subsequent output appears below. Silent when stderr is not a TTY.
    """
    if total <= 0:
        return
    if not sys.stderr.isatty():
        return
    pct = current * 100 // total
    filled = width * current // total
    bar = "█" * filled + "·" * (width - filled)
    sys.stderr.write(f"\r  {label}: {bar} {current:>4}/{total} ({pct:>3}%)")
    sys.stderr.flush()
    if current >= total:
        sys.stderr.write("\n")


# ── Currency helpers ──────────────────────────────────────────────────────────
def fmt_money(amount: float, currency: str = "USD") -> str:
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "CHF": "CHF "}.get(currency, currency + " ")
    sign = "-" if amount < 0 else ""
    return f"{sign}{sym}{abs(amount):,.2f}"


# ── Generic CSV reader/writer ─────────────────────────────────────────────────
def _is_comment_line(line: str) -> bool:
    """Recognize a leading comment line. Tolerates csv-writer quote-wrapping of
    comments that contained commas (e.g. `"# foo, bar"`)."""
    s = line.lstrip()
    return s.startswith("#") or s.startswith('"#') or s.startswith("'#")


def _count_leading_comments(path: Path) -> int:
    n = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if _is_comment_line(line):
                n += 1
            elif line.strip() == "":
                n += 1  # also skip blank lines between header and data
            else:
                return n
    return n


def read_csv_with_comments(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV, skipping `# ...` comment lines at the top. Returns (header, rows)."""
    n_comments = _count_leading_comments(path)
    with path.open(encoding="utf-8", newline="") as f:
        for _ in range(n_comments):
            f.readline()
        # Peek a sample line to guess the delimiter, then rewind to that point.
        pos = f.tell()
        sample = f.readline()
        f.seek(pos)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delim)
        rows = list(reader)
        header = reader.fieldnames or []
    return header, rows
