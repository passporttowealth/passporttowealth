#!/bin/bash
#
# install.sh — Passport to Wealth Finance Clarity bootstrap installer (macOS).
#
# Canonical install path. Designed to be streamed and executed in one shot:
#
#   curl -fsSL https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.sh | bash
#
# (or, if the branded short URL is wired up:)
#
#   curl -fsSL https://passporttowealth.app/install | bash
#
# Provisions Xcode CLT, uv (Python toolchain), Python 3.11 via uv, jq (via
# Homebrew only if missing), Claude Code, the here-now publishing skill, the
# finance-clarity-build skill (via npx skills add), and the workspace at
# ~/Documents/my-finances. Leaves no artifacts on the Desktop. Re-entry is
# `claude` from any Terminal — the skill knows where the workspace is.
#
# Curl-pipe-bash bypasses macOS Gatekeeper because nothing lands on disk as a
# downloaded file. The legacy double-click path lives at installer/legacy/
# (kept as a fallback for users who can't open Terminal).
#
# Full design: dev/finance-clarity-build-spec.md §4.
#
# Copyright © 2026 Passport to Wealth. All rights reserved.

set -u

# Curl-pipe-bash gotcha: when the script is invoked as `curl ... | bash`,
# bash reads the entire script from the pipe and stdin reaches EOF before any
# `read` runs — so consent prompts auto-fire with empty input and the install
# silently cancels. Re-bind stdin to the controlling terminal so `read` works.
#
# We capture the interactive state into INTERACTIVE *once* here. Helpers like
# pause_for_user use that flag instead of re-testing `[ -t 0 ]` later, because
# bash 3.2 (Apple's default) sometimes returns the original (pre-redirect)
# tty state from `[ -t 0 ]` even after a successful redirect — leading to
# pauses being silently skipped even when stdin IS a tty after rebind.
#
# INTERACTIVE_DIAG is logged later (once $INSTALL_LOG is open) so support
# can see exactly which branch fired without asking the user to re-run.
INTERACTIVE=1
if [ -t 0 ]; then
  INTERACTIVE_DIAG="already_tty"
elif [ -e /dev/tty ] && exec </dev/tty 2>/dev/null; then
  INTERACTIVE_DIAG="rebind_ok"
else
  INTERACTIVE=0
  INTERACTIVE_DIAG="rebind_failed"
  AUTO_MODE_FORCED=1   # truly headless — fall back to non-interactive
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
# AUTO_MODE_FORCED is set above when there's no controlling TTY (headless
# install, e.g. CI). Honor it the same way as the explicit --auto flag.
if [ "${AUTO_MODE_FORCED:-0}" = "1" ]; then
  AUTO_MODE=1
  PACE_SLEEP="0"
fi

ok_paced()  { ok "$@"; [ "$AUTO_MODE" = "0" ] && sleep "$PACE_SLEEP"; }
say_paced() { say "$@"; [ "$AUTO_MODE" = "0" ] && sleep "$PACE_SLEEP"; }

# pause_for_user — explicit "Press Enter to continue" gate between major
# sections. Converts the firehose into a conversation. TTY-guarded so
# non-interactive runs (--auto, scripts, CI) don't hang.
pause_for_user() {
  # Use the captured INTERACTIVE flag set at the top, NOT a fresh `-t 0`
  # test. Bash 3.2 can return the pre-redirect TTY state even after a
  # successful `exec </dev/tty`, which previously caused this function
  # to silently skip every pause.
  if [ "$AUTO_MODE" = "1" ] || [ "$INTERACTIVE" = "0" ]; then
    return 0
  fi
  # Print the prompt as a STANDALONE line via printf (stdout) instead of
  # using `read -p`. Two reasons: (1) bash's `read -p` writes to stderr
  # with quirky flushing on some macOS terminals so the prompt can fail
  # to appear, and (2) DIM ANSI (\033[2m) is borderline-invisible on
  # several Mac Terminal themes. We use BOLD + a leading "▶" marker to
  # be unmissable, on its own line, then read empty input.
  printf '\n%s▶ Press Enter to continue%s\n' "$BOLD" "$RESET"
  read -r _
}

INSTALL_LOG="${HOME}/Library/Logs/passport-to-wealth-install.log"
mkdir -p "$(dirname "$INSTALL_LOG")"
exec 3>>"$INSTALL_LOG"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&3; }

