#!/bin/bash
# view-local.sh — open the freshly built dashboard in the user's default browser
# from disk (file:// URL). The local-first default for the Strategic #2 flow:
# users see their dashboard immediately, no third-party server, no signup,
# no passcode. Sharing (here.now) is opt-in via publish.sh.
#
# Spec §12.5. Reads from $WS/site/index.html. Refuses if site/ is missing or
# stale (refresh.sh writes site/, so this should always exist after refresh).

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
SITE="$WS/site"
INDEX="$SITE/index.html"

fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
note() { printf '  %s\n' "$*"; }

[ -d "$SITE" ]   || fail "no site/ at $SITE — run refresh.sh first"
[ -f "$INDEX" ]  || fail "site/ exists but index.html is missing — try a fresh refresh.sh"

URL="file://$INDEX"

printf '\n\033[1m▸ Opening your dashboard locally\033[0m\n'
note "URL:   $URL"
note "Privacy: this file lives only on your laptop. Nothing is sent anywhere."
note "Share:  if you'd like to share with an advisor or family member,"
note "        ask Claude to 'share my dashboard' — that runs the publish flow."

# Cross-platform open. macOS = open, Linux = xdg-open, Windows (git-bash) = start.
if command -v open >/dev/null 2>&1; then
  open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL"
elif command -v start >/dev/null 2>&1; then
  start "" "$URL"
else
  printf '\n  Could not auto-open a browser. Paste this URL into yours:\n  %s\n\n' "$URL"
fi
