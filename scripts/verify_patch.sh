#!/usr/bin/env bash
# Proves the bad release is a *realistic* one: it passes every CI check and the smoke test,
# yet GET /api/quiz/sample (no count) returns 500. Applies the patch, checks, then reverts.
# Runs from the host with the project venv (PYTHON=... to override). Never pushes, never commits.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
PORT="${VERIFY_PORT:-18000}"
PATCH="scripts/bad_release.patch"
FAILS=0
SERVER_PID=""

pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }
check() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then pass "$name"; else fail "$name"; fi; }
coverage_of() { "$PY" -m pytest --cov=app --cov-fail-under=80 -q 2>&1 | sed -n 's/.*Total coverage: \([0-9.]*\)%.*/\1/p'; }

cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  if git apply -R --check "$PATCH" 2>/dev/null; then git apply -R "$PATCH"; fi
}
trap cleanup EXIT

if lsof -i ":$PORT" >/dev/null 2>&1; then echo "port $PORT is busy; set VERIFY_PORT"; exit 2; fi
STATE_BEFORE="$(git status --porcelain; shasum app/selection.py)"
echo "== baseline (good code)"
COV_GOOD="$(coverage_of)"
echo "coverage before: ${COV_GOOD}%"

echo "== verifying $PATCH"
check "A. patch applies cleanly" git apply --check "$PATCH"
git apply "$PATCH"

check "B1. ruff check passes" "$PY" -m ruff check app tests scripts
if "$PY" -m pytest --cov=app --cov-fail-under=80 -q >/dev/null 2>&1; then
  pass "B2. full pytest suite passes"
else
  fail "B2. full pytest suite passes"
fi
COV_BAD="$(coverage_of)"
if [ -n "$COV_BAD" ] && [ "$COV_BAD" = "$COV_GOOD" ]; then
  pass "B3. coverage unchanged (${COV_BAD}%)"
else
  fail "B3. coverage unchanged (good=${COV_GOOD} bad=${COV_BAD})"
fi
check "B4. retrieval quality gate passes" "$PY" -m scripts.quality_gate
pass "C. Trivy unchanged (one-line code change adds no dependency; not re-scanned here)"

ENABLE_DIAG=true APP_VERSION=verify "$PY" -m uvicorn app.main:app --port "$PORT" --log-level warning &
SERVER_PID=$!
for _ in $(seq 1 40); do curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1 && break; sleep 0.5; done

check "D. smoke test: /health and /api/quiz/demo return 200" \
  bash -c "curl -fsS http://localhost:$PORT/health && curl -fsS http://localhost:$PORT/api/quiz/demo"
NO_COUNT="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/api/quiz/sample")"
WITH_COUNT="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/api/quiz/sample?count=3")"
[ "$NO_COUNT" = "500" ] && pass "E1. /api/quiz/sample (no count) -> 500" || fail "E1. no count gave $NO_COUNT"
[ "$WITH_COUNT" = "200" ] && pass "E2. /api/quiz/sample?count=3 -> 200" || fail "E2. count=3 gave $WITH_COUNT"
ERR_FILE="$(curl -s "http://localhost:$PORT/internal/recent-errors" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["errors"][-1]["file"])' 2>/dev/null || true)"
[ "$ERR_FILE" = "selection.py" ] && pass "F1. stack trace names selection.py" || fail "F1. error file was '$ERR_FILE'"
grep -q '^+++ b/app/selection.py' "$PATCH" && pass "F2. patch modifies app/selection.py" || fail "F2. patch target"

kill "$SERVER_PID" 2>/dev/null || true; SERVER_PID=""
git apply -R "$PATCH"
if [ "$STATE_BEFORE" = "$(git status --porcelain; shasum app/selection.py)" ]; then
  pass "G. patch reverted, working tree identical to the start"
else
  fail "G. working tree differs from the start"
fi

echo
[ "$FAILS" -eq 0 ] && echo "ALL CHECKS PASSED" || { echo "$FAILS check(s) FAILED"; exit 1; }