# Surface the early TTY-rebind result so post-mortem support knows
# exactly which branch fired (already_tty / rebind_ok / rebind_failed).
# If a future client reports "press enter never showed", this line in
# the install log tells us why without needing a re-run.
log "tty_state: ${INTERACTIVE_DIAG} interactive=${INTERACTIVE} auto_mode_forced=${AUTO_MODE_FORCED:-0}"

# Track which phase we're in so a Ctrl-C / SIGTERM can log "cancelled at X".
# Updated at each Step heading. Initial value covers "before pre-flight" so an
# interrupt during the consent gate still logs something useful.
CURRENT_STEP="pre-consent"

# Issue E3 — SIGINT/SIGTERM trap. The previous installer exited silently on
# Ctrl-C with no log line, leaving advisors blind to where users abandoned.
# This trap also catches SIGTERM (e.g. user closes the Terminal window mid-run).
on_interrupt() {
  printf '\n'
  warn "Cancelled by you during: ${CURRENT_STEP}"
  log "user_interrupt at step=${CURRENT_STEP}"
  say "${DIM}Re-run me any time — most steps are idempotent.${RESET}"
  exit 130   # conventional exit code for "terminated by Ctrl-C"
}
trap on_interrupt INT TERM

# Note: the previous Terminal-window auto-close helper was removed in B9.10.
# It existed because the legacy Welcome.command opened its own Terminal window
# via `open -a Terminal "$0"` and we wanted to clean up at exit. The curl-piped
# install.sh runs inside the user's existing Terminal — closing that window
# would yank away their other tabs/windows. Just exit cleanly with a friendly
# message instead.

# Workspace location — overridable via FCB_WORKSPACE for testing.
# Default is ~/Documents/my-finances (adjusted later if iCloud-synced).
WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"

# Source-of-truth for the skill. Step 2h fetches it via `npx skills add`
# (B9.8 — same pattern Step 2g uses for the here-now skill). The skill CLI
# clones the repo, walks for SKILL.md, and installs the matching subdirectory
# to ~/.claude/skills/finance-clarity-build/. Override SKILL_REPO_REF for
# testing forks/branches (e.g. SKILL_REPO_REF=passporttowealth/finance-clarity).
SKILL_REPO_REF="${FCB_SKILL_REPO_REF:-passporttowealth/passporttowealth}"
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

# Pre-consent text is dense and important (privacy disclosures, what the
# user is agreeing to). Dry-run feedback: it dumps in <1 second and the
# user can't keep up. Split into three logical sections, each followed by
# pause_for_user so the user controls when to advance. Within each section,
# emphasis lines use say_paced so the eye gets a beat between bullets.
# --auto bypasses everything (existing behavior).

# ── Section 1: welcome + what-the-user-does preview ──────────────────────────
clear
hr
say "${BOLD}Welcome — let's set up your private finance workspace.${RESET}"
hr
say
say "I'll do all the technical bits. You'll only need to:"
say
say_paced "  1. Type your Mac password once (when Mac asks)."
say_paced "  2. Sign in to your AI assistant."
say_paced "  3. Sign up for the service that hosts your private dashboard."
say
pause_for_user

# ── Section 2: prototype notice (always visible — not dimmed) ────────────────
say
hr
say "${YELLOW}${BOLD}⚠  PROTOTYPE — pre-release software${RESET}"
hr
say
say "This is a ${BOLD}pilot tool${RESET} for clients of Passport to Wealth, under"
say "active development. Use it as a complement to — not a replacement for —"
say "your existing financial records."
say
say_paced "  • Expect bugs and incomplete features."
say_paced "  • ${BOLD}Always keep your original bank exports and statements.${RESET}"
say_paced "  • Do not delete source files based on what the dashboard shows."
say_paced "  • If anything looks wrong, tell your advisor — don't assume the"
say         "    dashboard is correct."
say
pause_for_user

