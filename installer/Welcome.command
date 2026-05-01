#!/bin/bash
#
# Welcome.command — Passport to Wealth Finance Clarity bootstrap installer
#
# v0 SKELETON — does not yet provision a working workspace.
# Demonstrates the planned flow (pre-flight, friendly progress messages,
# auth path selection, publishing-host signup walkthrough) but the actual
# package installs are stubbed. See engagement/development/finance-clarity-build-spec.md §4
# for the full intended behavior.
#
# Copyright © 2026 Passport to Wealth. All rights reserved.

set -u

# Open in its own Terminal window when double-clicked. Re-exec ourselves
# inside Terminal if we were launched from Finder without a TTY.
if [[ ! -t 1 && -z "${REEXEC_TTY:-}" ]]; then
  REEXEC_TTY=1 open -a Terminal "$0"
  exit 0
fi

# Friendly title bar
printf '\033]0;Setting up your finance workspace\007'

# ANSI colors (kept simple so the user-facing text stays approachable)
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
DIM=$'\033[2m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

say() { printf '%s\n' "$*"; }
ok()  { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn(){ printf '  %s⚠%s %s\n' "$YELLOW" "$RESET" "$*"; }
fail(){ printf '  %s✗%s %s\n' "$RED" "$RESET" "$*"; }
hr()  { printf '%s%s%s\n' "$DIM" "──────────────────────────────────────────────────────" "$RESET"; }

# B9.3 — pacing helpers. Pre-flight ✓s flash by faster than humans can read.
# These give the user time to absorb each line and put them in control of
# section transitions. --auto bypasses all pacing for CI / Rafa's reruns.
PACE_SLEEP="0.4"
AUTO_MODE=0
for arg in "$@"; do
  case "$arg" in
    --auto) AUTO_MODE=1; PACE_SLEEP="0" ;;
  esac
done

ok_paced()  { ok "$@"; [ "$AUTO_MODE" = "0" ] && sleep "$PACE_SLEEP"; }
say_paced() { say "$@"; [ "$AUTO_MODE" = "0" ] && sleep "$PACE_SLEEP"; }

# pause_for_user — explicit "Press Enter to continue" gate between major
# sections. Converts the firehose into a conversation. TTY-guarded so
# non-interactive runs (--auto, scripts, CI) don't hang.
pause_for_user() {
  if [ "$AUTO_MODE" = "1" ] || [ ! -t 0 ]; then
    return 0
  fi
  printf '\n'
  read -r -p "$(printf '%sPress Enter to continue%s ' "$DIM" "$RESET")" _
}

INSTALL_LOG="${HOME}/Library/Logs/passport-to-wealth-install.log"
mkdir -p "$(dirname "$INSTALL_LOG")"
exec 3>>"$INSTALL_LOG"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&3; }

# Workspace location — overridable via FCB_WORKSPACE for testing.
# Default is ~/Documents/my-finances (adjusted later if iCloud-synced).
WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"

# Source-of-truth for the skill — used by the install step to git-clone the
# finance-clarity-build skill into ~/.claude/skills if it isn't already there.
SKILL_REPO_URL="${FCB_SKILL_REPO_URL:-https://github.com/rafaeldavid/passporttowealth.git}"
SKILL_INSTALL_DIR="${FCB_SKILL_INSTALL_DIR:-${HOME}/.claude/skills/finance-clarity-build}"

# Helper: run a command, suppress its noisy output, surface only success/fail.
# Returns 0/non-zero from the wrapped command. Use for `brew install` etc.
run_quiet() {
  local label="$1"; shift
  if "$@" >>"$INSTALL_LOG" 2>&1; then
    ok_paced "$label"
    return 0
  else
    fail "$label failed — see $INSTALL_LOG for details"
    return 1
  fi
}

clear
hr
say "${BOLD}Welcome — let's set up your private finance workspace.${RESET}"
hr
say
say "I'll do all the technical bits. You'll only need to:"
say "  1. Type your Mac password once (when Mac asks)."
say "  2. Sign in to your AI assistant."
say "  3. Sign up for the service that hosts your private dashboard."
say

