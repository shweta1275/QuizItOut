#!/usr/bin/env bash
set -euo pipefail
curl -fsS -X POST localhost:8000/admin/chaos -H 'content-type: application/json' -d '{"fail_rate":0.0}'
echo