# ── Section 3: Anthropic data-terms consent gate (OP-13) ─────────────────────
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
say_paced "  • Privacy hub:           ${BOLD}https://privacy.anthropic.com/${RESET}"
say_paced "  • Privacy policy:        ${BOLD}https://www.anthropic.com/legal/privacy${RESET}"
say_paced "  • Consumer (Pro/Max):    ${BOLD}https://www.anthropic.com/legal/consumer-terms${RESET}"
say_paced "  • Commercial (API key):  ${BOLD}https://www.anthropic.com/legal/commercial-terms${RESET}"
say_paced "  • Trust & security:      ${BOLD}https://trust.anthropic.com/${RESET}"
say
say "Things to know — and to manage in your Anthropic account settings:"
say_paced "  • You can opt out of having your conversations used to improve Claude."
say_paced "  • You can delete your conversation history at any time."
say_paced "  • Sensitive files (paystubs, tax documents) are skipped by default by"
say         "    this skill, so their contents are not sent to Claude unless you"
say         "    explicitly ask."
say
say "If you do not accept Anthropic's terms, please ${BOLD}stop here${RESET} and contact"
say "your advisor — we can talk about alternatives."
say
pause_for_user

# NOTE (B9.1): we deliberately do NOT auto-open the privacy hub in a
# browser here. Auto-opening mid-flow snaps focus away from this Terminal
# and confuses users about what to type next. Terminal already linkifies
# the URLs printed above — the user clicks if they want to read first.

say "${BOLD}By typing 'I accept' below you confirm:${RESET}"
say_paced "  1. You accept Anthropic's data-handling terms (linked above)."
say_paced "  2. You understand this is ${BOLD}prototype${RESET} software and you will keep"
say         "     your original financial records as the source of truth."
say
while true; do
  printf '%s▶ Type "I accept" to continue, or "no" to cancel:%s ' "$BOLD" "$RESET"
  read -r consent
  consent_lc=$(printf '%s' "$consent" | tr '[:upper:]' '[:lower:]' | xargs)
  case "$consent_lc" in
    "i accept"|"i agree"|"accept"|"agree"|"yes")
      ok "Acceptance recorded."
      log "consent_accepted_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) (anthropic_data_terms + prototype_status)"
      break
      ;;
    "no"|"cancel"|"quit"|"stop")
      # Empty input intentionally NOT in this branch. If the TTY rebind
      # failed, `read` returns immediately with empty input — we don't
      # want that to silently exit. Empty falls through to the re-prompt
      # below where the user gets a clear "I didn't catch that" message.
      say
      say "${DIM}No problem — install cancelled. Talk to your advisor any time.${RESET}"
      log "consent_declined_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      exit 0
      ;;
    "")
      warn "I didn't catch any input. Type ${BOLD}I accept${RESET} to continue, or ${BOLD}no${RESET} to cancel."
      log "consent_empty_input — possibly tty_state=${INTERACTIVE_DIAG}"
      # If we keep getting empty input, the TTY rebind is broken and
      # we'd loop forever. Detect 5 empties in a row and bail with a
      # clear support pointer.
      EMPTY_COUNT=$((${EMPTY_COUNT:-0} + 1))
      if [ "$EMPTY_COUNT" -ge 5 ]; then
        fail "I'm not getting any input from you (5 empty replies in a row)."
        fail "This usually means the install can't read from your terminal. See:"
        fail "  $INSTALL_LOG"
        fail "Send the log to your advisor."
        log "consent_aborted_after_${EMPTY_COUNT}_empties tty_state=${INTERACTIVE_DIAG}"
        exit 1
      fi
      ;;
    *)
      warn "I didn't understand. Please type 'I accept' or 'no'."
      ;;
  esac
done

say
# Same visibility fix as pause_for_user: print prompt as a line, then
# `read` without -p. `read -p` plus DIM/BOLD ANSI is invisible on some
# Mac Terminal themes.
printf '%s▶ Press Enter to begin the install (or Ctrl-C to cancel)%s\n' "$BOLD" "$RESET"
read -r _

# ── Pre-flight (OP-11) ────────────────────────────────────────────────────────
say
hr
CURRENT_STEP="1/5 pre-flight checks"
say "${BOLD}Step 1 of 5 — Checking your Mac${RESET}"
hr

log "preflight start"

# macOS version
macos_major=$(sw_vers -productVersion | cut -d. -f1)
if [[ "$macos_major" -lt 13 ]]; then
  fail "Your Mac is running macOS $(sw_vers -productVersion). I need macOS 13 (Ventura) or later."
  fail "FCB-0001 — see dev/finance-clarity-build-spec.md §4.2"
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
CURRENT_STEP="2/5 installing tools"
say "${BOLD}Step 2 of 5 — Installing the tools your dashboard needs${RESET}"
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

