#!/bin/bash
# restore-workspace.sh — unpack an encrypted workspace backup. Spec §15.
#
# Usage:
#   restore-workspace.sh /path/to/finance-workspace-backup-YYYYMMDD.zip

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

BACKUP="${1:-}"
if [ -z "$BACKUP" ]; then
  echo "Where's your backup file? Drag it into this window or paste the full path,"
  read -r -p "then press Enter: " BACKUP
fi
[ -f "$BACKUP" ] || fail "backup file not found: $BACKUP"

read -r -s -p "Backup password: " PW; echo

STAGING=$(mktemp -d "/tmp/fcb-restore.XXXXXX")
trap "rm -rf '$STAGING'" EXIT

step "Unpacking backup"
( cd "$STAGING" && unzip -qq -P "$PW" "$BACKUP" ) || fail "wrong password or corrupted file"

# Restore each file the backup contains
for src in rules.yaml fx_overrides.yaml config.yaml .env; do
  if [ -f "$STAGING/$src" ]; then
    if [ -f "$WS/$src" ]; then
      cp "$WS/$src" "$WS/$src.bak.$(date +%Y%m%dT%H%M%S)"
    fi
    cp "$STAGING/$src" "$WS/$src"
    chmod 600 "$WS/$src" 2>/dev/null || true
    echo "  ✓ restored $src"
  fi
done
if [ -d "$STAGING/.herenow" ]; then
  rm -rf "$WS/.herenow"
  cp -R "$STAGING/.herenow" "$WS/.herenow"
  echo "  ✓ restored .herenow/"
fi

cat <<EOF

✓ Done. Your workspace is restored.

  Next: run "refresh" so I can validate the connection to your existing
  dashboard (if you had one). Drop new files into inbox/ if you have any.

EOF