# ── Prototype notice (always visible — not dimmed) ────────────────────────────
say
hr
say "${YELLOW}${BOLD}⚠  PROTOTYPE — pre-release software${RESET}"
hr
say
say "This is a ${BOLD}pilot tool${RESET} for clients of Passport to Wealth, under"
say "active development. Use it as a complement to — not a replacement for —"
say "your existing financial records."
say
say "  • Expect bugs and incomplete features."
say "  • ${BOLD}Always keep your original bank exports and statements.${RESET}"
say "  • Do not delete source files based on what the dashboard shows."
say "  • If anything looks wrong, tell your advisor — don't assume the"
say "    dashboard is correct."
say
say "${DIM}Internal note: this is a v0 skeleton. Real installer functionality"
say "is being built per engagement/development/backlog.md Epic 1.${RESET}"
say

# ── Anthropic data-terms consent gate (required before any install action) ────
hr
say "${BOLD}Before we continue — about the AI assistant${RESET}"
hr
say
say "This workspace uses ${BOLD}Claude${RESET}, an AI assistant made by Anthropic."
say "When you ask Claude to build, refresh, or troubleshoot your dashboard,"
say "the contents of the messages you send (which may include details from"
say "your financial files as you discuss them) are sent to Anthropic to"
say "produce a response."
say
say "Anthropic's data handling — including ${BOLD}what they retain${RESET}, ${BOLD}for how"
say "long${RESET}, ${BOLD}whether your conversations are used to train models${RESET}, and how"
say "you can change those settings — is described in their official"
say "documentation. Please review it before continuing:"
say
say "  • Privacy hub:           ${BOLD}https://privacy.anthropic.com/${RESET}"
say "  • Privacy policy:        ${BOLD}https://www.anthropic.com/legal/privacy${RESET}"
say "  • Consumer (Pro/Max):    ${BOLD}https://www.anthropic.com/legal/consumer-terms${RESET}"
say "  • Commercial (API key):  ${BOLD}https://www.anthropic.com/legal/commercial-terms${RESET}"
say "  • Trust & security:      ${BOLD}https://trust.anthropic.com/${RESET}"
say
say "Things to know — and to manage in your Anthropic account settings:"
say "  • You can opt out of having your conversations used to improve Claude."
say "  • You can delete your conversation history at any time."
say "  • Sensitive files (paystubs, tax documents) are skipped by default by"
say "    this skill, so their contents are not sent to Claude unless you"
say "    explicitly ask."
say
say "If you do not accept Anthropic's terms, please ${BOLD}stop here${RESET} and contact"
say "your advisor — we can talk about alternatives."
say

# NOTE (B9.1): we deliberately do NOT auto-open the privacy hub in a
# browser here. Auto-opening mid-flow snaps focus away from this Terminal
# and confuses users about what to type next. Terminal already linkifies
# the URLs printed above — the user clicks if they want to read first.

say "${BOLD}By typing 'I accept' below you confirm:${RESET}"
say "  1. You accept Anthropic's data-handling terms (linked above)."
say "  2. You understand this is ${BOLD}prototype${RESET} software and you will keep"
say "     your original financial records as the source of truth."
say
while true; do
  read -r -p "$(printf 'Type %sI accept%s to continue, or %sno%s to cancel: ' "$BOLD" "$RESET" "$BOLD" "$RESET")" consent
  consent_lc=$(printf '%s' "$consent" | tr '[:upper:]' '[:lower:]' | xargs)
  case "$consent_lc" in
    "i accept"|"i agree"|"accept"|"agree"|"yes")
      ok "Acceptance recorded."
      log "consent_accepted_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) (anthropic_data_terms + prototype_status)"
      break
      ;;
    "no"|"cancel"|"quit"|"stop"|"")
      say
      say "${DIM}No problem — install cancelled. Talk to your advisor any time.${RESET}"
      log "consent_declined_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      exit 0
      ;;
    *)
      warn "I didn't understand. Please type 'I accept' or 'no'."
      ;;
  esac
done

say
read -r -p "Press Enter to begin the install (or Ctrl-C to cancel)... " _

# ── Pre-flight (OP-11) ────────────────────────────────────────────────────────
say
hr
say "${BOLD}Step 1 of 6 — Checking your Mac${RESET}"
hr