# 2b. Homebrew — needed for jq + Node.js. Skipped entirely if all three of
# {brew, jq, node} are already present. uv (next step) replaces Homebrew's
# role for Python provisioning.
NEED_BREW=0
if ! command -v jq   >/dev/null 2>&1; then NEED_BREW=1; fi
if ! command -v node >/dev/null 2>&1; then NEED_BREW=1; fi
if [ "$NEED_BREW" = "1" ] && ! command -v brew >/dev/null 2>&1; then
  say "Installing Homebrew (Mac will ask for your password). Needed to fetch jq + Node.js..."
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
elif command -v brew >/dev/null 2>&1; then
  ok_paced "Homebrew already installed"
fi

# 2c. uv — single 10MB binary that replaces our previous brew/python/venv/pip
# chain. One install action (this) instead of four (Homebrew, brew Python,
# python -m venv, pip install). Astral's installer drops it at ~/.local/bin/uv.
UV_BIN="${HOME}/.local/bin/uv"
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
  ok_paced "uv already installed"
else
  say "Installing uv (Python toolchain)..."
  log "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh 2>>"$INSTALL_LOG" | sh >>"$INSTALL_LOG" 2>&1 \
    || { fail "uv install failed — see $INSTALL_LOG"; exit 1; }
  if [ ! -x "$UV_BIN" ]; then
    fail "uv installer ran but $UV_BIN not found — see $INSTALL_LOG"
    exit 1
  fi
  # Make uv findable for the rest of this script + future shell sessions.
  export PATH="${HOME}/.local/bin:${PATH}"
  ok_paced "uv installed"
fi

# 2d. Python 3.11 (we pin to 3.11 because some upstream deps lag on 3.13/3.14).
# uv downloads a managed, isolated CPython — no system Python involved, no
# Homebrew taps, no PATH games. PYTHON311 resolves to an absolute path inside
# uv's managed install directory so Step 6 `test -x` works correctly.
say "Provisioning Python 3.11..."
"$UV_BIN" python install 3.11 >>"$INSTALL_LOG" 2>&1 \
  || { fail "uv python install 3.11 failed — see $INSTALL_LOG"; exit 1; }
PYTHON311="$("$UV_BIN" python find 3.11 2>>"$INSTALL_LOG" | head -1)"
if [ -z "$PYTHON311" ] || [ ! -x "$PYTHON311" ]; then
  fail "uv installed Python 3.11 but couldn't resolve its path — see $INSTALL_LOG"
  exit 1
fi
ok_paced "Python 3.11 ready ($PYTHON311)"

# 2e. jq + Node.js — both via Homebrew (the only tools we need brew for).
#   jq:   used by the here-now publish script + our wrapper scripts.
#   node: provides `npx`, which Steps 2g + 2h use to install the here-now
#         and finance-clarity-build skills via `npx skills add`. Without
#         this, `npx: command not found` would dead-end every fresh-Mac
#         install (Apple doesn't ship Node).
if command -v jq >/dev/null 2>&1; then
  ok_paced "jq already installed"
else
  run_quiet "jq installed" brew install jq || exit 1
fi
if command -v node >/dev/null 2>&1; then
  ok_paced "Node.js already installed (provides npx for skill installs)"
else
  say "Installing Node.js (~10s, gives us npx for the next steps)..."
  run_quiet "Node.js installed" brew install node || exit 1
fi

# 2f. Workspace venv + Python deps. uv handles both in one operation per call.
# `uv venv` creates ~/Documents/my-finances/.venv pointing at the managed
# Python from 2d; `uv pip install --python` installs into that venv without
# needing source-activation.
mkdir -p "$WS"
if [ -x "$WS/.venv/bin/python" ]; then
  ok_paced "Workspace Python environment already set up"
else
  say "Creating workspace Python environment..."
  "$UV_BIN" venv --python "$PYTHON311" "$WS/.venv" >>"$INSTALL_LOG" 2>&1 \
    || { fail "uv venv failed — see $INSTALL_LOG"; exit 1; }
  ok_paced "Workspace Python environment ready"
fi

