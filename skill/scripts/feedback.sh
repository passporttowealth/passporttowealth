#!/bin/bash
# feedback.sh — triple-delivery feedback channel. Spec §15.1.
#
# Distinct from support-bundle (failures): this is for non-bug feedback —
# suggestions, "this could be better", "I love this", etc.
#
# Three parallel paths:
#   1. Local save (always): ~/Documents/my-finances/feedback/{ts}.txt
#   2. mailto: opens user's email client to advisor.feedback_email
#   3. Optional HTTPS POST to feedback.endpoint_url (config.yaml)
#      — recommended setup: Cloudflare Worker that creates a GitHub issue
#        (see docs/feedback-channel.md)
#
# Usage:
#   feedback.sh "free-text message" [--context a|b|c]
# Or read from stdin if no argument.

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
CONFIG="$WS/config.yaml"
TS=$(date -u +%Y%m%dT%H%M%SZ)

CONTEXT_LEVEL="a"
MESSAGE=""
for arg in "$@"; do
  case "$arg" in
    --context=*) CONTEXT_LEVEL="${arg#--context=}" ;;
    --context)   CONTEXT_LEVEL="next" ;;
    a|b|c)
      if [ "$CONTEXT_LEVEL" = "next" ]; then CONTEXT_LEVEL="$arg"; else MESSAGE="$MESSAGE $arg"; fi
      ;;
    *)
      MESSAGE="$MESSAGE $arg"
      ;;
  esac
done
MESSAGE="${MESSAGE# }"

if [ -z "$MESSAGE" ]; then
  if [ -t 0 ]; then
    printf 'Tell me what is on your mind (Enter twice to send): '
    MESSAGE=""
    while IFS= read -r line; do
      [ -z "$line" ] && [ -n "$MESSAGE" ] && break
      MESSAGE="${MESSAGE}${line}
"
    done
  else
    MESSAGE=$(cat)
  fi
fi

# ── 1. Local save (always) ────────────────────────────────────────────────────
mkdir -p "$WS/feedback"
LOCAL="$WS/feedback/${TS}.txt"
{
  echo "Timestamp:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Context:      $CONTEXT_LEVEL"
  echo "Skill ver:    0.0.1-stub"
  echo "Platform:     $(uname -s) $(uname -r)"
  echo ""
  echo "Message:"
  echo "$MESSAGE"
} > "$LOCAL"
chmod 600 "$LOCAL"
printf '✓ Saved locally: %s\n' "$LOCAL"

# Read advisor feedback email + endpoint from config (yaml). Use python for parsing.
ADVISOR_EMAIL=$(python3 -c "
import sys
try:
    import yaml
    with open('$CONFIG') as f: c = yaml.safe_load(f) or {}
    print((c.get('advisor') or {}).get('feedback_email', ''))
except Exception:
    print('')
" 2>/dev/null)
ENDPOINT=$(python3 -c "
import sys
try:
    import yaml
    with open('$CONFIG') as f: c = yaml.safe_load(f) or {}
    print((c.get('feedback') or {}).get('endpoint_url') or '')
except Exception:
    print('')
" 2>/dev/null)
ENDPOINT_TOKEN=$(python3 -c "
import sys
try:
    import yaml
    with open('$CONFIG') as f: c = yaml.safe_load(f) or {}
    print((c.get('feedback') or {}).get('endpoint_token') or '')
except Exception:
    print('')
" 2>/dev/null)

# ── 2. mailto: ────────────────────────────────────────────────────────────────
if [ -n "$ADVISOR_EMAIL" ]; then
  SUBJECT="Finance Clarity feedback ($TS)"
  # URL-encode body & subject
  BODY_ENC=$(python3 -c "
import urllib.parse, sys
print(urllib.parse.quote(sys.stdin.read()))
" <<< "$MESSAGE")
  SUBJECT_ENC=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$SUBJECT")
  MAILTO="mailto:${ADVISOR_EMAIL}?subject=${SUBJECT_ENC}&body=${BODY_ENC}"
  case "$(uname -s)" in
    Darwin)  open "$MAILTO" 2>/dev/null && printf '✓ Opened email to %s\n' "$ADVISOR_EMAIL" ;;
    Linux)   xdg-open "$MAILTO" 2>/dev/null && printf '✓ Opened email to %s\n' "$ADVISOR_EMAIL" ;;
    *)       printf '· mailto link (paste into your email):\n  %s\n' "$MAILTO" ;;
  esac
  # Also copy to clipboard for the case where mailto: is unset
  if command -v pbcopy >/dev/null 2>&1; then
    printf 'To: %s\nSubject: %s\n\n%s' "$ADVISOR_EMAIL" "$SUBJECT" "$MESSAGE" | pbcopy
    echo '✓ Copied to your clipboard as a fallback'
  fi
fi

# ── 3. HTTPS POST to optional endpoint ────────────────────────────────────────
if [ -n "$ENDPOINT" ]; then
  PAYLOAD=$(python3 -c "
import json, platform, sys
msg = sys.stdin.read()
print(json.dumps({
    'v': 1,
    'ts': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'client_id': '$(echo -n "$WS" | shasum -a 256 | head -c 16)',
    'advisor_id': 'passporttowealth',
    'skill_version': '0.0.1-stub',
    'platform': platform.platform(),
    'message': msg,
    'context_level': '$CONTEXT_LEVEL',
    'context': {},
}))
" <<< "$MESSAGE")
  HEADERS=(-H "Content-Type: application/json")
  [ -n "$ENDPOINT_TOKEN" ] && HEADERS+=(-H "Authorization: Bearer $ENDPOINT_TOKEN")
  RESP=$(curl -fsS -X POST "${HEADERS[@]}" -d "$PAYLOAD" "$ENDPOINT" 2>&1) && \
    printf '✓ Sent to advisor endpoint: %s\n' "$RESP" || \
    { printf '· Endpoint POST failed (queued for retry): %s\n' "$RESP"
      mkdir -p "$WS/pipeline/output/feedback/_pending"
      cp "$LOCAL" "$WS/pipeline/output/feedback/_pending/" ; }
fi

if [ -z "$ADVISOR_EMAIL" ] && [ -z "$ENDPOINT" ]; then
  echo ""
  echo "ℹ No advisor feedback_email or feedback.endpoint_url configured in:"
  echo "    $CONFIG"
  echo "  Your message is saved locally; ask your advisor for delivery details."
fi

echo ""
