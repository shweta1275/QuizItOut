#!/usr/bin/env bash
# Fix-forward after a rollback: revert the bad commit so the next push does not redeploy it.
# Commits locally and stops. YOU push: it never pushes by itself.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -n "$(git status --porcelain)" ]; then echo "Working tree is not clean; commit or stash first."; exit 1; fi
SHA="$(git log --format=%h -n 1 --grep='^fix: simplify count handling$')"
if [ -z "$SHA" ]; then echo "No 'fix: simplify count handling' commit found."; exit 1; fi
git revert --no-edit "$SHA"
echo "Reverted $SHA locally."
echo "Now run: git push"
