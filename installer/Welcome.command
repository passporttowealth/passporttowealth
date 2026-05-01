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

# ── Runtime provisioning (stubbed) ────────────────────────────────────────────
hr
say "${BOLD}Step 2 of 6 — Installing the tools your dashboard needs${RESET}"
hr
say
warn "[STUB] This step would install: Xcode CLT, Homebrew, Python 3.11, jq,"
warn "       openpyxl, pdfplumber, pyyaml, chardet, Claude Code CLI, the"
warn "       publishing-host skill, and the finance-clarity-build skill."
log "stub: runtime install"

# ── AI assistant auth (§4.3) ──────────────────────────────────────────────────
say
hr
say "${BOLD}Step 3 of 6 — Signing in to your AI assistant${RESET}"
hr
say
say "How do you sign in to Claude?"
say "  1. Claude Pro (~\$17/month) — sign in with your email"
say "  2. Claude Max — sign in with your email"
say "  3. An Anthropic API key — paste the key (starts with sk-ant-)"
say
say "${DIM}If you don't have any of these, please call your advisor — this is"
say "the one step I can't do without you.${RESET}"
say
read -r -p "Type 1, 2, or 3: " auth_choice

case "$auth_choice" in
  1|2)
    warn "[STUB] Would launch \`claude\` to trigger the OAuth browser flow,"
    warn "       wait for completion, and verify with a one-shot prompt."
    log "stub: claude oauth"
    ;;
  3)
    say
    read -r -s -p "Paste your Anthropic API key (won't be shown): " api_key
    say
    if [[ ! "$api_key" =~ ^sk-ant- ]]; then
      fail "That doesn't look like an Anthropic API key (should start with sk-ant-)."
      fail "FCB-0004"
      log "FCB-0004 api_key_format_invalid"
      exit 1
    fi
    warn "[STUB] Would write key to workspace .env (chmod 600), export to"
    warn "       START-HERE's launch env, and verify with a 1-token request."
    log "stub: api key path"
    ;;
  *)
    fail "I didn't understand. Run me again and pick 1, 2, or 3."
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
warn "[STUB] Would open https://here.now/signup in the browser, then loop:"
warn "       prompt → trim → test API call → on failure show specific guidance"
warn "       (\"that looks like an email\" / \"that looks like a URL\" etc.)."
log "stub: publishing host signup"

# ── Finalize ──────────────────────────────────────────────────────────────────
say
hr
say "${BOLD}Step 5 of 6 — Setting up your finance workspace${RESET}"
hr
say
warn "[STUB] Would create ~/Documents/my-finances/ with subfolder layout,"
warn "       pre-warm the FX cache (24 months), check iCloud sync and offer"
warn "       to relocate to ~/finance-workspace/, drop START-HERE on Desktop."
log "stub: workspace creation"

say
hr
say "${BOLD}Step 6 of 6 — Final check${RESET}"
hr
say
warn "[STUB] Would run the diagnostic and report green/red for each component."
log "stub: diagnostic"

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
