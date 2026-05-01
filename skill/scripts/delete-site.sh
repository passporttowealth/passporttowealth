#!/bin/bash
# delete-site.sh — take the user's published dashboard down. Spec §15.
#
# Confirms with the user, calls DELETE on the host, clears local state.
# Local data (rules, fx_cache, etc.) is preserved — only the public site
# goes away.
#
# Usage:
#   delete-site.sh [--yes]  (--yes skips the confirmation; do not pass casually)

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
ENV_FILE="$WS/.env"
STATE="$WS/.herenow/state.json"
CRED_FILE="${HOME}/.herenow/credentials"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "$STATE" ] || fail "no published site found — nothing to delete"

SLUG=$(jq -r '.publishes | keys[0] // ""' "$STATE" 2>/dev/null)
[ -n "$SLUG" ] || fail "no slug in $STATE — nothing to delete"
URL=$(jq -r --arg s "$SLUG" '.publishes[$s].siteUrl // ("https://" + $s + ".here.now/")' "$STATE")

# ── Confirm ───────────────────────────────────────────────────────────────────
SKIP_CONFIRM=""
for arg in "$@"; do [ "$arg" = "--yes" ] && SKIP_CONFIRM=1; done
if [ -z "$SKIP_CONFIRM" ]; then
  cat <<EOF

This will remove your dashboard at:
    $URL

Your data on this laptop stays put — only the public page goes away.
You can publish a new one any time by saying "publish".

EOF
  read -r -p "Type 'yes delete' to confirm: " CONFIRM
  if [ "$CONFIRM" != "yes delete" ]; then
    echo "Cancelled. Nothing was changed."
    exit 0
  fi
fi

step "Deleting site on host"
if [ -f "$CRED_FILE" ]; then
  TOKEN=$(tr -d '[:space:]' < "$CRED_FILE")
  RESP=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
    -H "Authorization: Bearer $TOKEN" \
    "https://here.now/api/v1/publish/$SLUG" 2>&1) || true
  case "$RESP" in
    200|204) echo "  ✓ host returned $RESP — site deleted" ;;
    404)     echo "  · host returned 404 — site already gone (treating as success)" ;;
    *)       printf '\033[33m  ⚠ host returned %s — verify in your account dashboard\033[0m\n' "$RESP" ;;
  esac
else
  printf '\033[33m  ⚠ credentials missing — local state cleared but host still has the site\033[0m\n'
  echo "    delete it manually from your account dashboard"
fi

# Clear local state regardless — slug is gone from our perspective
rm -f "$STATE"
# Keep .env DASHBOARD_PASSCODE in case the user re-publishes; just clear SITE_URL
if [ -f "$ENV_FILE" ]; then
  grep -v '^SITE_URL=' "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

cat <<EOF

✓ Done. Your dashboard at $URL is no longer online.
  Your local data is untouched. To publish a new one later, just say "publish".

EOF
