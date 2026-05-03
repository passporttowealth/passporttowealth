#!/bin/bash
# backup-workspace.sh — encrypted backup of the user's workspace settings.
# Spec §15.
#
# Bundles: rules.yaml, fx_overrides.yaml, config.yaml, .env, .herenow/state.json
# Encrypted with a one-time password the user supplies (we do NOT store it).
# Output to ~/Desktop/finance-workspace-backup-{date}.zip
#
# Excludes: any client transaction data, payslips, tax docs, FX cache,
# pipeline outputs.

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
DESKTOP="${HOME}/Desktop"
[ -d "$DESKTOP" ] || DESKTOP="$WS"
DATE=$(date +%Y%m%d)
OUT="$DESKTOP/finance-workspace-backup-$DATE.zip"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

command -v zip >/dev/null || fail "zip not installed"

# Get a one-time backup password from the user. We don't store it — they re-supply on restore.
echo ""
echo "I'll bundle your settings into a single encrypted file you can store"
echo "anywhere safe (cloud drive, USB stick, even email-to-self)."
echo ""
echo "I need a password for the backup. Pick something you'll remember —"
echo "without it the backup is unrecoverable."
echo ""

read -r -s -p "Backup password: " PW1; echo
read -r -s -p "Confirm:         " PW2; echo
[ "$PW1" = "$PW2" ] || fail "passwords don't match"
[ ${#PW1} -ge 8 ] || fail "password must be at least 8 characters"

# Stage the files we'll back up
STAGING=$(mktemp -d "/tmp/fcb-backup.XXXXXX")
trap 'rm -rf "$STAGING"' EXIT

[ -f "$WS/rules.yaml" ]          && cp "$WS/rules.yaml"          "$STAGING/"
[ -f "$WS/fx_overrides.yaml" ]   && cp "$WS/fx_overrides.yaml"   "$STAGING/"
[ -f "$WS/config.yaml" ]         && cp "$WS/config.yaml"         "$STAGING/"
[ -f "$WS/.env" ]                && cp "$WS/.env"                "$STAGING/.env"
[ -d "$WS/.herenow" ]            && cp -R "$WS/.herenow"         "$STAGING/.herenow"

step "Bundling encrypted backup"
( cd "$STAGING" && zip -qr -P "$PW1" "$OUT" . )

cat <<EOF

✓ Done. Backup saved to:
      $OUT

  Keep it somewhere safe — cloud drive, USB stick, etc.
  To use it on a new computer:
    1. Install the workspace there first.
    2. Say "restore from backup" and point me at the file.

  Without the password you typed, the backup cannot be opened — by you,
  by me, by anyone. Don't lose it.

EOF
