#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Использование: ./scripts/analyze_task.sh <task-id>"
  exit 1
fi

TASK_ID="$1"

curl -sS -X POST "http://localhost:8000/analyze-task" \
  -H "Content-Type: application/json" \
  -d "{\"task_id\":\"${TASK_ID}\"}"
echo