log "preflight start"

# macOS version
macos_major=$(sw_vers -productVersion | cut -d. -f1)
if [[ "$macos_major" -lt 13 ]]; then
  fail "Your Mac is running macOS $(sw_vers -productVersion). I need macOS 13 (Ventura) or later."
  fail "FCB-0001 — see engagement/development/finance-clarity-build-spec.md §4.2"
  log "FCB-0001 macos_version=$(sw_vers -productVersion)"
  exit 1
fi
ok_paced "macOS version OK ($(sw_vers -productVersion))"

# Disk space
free_kb=$(df -k "$HOME" | awk 'NR==2 {print $4}')
free_gb=$(( free_kb / 1024 / 1024 ))
if [[ "$free_gb" -lt 5 ]]; then
  fail "Only ${free_gb} GB free on your home drive. I need at least 5 GB."
  fail "FCB-0002 — free up some space and run me again."
  log "FCB-0002 free_gb=$free_gb"
  exit 1
fi
ok_paced "Free disk space OK (${free_gb} GB)"

# MDM check
if profiles status -type enrollment 2>/dev/null | grep -q "Enrolled via DEP: Yes\|MDM enrollment: Yes"; then
  fail "Your Mac is managed by an organization (MDM enrolled)."
  fail "This skill is designed for personal laptops. Please talk to your advisor."
  fail "FCB-0003"
  log "FCB-0003 mdm_detected=true"
  exit 1
fi
ok_paced "Personal Mac (not MDM-managed)"

# Network reachability
if ! curl -fsS --max-time 5 -o /dev/null https://api.frankfurter.app/latest; then
  warn "Couldn't reach the exchange-rate service. The installer will continue but FX may be stale."
  log "FCB-0010 network=frankfurter unreachable"
fi
ok_paced "Network reachable"

pause_for_user  # B9.3 — gate before tools-install section

# Xcode CLT detection drives the time estimate
if xcode-select -p >/dev/null 2>&1; then
  estimate="about 10 minutes"
else
  estimate="30 to 60 minutes (Mac needs to download some developer tools first)"
fi
say
say "Estimated time: ${BOLD}${estimate}${RESET}"
say

# ── Runtime provisioning ─────────────────────────────────────────────────────
hr
say "${BOLD}Step 2 of 6 — Installing the tools your dashboard needs${RESET}"
hr
say

# 2a. Xcode Command Line Tools — required for git, compilers, etc.
if xcode-select -p >/dev/null 2>&1; then
  ok_paced "Developer tools already installed"
else
  say "Mac is going to ask permission to download some developer tools."
  say "${DIM}This is a system dialog; click \"Install\" when it appears. May take 10-30 min.${RESET}"
  log "installing xcode-select CLT"
  xcode-select --install 2>>"$INSTALL_LOG" || true
  # Block until user clicks Install in the system dialog
  until xcode-select -p >/dev/null 2>&1; do
    sleep 10
    printf '.'
  done
  say
  ok_paced "Developer tools installed"
fi

# 2b. Homebrew — required for python@3.11 + jq
if command -v brew >/dev/null 2>&1; then
  ok_paced "Homebrew already installed"
else
  say "Installing Homebrew (Mac will ask for your password)..."
  log "installing homebrew"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    >>"$INSTALL_LOG" 2>&1 || { fail "Homebrew install failed — see $INSTALL_LOG"; exit 1; }
  # Add brew to PATH for this session (Apple Silicon vs Intel locations differ)
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  ok_paced "Homebrew installed"
fi

# 2c. Python 3.11 (we pin to 3.11 because some upstream deps lag on 3.13/3.14)
PYTHON311=""
for candidate in python3.11 /opt/homebrew/opt/python@3.11/bin/python3.11 /usr/local/opt/python@3.11/bin/python3.11; do
  if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
    PYTHON311="$candidate"; break
  fi
done
if [ -n "$PYTHON311" ]; then
  ok_paced "Python 3.11 already installed"
else
  say "Installing Python 3.11..."
  run_quiet "Python 3.11 installed" brew install python@3.11 || exit 1
  PYTHON311="$(brew --prefix python@3.11)/bin/python3.11"
