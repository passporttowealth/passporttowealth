#!/bin/bash
# publish-landing.sh — publish the landing page to here.now with build-time
# substitutions baked in.
#
# Why this exists: installer/index.html has a `{{BUILD_STAMP}}` placeholder
# in the footer that should resolve to a real UTC timestamp on every publish
# (so visitors can tell when the live page was last refreshed). We don't
# want that placeholder substituted in the source file (would create churn
# on every publish), so we copy installer/ to a temp build dir, do the
# substitution there, and publish that.
#
# Usage:
#   bash installer/publish-landing.sh
#
# Requires: the here-now skill installed locally with credentials saved.
#
# Copyright © 2026 Passport to Wealth. All rights reserved.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HERENOW_PUBLISH="${HERENOW_PUBLISH_SCRIPT:-${HOME}/.claude/skills/here-now/scripts/publish.sh}"
SLUG="${LANDING_SLUG:-sandy-delta-dc3r}"

[ -x "$HERENOW_PUBLISH" ] || {
  echo "ERROR: here-now publish script not found at $HERENOW_PUBLISH" >&2
  echo "       Install it with: npx skills add heredotnow/skill --skill here-now -g" >&2
  exit 1
}

BUILD_DIR="$(mktemp -d -t passport-landing-XXXXXX)"
trap 'rm -rf "$BUILD_DIR"' EXIT

# Regenerate /docs page from current install scripts so the live page
# never drifts. CI also runs this in --check mode to gate PRs.
echo "▸ Rebuilding /docs from install scripts"
python3 "$REPO_ROOT/installer/build_docs.py"

# Mirror the installer/ tree, dereferencing any symlinks so the publish
# bundle has real files (here-now's publish.sh skips symlinks).
# rsync -L turns symlinks into copies of their targets.
rsync -aL --exclude '.herenow' --exclude '.DS_Store' \
  "$SCRIPT_DIR/" "$BUILD_DIR/"

# Substitute {{BUILD_STAMP}} with current UTC stamp (yyyymmddHHMMSS, same
# format as the install_started telemetry build_stamp so the two correlate).
STAMP="$(date -u +%Y%m%d%H%M%S)"
# macOS sed needs an empty -i suffix; GNU sed doesn't. Use a temp + mv to
# stay portable.
sed "s/{{BUILD_STAMP}}/$STAMP/g" "$BUILD_DIR/index.html" > "$BUILD_DIR/index.html.tmp"
mv "$BUILD_DIR/index.html.tmp" "$BUILD_DIR/index.html"

# Sanity-check the substitution actually fired.
if grep -q '{{BUILD_STAMP}}' "$BUILD_DIR/index.html"; then
  echo "ERROR: BUILD_STAMP substitution failed — placeholder still present" >&2
  exit 1
fi

echo "▸ Built landing bundle at $BUILD_DIR"
echo "  BUILD_STAMP = $STAMP"
echo "  Publishing to slug: $SLUG"

# Carry over the .herenow state from the source dir so the publish script
# knows the existing slug/claim. (We excluded it from the rsync above so
# the source state stays under source control.)
if [ -d "$SCRIPT_DIR/.herenow" ]; then
  cp -R "$SCRIPT_DIR/.herenow" "$BUILD_DIR/.herenow"
fi

bash "$HERENOW_PUBLISH" "$BUILD_DIR" --slug "$SLUG" --client claude-code

# Sync .herenow state back so future publishes see updated tokens (in case
# the publish rotated anything).
if [ -d "$BUILD_DIR/.herenow" ]; then
  cp -R "$BUILD_DIR/.herenow" "$SCRIPT_DIR/"
fi

echo "✓ Landing published. Visit https://passporttowealth.app/ to verify."