# Install / update Python deps. uv resolves + installs in one shot, far faster
# than pip. Inline list (skill repo's requirements.txt may not be on disk yet).
say "Installing Python dependencies..."
"$UV_BIN" pip install --python "$WS/.venv/bin/python" --quiet \
  "openpyxl~=3.1" "pdfplumber~=0.11" "PyYAML~=6.0" "chardet~=5.2" "reportlab~=4.4" \
  >>"$INSTALL_LOG" 2>&1 || { fail "Python deps install failed — see $INSTALL_LOG"; exit 1; }
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

# 2g. here-now skill — bundles the publishing flow.
# Non-interactive flags: --agent claude-code (skip the agent picker),
# -y (skip confirmation prompts). Without these the install hangs on the
# interactive scope/agent menu when run via curl-pipe-bash (no TTY for input).
mkdir -p "$HOME/.claude/skills"
if [ -d "$HOME/.claude/skills/here-now" ]; then
  ok_paced "Publishing-host skill already installed"
elif ! command -v npx >/dev/null 2>&1; then
  # Defensive: Step 2e brew-installs Node, so this branch should be unreachable.
  # If it fires, something went wrong with the brew step — point at the log.
  fail "npx not available even after Step 2e — see $INSTALL_LOG and contact your advisor"
  exit 1
else
  say "Installing publishing-host skill..."
  npx -y skills add heredotnow/skill --skill here-now --agent claude-code -g -y \
    >>"$INSTALL_LOG" 2>&1 \
    || { fail "here-now skill install failed — see $INSTALL_LOG"; exit 1; }
  ok_paced "Publishing-host skill installed"
fi

# 2h. finance-clarity-build skill — fetched via the same skills CLI as Step 2g.
# Walks the repo for SKILL.md and copies the matching subdirectory contents to
# ~/.claude/skills/finance-clarity-build/. The skill subdir lands flat under
# SKILL_INSTALL_DIR (no /skill/ prefix). See B9.8 in dev/backlog.md for context.
if [ -f "$SKILL_INSTALL_DIR/SKILL.md" ]; then
  say "Updating finance-clarity-build skill..."
  npx -y skills add "$SKILL_REPO_REF" --skill finance-clarity-build --agent claude-code -g -y \
    >>"$INSTALL_LOG" 2>&1 \
    || { fail "Skill update failed — see $INSTALL_LOG"; exit 1; }
  ok_paced "Finance Clarity skill up-to-date"
else
  say "Installing Finance Clarity skill..."
  npx -y skills add "$SKILL_REPO_REF" --skill finance-clarity-build --agent claude-code -g -y \
    >>"$INSTALL_LOG" 2>&1 \
    || { fail "Skill install failed — see $INSTALL_LOG"; exit 1; }
  ok_paced "Finance Clarity skill installed"
fi

# ── AI assistant auth (§4.3) ──────────────────────────────────────────────────
say
hr
CURRENT_STEP="3/5 Claude sign-in"
say "${BOLD}Step 3 of 5 — Signing in to your AI assistant${RESET}"
hr
say
say "How do you sign in to Claude?"
say "  1. ${BOLD}Paid subscription${RESET} — Claude Pro or Max (sign in with your email)"
say "  2. ${BOLD}Anthropic API key${RESET} — paste the key (starts with sk-ant-)"
say
say "${DIM}If you don't have either, please call your advisor — this is the"
say "one step I can't do without you.${RESET}"
say
printf '%s▶ Type 1 or 2:%s ' "$BOLD" "$RESET"
read -r auth_choice