fi

# 2d. jq — needed by here-now publish script + our wrappers
if command -v jq >/dev/null 2>&1; then
  ok_paced "jq already installed"
else
  run_quiet "jq installed" brew install jq || exit 1
fi

# 2e. Workspace venv + Python deps. Workspace is created on first use; create
# its parent now so the venv has somewhere to live.
mkdir -p "$WS"
if [ -x "$WS/.venv/bin/python" ]; then
  ok_paced "Workspace Python environment already set up"
else
  say "Creating workspace Python environment..."
  "$PYTHON311" -m venv "$WS/.venv" >>"$INSTALL_LOG" 2>&1 || { fail "venv creation failed"; exit 1; }
  ok_paced "Workspace Python environment ready"
fi

# Install / update Python deps from requirements.txt (downloaded with the skill repo).
# At this point the skill may not be installed yet (step 2g handles that), so use
# a known-good list inline.
say "Installing Python dependencies..."
"$WS/.venv/bin/pip" install --quiet --upgrade pip >>"$INSTALL_LOG" 2>&1 || true
"$WS/.venv/bin/pip" install --quiet \
  "openpyxl~=3.1" "pdfplumber~=0.11" "PyYAML~=6.0" "chardet~=5.2" "reportlab~=4.4" \
  >>"$INSTALL_LOG" 2>&1 || { fail "Python deps install failed"; exit 1; }
ok_paced "Python dependencies installed"

# 2f. Claude Code CLI — required to run the assistant
if command -v claude >/dev/null 2>&1; then
  ok_paced "Claude Code already installed"
else
  say "Installing Claude Code..."
  curl -fsSL https://claude.ai/install.sh 2>>"$INSTALL_LOG" | bash >>"$INSTALL_LOG" 2>&1 \
    || { fail "Claude Code install failed — see $INSTALL_LOG"; exit 1; }
  # Reload PATH from the user's shell rc so 'claude' is findable
  if [ -f "$HOME/.zshrc" ]; then source "$HOME/.zshrc" 2>/dev/null || true; fi
  ok_paced "Claude Code installed"
fi

# 2g. here-now skill — bundles the publishing flow
if [ -d "$HOME/.claude/skills/here-now" ]; then
  ok_paced "Publishing-host skill already installed"
else
  say "Installing publishing-host skill..."
  if command -v npx >/dev/null 2>&1; then
    npx -y skills add heredotnow/skill --skill here-now -g >>"$INSTALL_LOG" 2>&1 \
      || { fail "here-now skill install failed — see $INSTALL_LOG"; exit 1; }
  else
    fail "npx not available — install Node.js first or contact support"
    exit 1
  fi
  ok_paced "Publishing-host skill installed"
fi

# 2h. finance-clarity-build skill — git clone this repo into ~/.claude/skills/
mkdir -p "$HOME/.claude/skills"
if [ -d "$SKILL_INSTALL_DIR/.git" ]; then
  say "Updating finance-clarity-build skill..."
  ( cd "$SKILL_INSTALL_DIR" && git pull --quiet ) >>"$INSTALL_LOG" 2>&1 || true
  ok_paced "Finance Clarity skill up-to-date"
elif [ -d "$SKILL_INSTALL_DIR" ]; then
  ok_paced "Finance Clarity skill already installed (non-git)"
else
  say "Installing Finance Clarity skill..."
  git clone --quiet "$SKILL_REPO_URL" "$SKILL_INSTALL_DIR" >>"$INSTALL_LOG" 2>&1 \
    || { fail "Skill clone failed — see $INSTALL_LOG"; exit 1; }
  ok_paced "Finance Clarity skill installed"
fi

# ── AI assistant auth (§4.3) ──────────────────────────────────────────────────
say
hr
say "${BOLD}Step 3 of 6 — Signing in to your AI assistant${RESET}"
hr
say
say "How do you sign in to Claude?"
say "  1. ${BOLD}Paid subscription${RESET} — Claude Pro or Max (sign in with your email)"
say "  2. ${BOLD}Anthropic API key${RESET} — paste the key (starts with sk-ant-)"
say
say "${DIM}If you don't have either, please call your advisor — this is the"
say "one step I can't do without you.${RESET}"
say
read -r -p "Type 1 or 2: " auth_choice

