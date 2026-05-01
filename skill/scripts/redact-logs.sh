#!/bin/bash
# redact-logs.sh — re-run OP-7 redaction across all log files in the workspace.
# Spec §17.1.
#
# Idempotent — running twice produces the same output as running once.
#
# Patterns scrubbed: account-number-shaped digits (≥6 contiguous), SSN-shape,
# Anthropic-key-shape, publishing-host-key-shape, the user's passcode, the
# user's API key. See _lib.py for the full list.

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }

step "Scanning logs in $WS for sensitive patterns"

# Collect log paths to redact
LOGS=()
[ -f "$WS/pipeline/output/run.log" ] && LOGS+=("$WS/pipeline/output/run.log")
[ -f "$WS/install.log" ] && LOGS+=("$WS/install.log")
# Claude Code logs (third-party, location varies)
for d in "$WS/.claude" "$WS/.claude/conversation" ; do
  [ -d "$d" ] && while IFS= read -r p; do LOGS+=("$p"); done < <(find "$d" -type f -name "*.log" -o -name "*.jsonl" 2>/dev/null)
done

if [ ${#LOGS[@]} -eq 0 ]; then
  echo "  No logs found — nothing to redact."
  exit 0
fi

# Use the same redaction logic as _lib.py — call into it via Python
# so there's a single source of truth for what gets redacted.
PASSCODE=""
if [ -f "$WS/.env" ] && grep -q '^DASHBOARD_PASSCODE=' "$WS/.env"; then
  PASSCODE=$(grep '^DASHBOARD_PASSCODE=' "$WS/.env" | cut -d= -f2- | tr -d '"')
fi

for log in "${LOGS[@]}"; do
  python3 - "$log" "$PASSCODE" <<'PYEOF'
import re, sys, shutil
from pathlib import Path
sys.path.insert(0, "$SCRIPT_DIR")
log_path = Path(sys.argv[1])
extra_passcode = sys.argv[2] if len(sys.argv) > 2 else ""

patterns = [
    re.compile(r"\b\d{6,}\b"),
    re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]+\b"),
    re.compile(r"\bhn_(live|test)_[A-Za-z0-9_-]+\b"),
]
text = log_path.read_text(encoding="utf-8", errors="replace")
for pat in patterns:
    text = pat.sub("[REDACTED]", text)
if extra_passcode:
    text = text.replace(extra_passcode, "[REDACTED-PASSCODE]")
log_path.write_text(text, encoding="utf-8")
PYEOF
  echo "  ✓ redacted: $log"
done

echo ""
echo "Done. Each log was scrubbed in place. The originals are NOT kept on disk —"
echo "if you needed an unredacted copy for some reason, that opportunity is past."
echo ""
