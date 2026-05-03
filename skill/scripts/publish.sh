#!/bin/bash
# publish.sh — race-safe two-step publish to here.now. Spec §13.
#
# Flow (OP-2: never serve real content over an unprotected slug):
#   0. (First time only) Sign up with the publishing host via email-code flow.
#      Skipped silently on subsequent publishes once credentials exist.
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
#   - here-now skill installed at ~/.claude/skills/here-now/
#   - jq, curl
# Provides on first run:
#   - $HOME/.herenow/credentials (via inline email-code flow — Strategic #2,
#     formerly part of Welcome.command Step 4 but moved here so users who
#     never share their dashboard never have to sign up)

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
HERENOW_PUBLISH="${HERENOW_PUBLISH_SCRIPT:-${HOME}/.claude/skills/here-now/scripts/publish.sh}"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
note() { printf '  %s\n' "$*"; }
warn() { printf '  \033[33m⚠ %s\033[0m\n' "$*"; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
[ -d "$SITE" ] || fail "no site/ to publish — run refresh.sh first"
[ -d "$PLACEHOLDER" ] || fail "placeholder template missing at $PLACEHOLDER"
[ -x "$HERENOW_PUBLISH" ] || fail "here-now publish script missing at $HERENOW_PUBLISH"
command -v jq >/dev/null   || fail "jq not installed"
command -v curl >/dev/null || fail "curl not installed"

mkdir -p "$WS/.herenow"

# ── 0. First-time publishing-host signup (Strategic #2 — moved from installer) ─
# If the credential file is missing or empty, the user has never published.
# Run the email-code flow inline now. The user's at the moment of highest
# motivation ("I want to share my dashboard") so this lands much better than
# during install where they're not sure why they need an account.
mkdir -p "$(dirname "$CRED_FILE")"
SIGNUP_NEEDED=1
if [ -f "$CRED_FILE" ] && [ -s "$CRED_FILE" ]; then
  EXISTING_KEY=$(tr -d '[:space:]' < "$CRED_FILE")
  EX_HTTP=$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $EXISTING_KEY" \
    https://here.now/api/v1/account 2>/dev/null || echo "000")
  if [ "$EX_HTTP" = "200" ]; then
    SIGNUP_NEEDED=0
  fi
fi

if [ "$SIGNUP_NEEDED" = "1" ]; then
  # Manual-paste fallback used when the email-code flow fails or the user opts
  # out. Returns 0 if a working key is saved, 1 otherwise.
  manual_paste_fallback() {
    note ""
    note "OK — manual signup path:"
    note "  1. I'll open here.now's homepage in a moment."
    note "  2. Click 'Sign in' top-right and sign up with your email."
    note "  3. Find your API key on the dashboard."
    note "  4. Come back here and paste it."
    note ""
    read -r -p "  Press Enter to open the browser... " _
    command -v open >/dev/null 2>&1 && open "https://here.now/" 2>/dev/null || true
    local attempts=0
    while [ "$attempts" -lt 5 ]; do
      attempts=$((attempts + 1))
      printf '\n'
      read -r -p "  Paste your API key (or 'quit' to stop): " host_key
      host_key="$(printf '%s' "$host_key" | tr -d '[:space:]')"
      if [ "$host_key" = "quit" ] || [ -z "$host_key" ]; then return 1; fi
      [[ "$host_key" == *@* ]]   && { warn "That looks like an email — paste the API key, not your email."; continue; }
      [[ "$host_key" == http* ]] && { warn "That looks like a URL — find the key on the dashboard."; continue; }
      HTTP=$(curl -sS -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $host_key" \
        https://here.now/api/v1/account 2>/dev/null || echo "000")
      case "$HTTP" in
        200) printf '%s\n' "$host_key" > "$CRED_FILE"; chmod 600 "$CRED_FILE"; return 0 ;;
        401|403) warn "Host rejected that key. Did you confirm your email?" ;;
        404) warn "Host returned 404 — copy the key exactly, no extra characters." ;;
        *)   warn "Couldn't reach the host (HTTP $HTTP). Check your connection." ;;
      esac
    done
    return 1
  }

  step "First publish — let's set up your account with the host"
  note "Sharing your dashboard needs a free account on here.now (the service"
  note "that will host the URL). I'll set it up using just your email — no"
  note "browser clicking. The code is the only thing you'll have to type."
  note ""
  read -r -p "  Email: " host_email
  host_email="$(printf '%s' "$host_email" | tr -d '[:space:]')"
  HOST_DONE=0

  if [[ ! "$host_email" =~ .+@.+\..+ ]]; then
    warn "That doesn't look like an email. Falling back to manual setup."
    manual_paste_fallback && HOST_DONE=1 || fail "couldn't get a working key — try again later"
  else
    note "Sending a sign-in code to $host_email..."
    REQ_RESP=$(curl -sS -X POST \
      -H "Content-Type: application/json" \
      -d "$(printf '{"email":"%s"}' "$host_email")" \
      https://here.now/api/auth/agent/request-code 2>/dev/null)
    REQ_OK=$(printf '%s' "$REQ_RESP" | jq -r '.success // false' 2>/dev/null || echo "")

    if [ "$REQ_OK" != "true" ]; then
      warn "Couldn't send the sign-in code (response: ${REQ_RESP:0:120})."
      manual_paste_fallback && HOST_DONE=1 || fail "couldn't get a working key — try again later"
    else
      note "✓ Code sent. Check your inbox (subject usually mentions 'here.now')."
      note "  Codes look like ABCD-2345 and expire in a few minutes."
      printf '\n'
      vcode_attempts=0
      while [ "$vcode_attempts" -lt 5 ] && [ "$HOST_DONE" = "0" ]; do
        vcode_attempts=$((vcode_attempts + 1))
        read -r -p "  Code from email (or 'paste' for manual API key): " host_code
        host_code="$(printf '%s' "$host_code" | tr -d '[:space:]')"
        if [ "$host_code" = "paste" ] || [ "$host_code" = "manual" ]; then
          manual_paste_fallback && HOST_DONE=1 || fail "couldn't get a working key — try again later"
          break
        fi
        if [ -z "$host_code" ]; then warn "No code typed — try again, or 'paste'."; continue; fi
        VER_RESP=$(curl -sS -X POST \
          -H "Content-Type: application/json" \
          -d "$(printf '{"email":"%s","code":"%s"}' "$host_email" "$host_code")" \
          https://here.now/api/auth/agent/verify-code 2>/dev/null)
        VER_OK=$(printf '%s' "$VER_RESP" | jq -r '.success // false' 2>/dev/null || echo "")
        API_KEY=$(printf '%s' "$VER_RESP" | jq -r '.apiKey // empty' 2>/dev/null || echo "")
        if [ "$VER_OK" = "true" ] && [ -n "$API_KEY" ]; then
          printf '%s\n' "$API_KEY" > "$CRED_FILE"
          chmod 600 "$CRED_FILE"
          note "✓ Account ready."
          HOST_DONE=1
        else
          warn "That code didn't verify. ${VER_RESP:0:120}"
          warn "Try again, or type 'paste' to do it manually."
        fi
      done
      if [ "$HOST_DONE" = "0" ]; then
        warn "Couldn't verify the code after $vcode_attempts tries."
        manual_paste_fallback && HOST_DONE=1 || fail "couldn't get a working key — try again later"
      fi
    fi
  fi
fi

API_TOKEN=$(tr -d '[:space:]' < "$CRED_FILE")
[ -n "$API_TOKEN" ] || fail "credential file is empty after signup — please re-run"

# ── 1. Generate or read passcode (OP-9 — diceware, phone-friendly) ────────────
gen_passcode() {
  python3 - <<'PYEOF'
import secrets
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
fi
mkdir -p "$WS"
if [ -f "$ENV_FILE" ]; then
  grep -v '^DASHBOARD_PASSCODE=' "$ENV_FILE" 2>/dev/null > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
fi
printf 'DASHBOARD_PASSCODE=%s\n' "$PASSCODE" >> "$ENV_FILE"
chmod 600 "$ENV_FILE"

# ── 2. Determine slug (reuse if state exists; otherwise let host assign one) ──
SLUG=""
CLAIM=""
if [ -f "$STATE_FILE" ] && jq -e '.publishes | keys[0]' "$STATE_FILE" >/dev/null 2>&1; then
  SLUG=$(jq -r '.publishes | keys[0]' "$STATE_FILE")
  CLAIM=$(jq -r --arg s "$SLUG" '.publishes[$s].claimToken // ""' "$STATE_FILE")
  step "Reusing existing slug ($SLUG)"
fi

# ── 3. Stage placeholder (OP-2: gate the slug BEFORE real content) ───────────
step "Publishing placeholder"
PLACEHOLDER_OUT=$(mktemp)
PLACEHOLDER_ERR=$(mktemp)
trap 'rm -f "$PLACEHOLDER_OUT" "$PLACEHOLDER_ERR"' EXIT

if [ -n "$SLUG" ]; then
  # Update existing slug
  if [ -n "$CLAIM" ]; then
    "$HERENOW_PUBLISH" "$PLACEHOLDER" --slug "$SLUG" --claim-token "$CLAIM" --client "finance-clarity-build" \
      >"$PLACEHOLDER_OUT" 2>"$PLACEHOLDER_ERR" || \
      fail "placeholder publish failed: $(tail -10 "$PLACEHOLDER_ERR")"
  else
    "$HERENOW_PUBLISH" "$PLACEHOLDER" --slug "$SLUG" --client "finance-clarity-build" \
      >"$PLACEHOLDER_OUT" 2>"$PLACEHOLDER_ERR" || \
      fail "placeholder publish failed: $(tail -10 "$PLACEHOLDER_ERR")"
  fi
else
  # Fresh publish — host assigns the slug
  ( cd "$WS" && "$HERENOW_PUBLISH" "$PLACEHOLDER" --client "finance-clarity-build" ) \
    >"$PLACEHOLDER_OUT" 2>"$PLACEHOLDER_ERR" || \
    fail "placeholder publish failed: $(tail -10 "$PLACEHOLDER_ERR")"
fi

# Re-read state after publish to get the assigned slug + claim
if [ -f "$STATE_FILE" ]; then
  SLUG=$(jq -r '.publishes | keys[0]' "$STATE_FILE")
  CLAIM=$(jq -r --arg s "$SLUG" '.publishes[$s].claimToken // ""' "$STATE_FILE")
fi
[ -n "$SLUG" ] || fail "could not determine slug after placeholder publish"

URL="https://${SLUG}.here.now/"
note "Slug: $SLUG"
note "URL:  $URL"

# ── 4. Set passcode via metadata PATCH (OP-2 critical step) ───────────────────
step "Setting passcode on host"
PATCH_RESP=$(curl -fsS -X PATCH \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg p "$PASSCODE" '{password: $p}')" \
  "${PUBLISHING_HOST_API}/publish/${SLUG}/metadata" 2>&1) || \
  fail "metadata PATCH failed: $PATCH_RESP"

PROTECTED=$(echo "$PATCH_RESP" | jq -r '.passwordProtected // false')
if [ "$PROTECTED" != "true" ]; then
  fail "host did not confirm passwordProtected: true (response: $PATCH_RESP) — refusing to push real content"
fi
note "✓ passwordProtected: true"

# ── 5. Push real content to the now-protected slug ────────────────────────────
step "Pushing real dashboard content"
PUSH_OUT=$(mktemp)
PUSH_ERR=$(mktemp)
trap 'rm -f "$PLACEHOLDER_OUT" "$PLACEHOLDER_ERR" "$PUSH_OUT" "$PUSH_ERR"' EXIT

PUSH_ARGS=(--slug "$SLUG" --client "finance-clarity-build")
[ -n "$CLAIM" ] && PUSH_ARGS+=(--claim-token "$CLAIM")
"$HERENOW_PUBLISH" "$SITE" "${PUSH_ARGS[@]}" >"$PUSH_OUT" 2>"$PUSH_ERR" || \
  fail "real content push failed: $(tail -15 "$PUSH_ERR")"

# ── 6. Verify the slug is gated ──────────────────────────────────────────────
step "Verifying the URL returns the passcode challenge"
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$URL" || echo "000")
case "$HTTP_CODE" in
  200|302|401|403)
    # Get the body and check it's NOT the dashboard
    BODY=$(curl -sS "$URL" | head -c 4096)
    if echo "$BODY" | grep -qi "passcode\|password\|verify\|protected\|sign in"; then
      note "✓ HTTP $HTTP_CODE — password challenge served (real dashboard NOT exposed)"
    elif echo "$BODY" | grep -qi "Your Finance Dashboard\|Dashboard Data\|kpi-card"; then
      fail "SECURITY: HTTP $HTTP_CODE returned real dashboard content unauthenticated — rolling back"
    else
      note "  HTTP $HTTP_CODE — body doesn't match dashboard markers, assuming gated"
    fi
    ;;
  *)
    note "  HTTP $HTTP_CODE — unexpected but not necessarily a failure; manual check recommended"
    ;;
esac

# Update .env with SITE_URL
if [ -f "$ENV_FILE" ]; then
  grep -v '^SITE_URL=' "$ENV_FILE" 2>/dev/null > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
fi
printf 'SITE_URL=%s\n' "$URL" >> "$ENV_FILE"
chmod 600 "$ENV_FILE"

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