case "$auth_choice" in
  1)
    # Subscription path: confirm Claude Code is callable and stop. We don't
    # actively probe OAuth here. Reasons:
    #   1. `claude --print "ready"` would burn subscription quota for a probe.
    #   2. The probe picks up stale ANTHROPIC_API_KEY env vars (left over
    #      from prior installs / other tools) and prefers them over OAuth —
    #      surfacing a misleading "non-zero exit" warning when the user's
    #      subscription auth is actually fine.
    # When the user runs `claude` for the first time post-install, Claude
    # Code's normal first-run UX walks them through OAuth if needed.
    if claude --version >>"$INSTALL_LOG" 2>&1; then
      ok_paced "Claude Code ready"
      say "${DIM}Next time you run 'claude', it'll open your browser to sign in if needed.${RESET}"
      log "claude subscription path — deferring OAuth to user's first claude invocation"
    else
      fail "Claude Code didn't respond — install may have left it in a bad state"
      exit 1
    fi
    ;;
  2)
    say
    printf '%s▶ Paste your Anthropic API key (won'\''t be shown):%s ' "$BOLD" "$RESET"
    read -r -s api_key
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
    # Store the key in two places:
    #   1. Workspace .env (so the skill scripts can read it if needed).
    #   2. The user's shell rc, exported as ANTHROPIC_API_KEY (so claude
    #      picks it up no matter where they run it from). With START-HERE
    #      gone, the workspace launcher doesn't export the env var anymore,
    #      so the shell-rc export becomes the only universal path for
    #      API-key-auth users.
    mkdir -p "$WS"
    if [ -f "$WS/.env" ]; then
      grep -v '^ANTHROPIC_API_KEY=' "$WS/.env" 2>/dev/null > "$WS/.env.tmp" || true
      mv "$WS/.env.tmp" "$WS/.env"
    fi
    printf 'ANTHROPIC_API_KEY=%s\n' "$api_key" >> "$WS/.env"
    chmod 600 "$WS/.env"

    # Detect the user's shell rc (zsh on macOS 10.15+, bash for older systems).
    # Append a guarded export — idempotent if the user re-runs the installer.
    SHELL_RC=""
    case "${SHELL:-}" in
      */zsh) SHELL_RC="$HOME/.zshrc" ;;
      */bash) [ -f "$HOME/.bash_profile" ] && SHELL_RC="$HOME/.bash_profile" || SHELL_RC="$HOME/.bashrc" ;;
      *) SHELL_RC="$HOME/.zshrc" ;;  # default to zsh — modern macOS default
    esac
    touch "$SHELL_RC"
    # Strip any prior block we added (idempotent rerun)
    if grep -q '^# Passport to Wealth — Finance Clarity API key' "$SHELL_RC" 2>/dev/null; then
      sed -i.fcb-bak '/^# Passport to Wealth — Finance Clarity API key$/,/^# Passport to Wealth — end$/d' "$SHELL_RC"
      rm -f "${SHELL_RC}.fcb-bak"
    fi
    {
      printf '\n# Passport to Wealth — Finance Clarity API key\n'
      printf 'export ANTHROPIC_API_KEY=%s\n' "$api_key"
      printf '# Passport to Wealth — end\n'
    } >> "$SHELL_RC"
    log "api key saved to workspace .env + exported in $SHELL_RC"
    say "${DIM}Note: I added an export line to $SHELL_RC so claude finds the key${RESET}"
    say "${DIM}from any new Terminal window. Open a fresh tab to pick it up.${RESET}"
    ;;
  *)
    fail "I didn't understand. Run me again and pick 1 or 2."
    exit 1
    ;;
esac
ok_paced "AI assistant ready"

# Local-first architecture (Strategic #2): the dashboard opens in your
# browser locally by default. The publishing-host signup that used to live
# here as Step 4 has moved into skill/scripts/publish.sh — it now runs
# only when (and IF) the user explicitly chooses to share the dashboard
# with their advisor or family. Most dry-runs never need it.

# ── Finalize ──────────────────────────────────────────────────────────────────
say
hr
CURRENT_STEP="4/5 workspace setup"
say "${BOLD}Step 4 of 5 — Setting up your finance workspace${RESET}"
hr
say

