#!/usr/bin/env bash
# Replay a recorded incident through the copilot's real analysis code (demo safety net).
# Usage: fake_alert.sh [bad_release|chaos_after_docs_deploy|...]
set -euo pipefail
curl -fsS -X POST "localhost:8001/dev/replay/${1:-bad_release}"
echo