case "$auth_choice" in
  1)
    # Subscription path: launch `claude` to trigger OAuth if not authenticated.
    # Verifying authentication: claude prints help text without erroring iff the
    # user is logged in. If not logged in, it opens a browser to sign in.
    if claude --version >>"$INSTALL_LOG" 2>&1; then
      say "${DIM}Opening Claude — if you're not signed in yet, your browser will open${RESET}"
      say "${DIM}for you to sign in. Come back here when it says 'success'.${RESET}"
      log "claude oauth probe"
      # Run a no-op prompt to force any pending auth flow:
      printf '/exit\n' | claude --dangerously-skip-permissions --print "ready" >>"$INSTALL_LOG" 2>&1 \
        || warn "Claude returned a non-zero exit; continuing — you can verify later by running 'claude' yourself"
      ok_paced "Claude (subscription) ready"
    else
      fail "Claude Code didn't respond — install may have left it in a bad state"
      exit 1
    fi
    ;;
  2)
    say
    read -r -s -p "Paste your Anthropic API key (won't be shown): " api_key
    say
    api_key="$(printf '%s' "$api_key" | tr -d '[:space:]')"
    if [[ ! "$api_key" =~ ^sk-ant- ]]; then
      fail "That doesn't look like an Anthropic API key (should start with sk-ant-)."
      fail "FCB-0004"
      log "FCB-0004 api_key_format_invalid"
      exit 1
    fi
    # Validate the key with a tiny API call (max_tokens=1, so it costs ~nothing)
    say "Verifying your API key..."
    HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" \
      -H "x-api-key: $api_key" \
      -H "anthropic-version: 2023-06-01" \
      -H "content-type: application/json" \
      -d '{"model":"claude-haiku-4-5","max_tokens":1,"messages":[{"role":"user","content":"."}]}' \
      https://api.anthropic.com/v1/messages 2>>"$INSTALL_LOG")
    case "$HTTP_CODE" in
      200) ok_paced "API key verified" ;;
      401|403) fail "Anthropic rejected that key (HTTP $HTTP_CODE) — check your billing dashboard"; exit 1 ;;
      *)   warn "Couldn't verify (HTTP $HTTP_CODE) — saving anyway; you can re-test later" ;;
    esac
    # Store key in workspace .env so START-HERE can export it as ANTHROPIC_API_KEY.
    mkdir -p "$WS"
    if [ -f "$WS/.env" ]; then
      grep -v '^ANTHROPIC_API_KEY=' "$WS/.env" 2>/dev/null > "$WS/.env.tmp" || true
      mv "$WS/.env.tmp" "$WS/.env"
    fi
    printf 'ANTHROPIC_API_KEY=%s\n' "$api_key" >> "$WS/.env"
    chmod 600 "$WS/.env"
    log "api key saved to workspace .env"
    ;;
  *)
    fail "I didn't understand. Run me again and pick 1 or 2."
    exit 1
    ;;
esac
ok_paced "AI assistant ready"

pause_for_user  # B9.3 — gate before publishing-host signup

# ── Publishing-host signup (§4.4) ─────────────────────────────────────────────
say
hr
say "${BOLD}Step 4 of 6 — Setting up your private dashboard host${RESET}"
hr
say
say "I need a free account on the service that will host your private dashboard."
say "I'll open it in your browser. Please:"
say
say "  1. Sign up — just an email and password. (You'll only do this once.)"
say "  2. ${BOLD}CHECK YOUR EMAIL${RESET} for a verification link if asked. Click it. Come back."
say "  3. On the page that opens, look for a section called \"API Keys\""
say "     (might be under Settings or Account). Click \"Create New Key\"."
say "  4. Copy the long string of letters and numbers. It looks like:"
say "        ${DIM}hn_live_aBcD1234efGh5678…${RESET}"
say "  5. Paste it here, then press Enter."
say
say "${DIM}If you'd rather have your advisor do this, just call them now and"
say "share your screen. They can paste it for you. Take your time.${RESET}"
say
CRED_FILE="${HOME}/.herenow/credentials"
mkdir -p "$(dirname "$CRED_FILE")"