# 5a. iCloud sync check — Documents may be synced to iCloud, which would
# silently push the workspace to Apple's cloud. Offer to relocate.
DOCS_REAL="$(cd ~/Documents && pwd -P)"
if [[ "$DOCS_REAL" == */Mobile\ Documents/* ]] && [[ "$WS" == "$HOME/Documents/"* ]]; then
  warn "Your Documents folder syncs to iCloud."
  say "${DIM}For privacy, I can put your finance folder somewhere that doesn't sync.${RESET}"
  printf '%s▶ Move workspace to ~/finance-workspace/ instead of Documents? [Y/n]:%s ' "$BOLD" "$RESET"
  read -r RELOCATE
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
if [ ! -f "$WS/config.yaml" ] && [ -f "$SKILL_INSTALL_DIR/config.example.yaml" ]; then
  cp "$SKILL_INSTALL_DIR/config.example.yaml" "$WS/config.yaml"
  ok_paced "Workspace config created"
fi

# 5d. Pre-warm FX cache — last 24 months of business-day rates so the first
# pipeline run doesn't take 30-60s on a cold cache.
#
# stdout (noisy fetch debug) → install log; stderr (the progress() bar from
# _lib.py — TTY-guarded) → /dev/tty so the user sees motion in this Terminal
# even though we're inside a pipeline of redirects. If we used `2>&1` the
# helper would correctly detect "stderr is not a TTY" and stay silent,
# producing the 30-60s "stalled" silence the user reported.
if [ -x "$SKILL_INSTALL_DIR/scripts/fx_fetch.py" ]; then
  say "Pre-warming exchange-rate cache (last 24 months)..."
  END_DATE=$(date +%Y-%m-%d)
  START_DATE=$(date -v-24m +%Y-%m-%d 2>/dev/null || date -d "24 months ago" +%Y-%m-%d 2>/dev/null)
  FCB_WORKSPACE="$WS" "$WS/.venv/bin/python" "$SKILL_INSTALL_DIR/scripts/fx_fetch.py" \
    --base EUR --pairs USD,GBP --start "$START_DATE" --end "$END_DATE" \
    >>"$INSTALL_LOG" 2>/dev/tty || warn "FX pre-warm failed — pipeline will fetch on first use instead"
  ok_paced "Exchange rate cache pre-warmed"
fi

# Note: Step 5e/5f (workspace launcher script + START-HERE Desktop shortcut)
# were intentionally removed. Re-entry is now: open Terminal, type `claude`.
# The skill scripts default to ~/Documents/my-finances/.venv/bin/python (set
# in refresh.sh) so no venv-activation wrapper is needed. Claude Code's own
# auth state handles the AI side. No artifacts on the user's Desktop.

say
hr
CURRENT_STEP="5/5 final diagnostics"
say "${BOLD}Step 5 of 5 — Final check${RESET}"
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

check       "uv installed"                   test -x "$UV_BIN"
check       "Python 3.11 installed"          test -x "$PYTHON311"
check       "jq installed"                   command -v jq
check       "Node.js installed (npx)"        command -v npx
check       "Claude Code installed"          command -v claude
check_file  "Workspace folder"               "$WS"
check_file  "Workspace venv"                 "$WS/.venv/bin/python"
check_file  "Workspace config"               "$WS/config.yaml"
# Publishing-host credential is provisioned on first share (publish.sh runs
# the email-code flow then). Not checked here — most users never publish.
check_file  "Publishing-host skill"          "$HOME/.claude/skills/here-now"
check_file  "Finance Clarity skill"          "$SKILL_INSTALL_DIR/SKILL.md"
check_file  "FX cache directory"             "$WS/fx_cache"
# Pipeline scripts importable check
check       "Pipeline scripts importable"    \
  "$WS/.venv/bin/python" -c "import sys; sys.path.insert(0, '$SKILL_INSTALL_DIR/scripts'); import _lib, classify, normalize, categorize, build_site"

if [ "$DIAGNOSTIC_FAILS" -gt 0 ]; then
  # Diagnostic failures are now warnings, not blockers. The skill itself will
  # surface real problems when the user tries to use it; no point dead-ending
  # a possibly-fine install over a single check that may be a false positive.
  warn "$DIAGNOSTIC_FAILS diagnostic check(s) reported issues — see $INSTALL_LOG."
  warn "If something misbehaves when you run claude, re-run the installer or"
  warn "share the log with your advisor."
  log "diagnostic_failures count=$DIAGNOSTIC_FAILS"
else
  ok_paced "All diagnostics passed"
fi

say
hr
say "${GREEN}${BOLD}✓ Your workspace is ready.${RESET}"
hr
say
say "Anytime you want to use it:"
say
say "  ${BOLD}1.${RESET} Open ${BOLD}Terminal${RESET} (⌘+Space → type ${BOLD}Terminal${RESET} → Enter)"
say "  ${BOLD}2.${RESET} Type:  ${BOLD}claude${RESET}"
say "  ${BOLD}3.${RESET} Tell it ${BOLD}\"build my report\"${RESET} or ${BOLD}\"refresh my finances\"${RESET}"
say
say "Drop your bank statements and other files in:"
say "  ${BOLD}$WS/inbox/${RESET}"
say
say "${DIM}The skill knows where your workspace is — no need to navigate to it.${RESET}"
say
log "install completed"
