#!/bin/bash
# find-my-site.sh — locate the user's published dashboard. Spec §15.
#
# Two sources, in order:
#   1. Local state file (.herenow/state.json) — fast, works offline
#   2. Publishing host's account API (lists all sites under the user's account)
#      — useful if local state was lost (laptop change, accidental delete)

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
STATE="$WS/.herenow/state.json"
ENV_FILE="$WS/.env"
CRED_FILE="${HOME}/.herenow/credentials"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }

# 1. Local state
if [ -f "$STATE" ]; then
  step "Found local state file"
  python3 - <<PYEOF
import json
try:
    with open("$STATE") as f: d = json.load(f)
    pubs = d.get("publishes", {})
    if not pubs:
        print("  (no published sites recorded locally)")
    for slug, info in pubs.items():
        url = info.get("siteUrl", f"https://{slug}.here.now/")
        print(f"  · slug={slug}")
        print(f"    URL: {url}")
        if info.get("expiresAt"):
            print(f"    expires: {info['expiresAt']}")
except Exception as e:
    print(f"  (could not read state file: {e})")
PYEOF
  if [ -f "$ENV_FILE" ] && grep -q '^DASHBOARD_PASSCODE=' "$ENV_FILE"; then
    PASS=$(grep '^DASHBOARD_PASSCODE=' "$ENV_FILE" | cut -d= -f2-)
    echo ""
    echo "  Passcode (from .env): $PASS"
  fi
else
  step "No local state file"
  echo "  This usually means: fresh workspace, or you're on a new laptop."
fi

# 2. Account API (only if creds + no state)
if [ ! -f "$STATE" ] && [ -f "$CRED_FILE" ]; then
  step "Looking up sites under your account on the publishing host"
  TOKEN=$(tr -d '[:space:]' < "$CRED_FILE")
  RESP=$(curl -fsS -H "Authorization: Bearer $TOKEN" \
    "https://here.now/api/v1/account/sites?limit=50" 2>&1) || RESP=""
  if [ -z "$RESP" ]; then
    printf '\033[33m  ⚠ couldn'"'"'t reach the host to list your sites\033[0m\n'
  else
    # The shape of /account/sites isn't documented in the public skill ref;
    # accept either {sites: [...]} or {publishes: [...]} for forward-compat.
    COUNT=$(echo "$RESP" | jq -r '(.sites // .publishes // []) | length' 2>/dev/null)
    if [ -z "$COUNT" ] || [ "$COUNT" = "0" ]; then
      echo "  No sites under your account on the host — nothing to recover."
    else
      echo "  Found $COUNT site(s) under your account:"
      echo "$RESP" | jq -r '(.sites // .publishes // [])[] | "    · slug=\(.slug // .name)  url=\(.siteUrl // ("https://" + (.slug // .name) + ".here.now/"))  expires=\(.expiresAt // "—")"' 2>/dev/null
      echo ""
      echo "  Tell me which slug to re-link to this workspace, then I'll restore it:"
      read -r -p "    Slug (or Enter to cancel): " PICK
      if [ -n "$PICK" ]; then
        URL="https://${PICK}.here.now/"
        printf '{"publishes":{"%s":{"siteUrl":"%s"}}}\n' "$PICK" "$URL" > "$STATE"
        echo "  ✓ Linked. Run 'refresh' to push your latest content to it."
      fi
    fi
  fi
fi

if [ ! -f "$STATE" ] && [ ! -f "$CRED_FILE" ]; then
  echo ""
  echo "  Without a local state file or host credentials, I can't find your"
  echo "  existing site automatically. Two options:"
  echo "    1. If you have your old workspace backup: 'restore from backup'."
  echo "    2. Ask your advisor — they can help locate it."
fi

echo ""
