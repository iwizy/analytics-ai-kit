#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Использование: ./scripts/gap_analysis.sh <task-id> [draft-path]"
  exit 1
fi

TASK_ID="$1"
DRAFT_PATH="${2:-}"

if [[ -n "${DRAFT_PATH}" ]]; then
  PAYLOAD="{\"task_id\":\"${TASK_ID}\",\"draft_path\":\"${DRAFT_PATH}\"}"
else
  PAYLOAD="{\"task_id\":\"${TASK_ID}\"}"
fi

curl -sS -X POST "http://localhost:8000/gap-analysis" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}"
echo
