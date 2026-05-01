#!/bin/bash
# reset-rules.sh — back up rules.yaml and restore the starter set. Spec §15.

set -euo pipefail

WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STARTER="$SKILL_ROOT/templates/rules-starter.yaml"
USER_RULES="$WS/rules.yaml"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }

[ -f "$STARTER" ] || { printf '\033[31m✗ starter rules missing at %s\033[0m\n' "$STARTER" >&2; exit 1; }

if [ -f "$USER_RULES" ]; then
  BAK="$USER_RULES.bak.$(date +%Y%m%dT%H%M%S)"
  cp "$USER_RULES" "$BAK"
  step "Backed up your current rules to: $BAK"
fi

cp "$STARTER" "$USER_RULES"
step "Restored starter rules ($(grep -c '^- ' "$STARTER") rules)"

cat <<EOF

✓ Done. Re-running categorization with the starter rules now…
  (Run refresh.sh, or just say "refresh" to the assistant, to apply.)

EOF