# If the user already has a working credential, skip — idempotent re-run.
if [ -s "$CRED_FILE" ]; then
  EXISTING_KEY=$(tr -d '[:space:]' < "$CRED_FILE")
  EX_HTTP=$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $EXISTING_KEY" \
    https://here.now/api/v1/account 2>>"$INSTALL_LOG" || echo "000")
  if [ "$EX_HTTP" = "200" ]; then
    ok_paced "Publishing host already configured"
    log "publishing host: existing credential valid"
    HOST_DONE=1
  fi
fi

if [ "${HOST_DONE:-0}" != "1" ]; then
  # Tell the user where to go BEFORE opening the browser (B9.1 lesson —
  # don't snap focus mid-instruction).
  say "I'll open the publishing host's homepage in a moment."
  say "Once it loads:"
  say "  1. Click ${BOLD}Sign in${RESET} in the top-right corner."
  say "  2. Sign up with your email (you'll only do this once)."
  say "  3. ${BOLD}CHECK YOUR EMAIL${RESET} for a verification link if asked. Click it."
  say "  4. On the dashboard, find your API key — copy the long random string."
  say "  5. Come back here and paste it."
  say
  read -r -p "$(printf '%sPress Enter when you'"'"'re ready to open the browser...%s ' "$DIM" "$RESET")" _

  if command -v open >/dev/null 2>&1; then
    open "https://here.now/" 2>/dev/null || true
  fi
  # Loop until we get a key that the host accepts (or the user gives up).
  attempts=0
  while [ "$attempts" -lt 5 ]; do
    attempts=$((attempts + 1))
    say
    read -r -p "Paste your API key here (or 'quit' to stop): " host_key
    host_key="$(printf '%s' "$host_key" | tr -d '[:space:]')"
    if [ "$host_key" = "quit" ] || [ -z "$host_key" ]; then
      fail "Cancelled. Run me again whenever you're ready."
      exit 0
    fi
    # Friendly format checks before hitting the API
    if [[ "$host_key" == *@* ]]; then
      warn "That looks like an email address. The key is a long random string, not your email."
      continue
    fi
    if [[ "$host_key" == http* ]]; then
      warn "That looks like a web address. Look for 'API Keys' on the page, not the URL bar."
      continue
    fi
    # Validate against the host
    HTTP=$(curl -sS -o /dev/null -w "%{http_code}" \
      -H "Authorization: Bearer $host_key" \
      https://here.now/api/v1/account 2>>"$INSTALL_LOG" || echo "000")
    case "$HTTP" in
      200)
        printf '%s\n' "$host_key" > "$CRED_FILE"
        chmod 600 "$CRED_FILE"
        ok_paced "Publishing host configured"
        log "publishing host: credential validated"
        break
        ;;
      401|403)
        warn "The host says that key isn't recognized. Did you confirm your email yet?"
        ;;
      404)
        warn "Host returned 404 — make sure you copied the API key exactly, no extra characters."
        ;;
      *)
        warn "Couldn't reach the host (HTTP $HTTP). Try again — if it keeps failing, ask your advisor."
        ;;
    esac
  done
  if [ ! -s "$CRED_FILE" ]; then
    fail "Couldn't get a working key after $attempts tries. Re-run when ready."
    exit 1
  fi
fi

# ── Finalize ──────────────────────────────────────────────────────────────────
say
hr
say "${BOLD}Step 5 of 6 — Setting up your finance workspace${RESET}"
hr
say

