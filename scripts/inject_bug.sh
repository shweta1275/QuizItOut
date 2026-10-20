#!/usr/bin/env bash
# Demo helper: ship the "bad release" (passes CI, breaks /api/quiz/sample without count).
# Commits locally and stops. YOU push: it never pushes by itself.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -n "$(git status --porcelain)" ]; then echo "Working tree is not clean; commit or stash first."; exit 1; fi
git apply scripts/bad_release.patch
git add app/selection.py
git commit -q -m "fix: simplify count handling"
echo "Committed the bad release locally."
echo "Now run: git push"
