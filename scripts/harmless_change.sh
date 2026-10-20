#!/usr/bin/env bash
# Demo helper: a docs-only release (touches no code). Commits locally and stops. YOU push.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -n "$(git status --porcelain)" ]; then echo "Working tree is not clean; commit or stash first."; exit 1; fi
[ -f docs/CHANGELOG.md ] || printf '# Changelog\n\n' > docs/CHANGELOG.md
echo "- $(date '+%Y-%m-%d %H:%M:%S'): docs touched" >> docs/CHANGELOG.md
git add docs/CHANGELOG.md
git commit -q -m "docs: update changelog"
echo "Committed a docs-only change locally."
echo "Now run: git push"