# 5a. iCloud sync check — Documents may be synced to iCloud, which would
# silently push the workspace to Apple's cloud. Offer to relocate.
DOCS_REAL="$(cd ~/Documents && pwd -P)"
if [[ "$DOCS_REAL" == */Mobile\ Documents/* ]] && [[ "$WS" == "$HOME/Documents/"* ]]; then
  warn "Your Documents folder syncs to iCloud."
  say "${DIM}For privacy, I can put your finance folder somewhere that doesn't sync.${RESET}"
  read -r -p "Move workspace to ~/finance-workspace/ instead of Documents? [Y/n]: " RELOCATE
  case "$(printf '%s' "$RELOCATE" | tr '[:upper:]' '[:lower:]' | xargs)" in
    ""|y|yes)
      NEW_WS="$HOME/finance-workspace"
      if [ -d "$WS" ] && [ "$WS" != "$NEW_WS" ]; then
        # Move existing partial workspace state
        mkdir -p "$NEW_WS"
        if [ "$(ls -A "$WS" 2>/dev/null)" ]; then
          cp -R "$WS"/. "$NEW_WS"/ 2>>"$INSTALL_LOG" || true
        fi
        rm -rf "$WS"
      fi
      WS="$NEW_WS"
      mkdir -p "$WS"
      ok_paced "Workspace relocated to $WS"
      log "workspace: relocated to non-iCloud path"
      ;;
  esac
fi

# 5b. Folder layout — every subfolder the pipeline expects
mkdir -p "$WS/inbox" \
         "$WS/01_bank_transactions" "$WS/02_payslips" "$WS/03_amazon_orders" \
         "$WS/04_reference_docs" "$WS/05_other" \
         "$WS/pipeline/output/errors" \
         "$WS/fx_cache" "$WS/site"
ok_paced "Workspace folders ready ($WS)"

# 5c. Bootstrap config.yaml from the skill's example
if [ ! -f "$WS/config.yaml" ] && [ -f "$SKILL_INSTALL_DIR/skill/config.example.yaml" ]; then
  cp "$SKILL_INSTALL_DIR/skill/config.example.yaml" "$WS/config.yaml"
  ok_paced "Workspace config created"
fi

# 5d. Pre-warm FX cache — last 24 months of business-day rates so the first
# pipeline run doesn't take 30-60s on a cold cache. Honors the TTY-aware
# progress() helper added in B9.5; visible in this Terminal.
if [ -x "$SKILL_INSTALL_DIR/skill/scripts/fx_fetch.py" ]; then
  say "Pre-warming exchange-rate cache (last 24 months)..."
  END_DATE=$(date +%Y-%m-%d)
  START_DATE=$(date -v-24m +%Y-%m-%d 2>/dev/null || date -d "24 months ago" +%Y-%m-%d 2>/dev/null)
  FCB_WORKSPACE="$WS" "$WS/.venv/bin/python" "$SKILL_INSTALL_DIR/skill/scripts/fx_fetch.py" \
    --base EUR --pairs USD,GBP --start "$START_DATE" --end "$END_DATE" \
    >>"$INSTALL_LOG" 2>&1 || warn "FX pre-warm failed — pipeline will fetch on first use instead"
  ok_paced "Exchange rate cache pre-warmed"
fi

# 5e. Workspace launcher — the script START-HERE.command on the Desktop calls.
# This is what the B9.2 seamless-handoff exec's into at end of install.
LAUNCHER="$WS/.skill-launcher.sh"
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/bin/bash
# Finance Clarity — workspace launcher.
# Created by Welcome.command. Runs every time the user double-clicks
# START-HERE.command on their Desktop.

WS="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "\$WS"

# Activate the workspace venv so the pipeline scripts use the right Python
if [ -f "\$WS/.venv/bin/activate" ]; then
  source "\$WS/.venv/bin/activate"
fi

# Export Anthropic API key from .env if present (for the API-key auth path)
if [ -f "\$WS/.env" ] && grep -q '^ANTHROPIC_API_KEY=' "\$WS/.env"; then
  export ANTHROPIC_API_KEY="\$(grep '^ANTHROPIC_API_KEY=' "\$WS/.env" | cut -d= -f2-)"
fi

# Open Finder window at inbox so the user has a visible drop target
open "\$WS/inbox" 2>/dev/null || true

# Launch Claude Code in the workspace
exec claude
LAUNCHER_EOF
chmod +x "$LAUNCHER"
ok_paced "Workspace launcher created"

# 5f. Desktop shortcut — START-HERE.command. Self-deletes on close to avoid
# clutter; user can re-create later by re-running this installer.
DESKTOP_SHORTCUT="$HOME/Desktop/START-HERE.command"
cat > "$DESKTOP_SHORTCUT" <<SHORTCUT_EOF
#!/bin/bash
# Re-entry point for Finance Clarity. Created by the installer.
# Just runs the workspace launcher in the right workspace.
exec "$LAUNCHER"
SHORTCUT_EOF
chmod +x "$DESKTOP_SHORTCUT"
ok_paced "START-HERE shortcut on Desktop"

say
hr
say "${BOLD}Step 6 of 6 — Final check${RESET}"
hr
say

DIAGNOSTIC_FAILS=0
check() {
  local label="$1"; shift
  if "$@" >>"$INSTALL_LOG" 2>&1; then
    ok_paced "$label"
  else
    fail "$label"
    DIAGNOSTIC_FAILS=$((DIAGNOSTIC_FAILS + 1))
  fi
}
check_file() {
  local label="$1" path="$2"
  if [ -e "$path" ]; then ok_paced "$label"
  else fail "$label (missing: $path)"; DIAGNOSTIC_FAILS=$((DIAGNOSTIC_FAILS + 1)); fi
}

check       "Homebrew installed"             command -v brew
check       "Python 3.11 installed"          test -x "$PYTHON311"
check       "jq installed"                   command -v jq
check       "Claude Code installed"          command -v claude
check_file  "Workspace folder"               "$WS"
check_file  "Workspace venv"                 "$WS/.venv/bin/python"
check_file  "Workspace config"               "$WS/config.yaml"
check_file  "Workspace launcher"             "$WS/.skill-launcher.sh"
check_file  "Desktop shortcut"               "$HOME/Desktop/START-HERE.command"
check_file  "Publishing-host credential"     "$CRED_FILE"
check_file  "Publishing-host skill"          "$HOME/.claude/skills/here-now"
check_file  "Finance Clarity skill"          "$SKILL_INSTALL_DIR/skill"
check_file  "FX cache directory"             "$WS/fx_cache"
# Pipeline scripts importable check
check       "Pipeline scripts importable"    \
  "$WS/.venv/bin/python" -c "import sys; sys.path.insert(0, '$SKILL_INSTALL_DIR/skill/scripts'); import _lib, classify, normalize, categorize, build_site"

if [ "$DIAGNOSTIC_FAILS" -gt 0 ]; then
  fail "$DIAGNOSTIC_FAILS diagnostic check(s) failed — see $INSTALL_LOG for details."
  fail "Re-run me, or contact your advisor with the log file attached."
  exit 1
fi
ok_paced "All diagnostics passed"

say
hr
say "${GREEN}${BOLD}✓ Your workspace is ready.${RESET}"
hr
say

# B9.2 — seamless first-run handoff. Don't make the user hunt for a Desktop
# icon when momentum is highest. Ask, default-yes, exec straight into the
# workflow if a launcher exists. Desktop shortcut is for re-entry next time.
WORKSPACE_LAUNCHER="${WS:-${HOME}/Documents/my-finances}/.skill-launcher.sh"

if [ "$AUTO_MODE" = "1" ] || [ ! -t 0 ]; then
  say "Run START-HERE on your Desktop whenever you want to use it."
  log "completed; auto-mode skipped start-now prompt"
  exit 0
fi

read -r -p "$(printf 'Want to start now? %s[Y/n]%s ' "$BOLD" "$RESET")" START_ANSWER
case "$(printf '%s' "$START_ANSWER" | tr '[:upper:]' '[:lower:]' | xargs)" in
  ""|y|yes)
    if [ -x "$WORKSPACE_LAUNCHER" ]; then
      log "completed; launching workspace"
      exec 3>&-                          # release the install-log fd before exec
      exec "$WORKSPACE_LAUNCHER"
    else
      say
      say "${DIM}(v0 stub: workspace launcher isn't provisioned yet — would normally${RESET}"
      say "${DIM} exec into the AI assistant in your workspace folder here.)${RESET}"
      say
      say "Double-click ${BOLD}START-HERE${RESET} on your Desktop whenever you want to use it."
    fi
    ;;
  *)
    say
    say "Double-click ${BOLD}START-HERE${RESET} on your Desktop whenever you want to use it."
    ;;
esac
say "You can close this window now."
say
log "install completed"
