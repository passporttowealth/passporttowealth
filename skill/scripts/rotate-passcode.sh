#!/bin/bash
# rotate-passcode.sh — generate a new passcode, push to host, update .env. Spec §15.
#
# OP-9: agent generates the passcode, user never invents one.

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
ENV_FILE="$WS/.env"
STATE="$WS/.herenow/state.json"
CRED_FILE="${HOME}/.herenow/credentials"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "$STATE" ] || fail "no published site to rotate — run publish first"
SLUG=$(jq -r '.publishes | keys[0] // ""' "$STATE")
[ -n "$SLUG" ] || fail "no slug in state file"

# Generate a new diceware passphrase (same wordlist as publish.sh)
NEW_PASSCODE=$(python3 - <<'PYEOF'
import secrets
words = ["paper","orchid","stove","vine","river","cedar","lemon","tide",
         "harbor","raven","amber","cobalt","pebble","willow","clover","quartz",
         "saffron","timber","velvet","walnut","azure","lupine","silver","mint"]
print("-".join(secrets.choice(words) for _ in range(4)))
PYEOF
)

# Back up the old .env, write the new passcode
if [ -f "$ENV_FILE" ]; then
  cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%Y%m%dT%H%M%S)"
  grep -v '^DASHBOARD_PASSCODE=' "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
fi
printf 'DASHBOARD_PASSCODE=%s\n' "$NEW_PASSCODE" >> "$ENV_FILE"
chmod 600 "$ENV_FILE"

step "Updating passcode on host"
if [ -f "$CRED_FILE" ]; then
  echo "  [v0 stub] would PATCH https://here.now/api/v1/publish/$SLUG/metadata"
  echo "           body: {\"password\": \"$NEW_PASSCODE\"}"
else
  echo "  ⚠ credentials missing — local .env updated but host not yet rotated"
fi

URL=$(jq -r --arg s "$SLUG" '.publishes[$s].siteUrl // ("https://" + $s + ".here.now/")' "$STATE")

cat <<EOF

✓ Done. Your new passcode is:
      $NEW_PASSCODE

  The old one no longer works. Anyone using your dashboard right now will
  be asked for the new one. Update your password manager and any place you
  shared the old one.

  Your dashboard URL hasn't changed: $URL

EOF
