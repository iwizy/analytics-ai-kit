#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Использование: ./scripts/create_draft.sh <task-id> [ft|nft]"
  exit 1
fi

TASK_ID="$1"
DOC_TYPE="${2:-}"

if [[ -n "${DOC_TYPE}" ]]; then
  PAYLOAD="{\"task_id\":\"${TASK_ID}\",\"force_document_type\":\"${DOC_TYPE}\"}"
else
  PAYLOAD="{\"task_id\":\"${TASK_ID}\"}"
fi

curl -sS -X POST "http://localhost:8000/draft" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}"
echo
