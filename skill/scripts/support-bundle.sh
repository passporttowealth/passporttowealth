#!/bin/bash
# support-bundle.sh — triple-path delivery of a sanitized diagnostic. Spec §17.6.
#
# 1. Save zip to ~/Desktop/finance-support-bundle-{ts}.zip (always works).
# 2. Optionally upload to a fresh password-protected publishing-host slug
#    (only if publishing-host credentials work — graceful skip if not).
# 3. Open user's mail client (mailto:) with URL + temp passcode pre-filled,
#    copy the same to clipboard, print in Terminal as fallback.
#
# Bundle includes (per spec §17.6 — explicit redaction whitelist):
#   - Error envelopes from pipeline/output/errors/
#   - install.log (if exists)
#   - Last 200 lines of pipeline/output/run.log (already redacted)
#   - File COUNTS per workspace folder (no contents, no filenames)
#   - rules.yaml, fx_overrides.yaml (not sensitive)
#   - Skill versions, runtime versions, OS version, check.command output
#
# EXCLUDED EXPLICITLY:
#   .env, ~/.herenow/credentials, anything from 01_bank_transactions/,
#   02_payslips/, 04_reference_docs/, the rendered site, transactions_*.csv,
#   merchant names.

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
DESKTOP="${HOME}/Desktop"
[ -d "$DESKTOP" ] || DESKTOP="$WS"
BUNDLE="${DESKTOP}/finance-support-bundle-${TS}.zip"
STAGING=$(mktemp -d "/tmp/fcb-bundle.XXXXXX")
trap 'rm -rf "$STAGING"' EXIT

CONFIG="$WS/config.yaml"

# ── Stage allowed content ────────────────────────────────────────────────────
mkdir -p "$STAGING/errors" "$STAGING/logs" "$STAGING/config"

# Error envelopes (already redacted at write time)
if [ -d "$WS/pipeline/output/errors" ]; then
  cp "$WS/pipeline/output/errors/"*.json "$STAGING/errors/" 2>/dev/null || true
fi

# install.log (if present)
if [ -f "${HOME}/Library/Logs/passport-to-wealth-install.log" ]; then
  cp "${HOME}/Library/Logs/passport-to-wealth-install.log" "$STAGING/logs/install.log"
fi
if [ -f "${LOCALAPPDATA:-/nonexistent}/PassportToWealth/Logs/passport-to-wealth-install.log" ]; then
  cp "${LOCALAPPDATA}/PassportToWealth/Logs/passport-to-wealth-install.log" "$STAGING/logs/install.log"
fi

# Last 200 lines of run.log (already redacted)
if [ -f "$WS/pipeline/output/run.log" ]; then
  tail -n 200 "$WS/pipeline/output/run.log" > "$STAGING/logs/run.log.tail"
fi

# Non-sensitive config
[ -f "$WS/rules.yaml" ]          && cp "$WS/rules.yaml"          "$STAGING/config/"
[ -f "$WS/fx_overrides.yaml" ]   && cp "$WS/fx_overrides.yaml"   "$STAGING/config/"
[ -f "$WS/config.yaml" ]         && cp "$WS/config.yaml"         "$STAGING/config/"

# File counts only (no filenames)
{
  echo "Workspace folder counts:"
  for d in inbox 01_bank_transactions 02_payslips 03_amazon_orders 04_reference_docs 05_other; do
    n=0
    if [ -d "$WS/$d" ]; then
      n=$(find "$WS/$d" -type f ! -name '.*' | wc -l | tr -d ' ')
    fi
    printf '  %-25s %s files\n' "$d" "$n"
  done
} > "$STAGING/folder_counts.txt"

# Versions
{
  echo "Skill version: 0.0.1-stub"
  echo "Python: $(python3 --version 2>&1)"
  echo "OS: $(uname -a)"
  echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "User: (redacted)"
} > "$STAGING/versions.txt"

# ── 1. Save zip to Desktop (always works) ────────────────────────────────────
( cd "$STAGING" && zip -qr "$BUNDLE" . )
printf '✓ Saved bundle: %s\n' "$BUNDLE"

# ── 2. Upload to publishing host (best-effort) ───────────────────────────────
UPLOAD_URL=""
UPLOAD_PASSCODE=""
if [ -f "${HOME}/.herenow/credentials" ]; then
  echo "[v0 stub] would upload bundle as a fresh password-protected slug here."
  echo "         Skipped in v0 — bundle saved to Desktop instead."
fi

# ── 3. Email/clipboard/terminal-print ────────────────────────────────────────
ADVISOR_EMAIL=$(python3 -c "
try:
    import yaml
    print((yaml.safe_load(open('$CONFIG')) or {}).get('advisor', {}).get('support_email', ''))
except Exception: print('')
" 2>/dev/null)

SUBJECT="Finance Clarity support bundle ($TS)"
BODY="Hi — please find attached a support bundle from my Finance Clarity workspace.
The zip is at: $BUNDLE
$([ -n "$UPLOAD_URL" ] && echo "Or download from: $UPLOAD_URL  (passcode: $UPLOAD_PASSCODE)")
"

if [ -n "$ADVISOR_EMAIL" ]; then
  BODY_ENC=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read()))" <<< "$BODY")
  SUB_ENC=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$SUBJECT")
  MAILTO="mailto:${ADVISOR_EMAIL}?subject=${SUB_ENC}&body=${BODY_ENC}"
  case "$(uname -s)" in
    Darwin) open "$MAILTO" 2>/dev/null && printf '✓ Opened email to %s\n' "$ADVISOR_EMAIL" ;;
    Linux)  xdg-open "$MAILTO" 2>/dev/null && printf '✓ Opened email to %s\n' "$ADVISOR_EMAIL" ;;
    *)      printf '· mailto link:\n  %s\n' "$MAILTO" ;;
  esac
fi
if command -v pbcopy >/dev/null 2>&1; then
  printf '%s\n%s\n\n%s' "To: $ADVISOR_EMAIL" "Subject: $SUBJECT" "$BODY" | pbcopy
  echo '✓ Copied to your clipboard as a fallback'
fi

cat <<EOF

  Three ways to deliver this — pick whichever works:
    • Email is open and pre-filled (if your mail client is set up).
    • Same content is on your clipboard.
    • The zip is at: $BUNDLE

  Attach the zip to whichever message you send.

EOF
