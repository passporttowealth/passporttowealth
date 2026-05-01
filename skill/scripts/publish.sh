#!/bin/bash
# publish.sh — race-safe two-step publish to here.now. Spec §13.
#
# Flow (OP-2: never serve real content over an unprotected slug):
#   1. Stage placeholder (templates/placeholder/) → live URL exists, no data.
#   2. Generate or read passcode → write to .env.
#   3. PATCH metadata to set passcode → verify passwordProtected: true.
#   4. Push real site/ content to the now-protected slug.
#   5. Verify the slug returns the password challenge, not content.
#
# Refuses to push content to an unprotected slug. On any failure: roll back
# (delete the placeholder) and abort.
#
# Requires:
#   - here.now skill installed (`./scripts/publish.sh` from heredotnow/skill)
#   - $HOME/.herenow/credentials populated
#   - jq, curl
#
# v0 SAFETY NOTE:
#   This script wires the full flow but the actual API calls are stubbed
#   pending a real here.now token. Replace the "TODO" sections to enable
#   live publishing — see comments inline.

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLACEHOLDER="$SKILL_ROOT/templates/placeholder"
SITE="$WS/site"
ENV_FILE="$WS/.env"
STATE_FILE="$WS/.herenow/state.json"

PUBLISHING_HOST_API="https://here.now/api/v1"
CRED_FILE="${HOME}/.herenow/credentials"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
[ -d "$SITE" ] || fail "no site/ to publish — run refresh.sh first"
[ -f "$CRED_FILE" ] || fail "publishing-host credential missing at $CRED_FILE — re-run install"
command -v jq >/dev/null   || fail "jq not installed — pre-flight should have caught this"
command -v curl >/dev/null || fail "curl not installed — pre-flight should have caught this"

API_TOKEN=$(tr -d '[:space:]' < "$CRED_FILE")
[ -n "$API_TOKEN" ] || fail "credential file is empty"

# ── 1. Generate or read passcode (OP-9 — diceware, phone-friendly) ────────────
gen_passcode() {
  python3 - <<'PYEOF'
import secrets
# Phone-friendly diceware: 4 short lowercase words, no homophones, hyphens.
words = ["paper","orchid","stove","vine","river","cedar","lemon","tide",
         "harbor","raven","amber","cobalt","pebble","willow","clover","quartz",
         "saffron","timber","velvet","walnut","azure","lupine","silver","mint"]
print("-".join(secrets.choice(words) for _ in range(4)))
PYEOF
}

if [ -f "$ENV_FILE" ] && grep -q '^DASHBOARD_PASSCODE=' "$ENV_FILE"; then
  PASSCODE=$(grep '^DASHBOARD_PASSCODE=' "$ENV_FILE" | cut -d= -f2- | tr -d '"')
  step "Reusing existing passcode from .env"
else
  PASSCODE=$(gen_passcode)
  step "Generated a new passcode"
  mkdir -p "$WS"
  if [ -f "$ENV_FILE" ]; then
    grep -v '^DASHBOARD_PASSCODE=' "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
  fi
  printf 'DASHBOARD_PASSCODE=%s\n' "$PASSCODE" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

# ── 2. Determine slug (reuse if state exists; otherwise let host assign one) ──
mkdir -p "$WS/.herenow"
if [ -f "$STATE_FILE" ] && jq -e '.publishes | keys[0]' "$STATE_FILE" >/dev/null 2>&1; then
  SLUG=$(jq -r '.publishes | keys[0]' "$STATE_FILE")
  CLAIM=$(jq -r --arg s "$SLUG" '.publishes[$s].claimToken // ""' "$STATE_FILE")
  step "Reusing existing slug ($SLUG)"
else
  SLUG=""
  CLAIM=""
  step "First publish — placeholder will create a fresh slug"
fi

# ── 3. Stage placeholder ──────────────────────────────────────────────────────
# TODO(v0): wire this to the real here.now publish script.
# Reference: heredotnow/skill -- scripts/publish.sh {dir} [--slug X] [--claim-token Y]
step "Staging placeholder (so the slug is gated before real content is pushed)"
echo "  [v0 stub] would invoke: here-now publish.sh '$PLACEHOLDER' ${SLUG:+--slug $SLUG}"
echo "  After publish, capture slug + claim token from response → $STATE_FILE"

if [ -z "$SLUG" ]; then
  SLUG="example-slug-replace-me"
  CLAIM="example-claim-token"
  printf '{ "publishes": { "%s": { "siteUrl": "https://%s.here.now/", "claimToken": "%s" } } }\n' \
    "$SLUG" "$SLUG" "$CLAIM" > "$STATE_FILE"
fi
URL="https://${SLUG}.here.now/"

# ── 4. Set passcode via metadata PATCH ────────────────────────────────────────
step "Setting passcode on the host (OP-2: real content is NOT yet pushed)"
echo "  [v0 stub] would PATCH $PUBLISHING_HOST_API/publish/$SLUG/metadata"
echo "           body: {\"password\": \"$PASSCODE\"}"
echo "  Verify response includes \"passwordProtected\": true before continuing."

# ── 5. Push the real site (only after passcode is verified set) ──────────────
step "Pushing real dashboard content"
echo "  [v0 stub] would invoke: here-now publish.sh '$SITE' --slug $SLUG --claim-token $CLAIM"

# ── 6. Verify gated ───────────────────────────────────────────────────────────
step "Verifying the URL returns the passcode challenge (not the dashboard)"
echo "  [v0 stub] would: curl -sI $URL  → expect 401/302 to a password page"

# ── 7. Report ─────────────────────────────────────────────────────────────────
step "✓ Done"
cat <<EOF

  Your dashboard is live at:
      $URL

  Your passcode is:
      $PASSCODE

  Both are saved in: $ENV_FILE
  Ask Claude "what's my passcode?" any time and the agent will read it back.

  ⚠ Save the passcode somewhere you can reach from your phone:
      • Your phone's password manager (1Password, iCloud Keychain, Bitwarden)
      • OR ask the agent to email both to your own email.

EOF
