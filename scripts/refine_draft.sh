#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Использование: ./scripts/refine_draft.sh <task-id> [instructions] [draft-path]"
  exit 1
fi

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s' "${value}"
}

TASK_ID="$1"
INSTRUCTIONS_RAW="${2:-Уточни формулировки, добавь конкретику и проверяемость.}"
DRAFT_PATH_RAW="${3:-}"

INSTRUCTIONS="$(json_escape "${INSTRUCTIONS_RAW}")"
DRAFT_PATH="$(json_escape "${DRAFT_PATH_RAW}")"

if [[ -n "${DRAFT_PATH_RAW}" ]]; then
  PAYLOAD="{\"task_id\":\"${TASK_ID}\",\"instructions\":\"${INSTRUCTIONS}\",\"draft_path\":\"${DRAFT_PATH}\"}"
else
  PAYLOAD="{\"task_id\":\"${TASK_ID}\",\"instructions\":\"${INSTRUCTIONS}\"}"
fi

curl -sS -X POST "http://localhost:8000/refine" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}"
echo
