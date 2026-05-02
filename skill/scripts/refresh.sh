#!/bin/bash
# refresh.sh — orchestrate the full pipeline. Spec §6.2 (build) / §14 (refresh).
#
# Usage:
#   refresh.sh [--auto-confirm]
#
# Runs (each step calls the python script of the same name):
#   1. classify  → sort inbox into 01..05 buckets
#   2. dedupe    → flag exact dups + content overlaps
#   3. normalize → produce transactions_normalized.csv
#   4. fx_fetch  → warm cache for the date range we're working with
#   5. categorize → produce transactions_tagged.csv + monthly_actuals.csv
#   6. sanity    → hard floors + interactive gate (writes sanity_confirmed.json)
#   7. build_site → populate the site/ folder
#
# Skips publish — that's a separate explicit step (see publish.sh) so the user
# always confirms before anything goes online.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"

# Default to the workspace venv's Python so the script works from any cwd,
# without relying on a venv-activation wrapper. Falls back to system python3
# if the venv is missing (rare — installer creates it). PYTHON env var
# overrides for testing.
if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -x "$WS/.venv/bin/python" ]; then
  PY="$WS/.venv/bin/python"
else
  PY="python3"
fi

# Bootstrap a workspace config.yaml from the skill's example if missing.
# Lets users edit feedback.endpoint_url, advisor.feedback_email, etc.
# without having to know where the example lives.
if [ ! -f "$WS/config.yaml" ] && [ -f "$SKILL_ROOT/config.example.yaml" ]; then
  mkdir -p "$WS"
  cp "$SKILL_ROOT/config.example.yaml" "$WS/config.yaml"
  echo "▸ Created $WS/config.yaml from the skill's example."
  echo "  Edit it to point product feedback at your team."
fi

AUTO_CONFIRM=""
for arg in "$@"; do
  case "$arg" in
    --auto-confirm) AUTO_CONFIRM="--auto-confirm" ;;
  esac
done

step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }

step "1/7 Sorting inbox files"
$PY "$SCRIPT_DIR/classify.py"

step "2/7 Checking for duplicates"
$PY "$SCRIPT_DIR/dedupe.py"

step "3/7 Normalizing dates, currencies, and signs"
$PY "$SCRIPT_DIR/normalize.py"

# Detect the date range from the normalized output, then warm FX cache for it.
NORM_CSV="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}/pipeline/output/transactions_normalized.csv"
if [ -f "$NORM_CSV" ]; then
  START=$($PY -c "import csv; rows=list(csv.DictReader(open('$NORM_CSV'))); print(min(r['date'] for r in rows) if rows else '')")
  END=$($PY -c "import csv; rows=list(csv.DictReader(open('$NORM_CSV'))); print(max(r['date'] for r in rows) if rows else '')")
  if [ -n "$START" ]; then
    step "4/7 Fetching exchange rates for $START → $END"
    $PY "$SCRIPT_DIR/fx_fetch.py" --base EUR --pairs USD,GBP --start "$START" --end "$END" || true
  fi
fi

step "5/7 Categorizing transactions"
$PY "$SCRIPT_DIR/categorize.py"

step "6/7 Sanity check"
$PY "$SCRIPT_DIR/sanity.py" $AUTO_CONFIRM

step "7/7 Building dashboard"
$PY "$SCRIPT_DIR/build_site.py"

# Local-first default (Strategic #2): open the dashboard in the user's
# browser as soon as the build succeeds. Sharing via here.now is opt-in
# (run publish.sh when the user explicitly says "share with my advisor").
# Unless --no-open was passed (CI / scripted runs).
NO_OPEN=0
for arg in "$@"; do case "$arg" in --no-open) NO_OPEN=1 ;; esac; done

printf '\n\033[32m\033[1m✓ Done.\033[0m\n'
if [ "$NO_OPEN" = "0" ]; then
  "$SCRIPT_DIR/view-local.sh"
else
  printf '   Open %s/site/index.html in your browser to review.\n' "$WS"
fi
printf '\n   To share with your advisor or family (puts it online behind a passcode):\n'
printf '       %s/publish.sh\n\n' "$SCRIPT_DIR"
