#!/usr/bin/env bash
# 30% of /api/quiz/sample requests fail (simulated upstream outage, not caused by any release).
set -euo pipefail
curl -fsS -X POST localhost:8000/admin/chaos -H 'content-type: application/json' -d '{"fail_rate":0.3}'
echo
