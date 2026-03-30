#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Использование: ./scripts/run_pipeline.sh <task-id> [--type ft|nft] [--no-gaps] [--refine] [--refine-instructions "..."]

Параметры:
  --type ft|nft            Форсировать тип документа.
  --no-gaps                 Пропустить gap-analysis.
  --refine                  Запустить refine после draft.
  --refine-instructions     Инструкции для refine (по умолчанию берутся из скрипта).
  --draft-model             Модель для draft (по умолчанию из настроек rag-service).
  --gap-model               Модель для gap-analysis (по умолчанию из настроек rag-service).
  --refine-model            Модель для refine (по умолчанию из настроек rag-service).
  --wait                    Подождать завершения выполнения и печатать статусы.
USAGE
}

TASK_ID=""
DOC_TYPE=""
RUN_GAPS=true
RUN_REFINE=false
REFINE_INSTRUCTIONS="Уточни недостающие допущения и добавь проверки"
DRAFT_MODEL=""
GAP_MODEL=""
REFINE_MODEL=""
WAIT_MODE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --type)
      DOC_TYPE="$2"
      shift 2
      ;;
    --no-gaps)
      RUN_GAPS=false
      shift
      ;;
    --refine)
      RUN_REFINE=true
      shift
      ;;
    --refine-instructions)
      REFINE_INSTRUCTIONS="$2"
      shift 2
      ;;
    --draft-model)
      DRAFT_MODEL="$2"
      shift 2
      ;;
    --gap-model)
      GAP_MODEL="$2"
      shift 2
      ;;
    --refine-model)
      REFINE_MODEL="$2"
      shift 2
      ;;
    --wait)
      WAIT_MODE=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      echo "Неизвестный флаг: $1"
      usage
      exit 1
      ;;
    *)
      if [[ -z "$TASK_ID" ]]; then
        TASK_ID="$1"
      else
        echo "Лишний аргумент: $1"
        usage
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$TASK_ID" ]]; then
  usage
  exit 1
fi

build_payload() {
  python3 - <<'PY'
import json
import os

payload = {
    "task_id": os.environ["TASK_ID"],
    "run_gaps": os.environ["RUN_GAPS"].lower() == "true",
    "run_refine": os.environ["RUN_REFINE"].lower() == "true",
    "async_mode": True,
    "refine_instructions": os.environ["REFINE_INSTRUCTIONS"],
}

for key in ["DOC_TYPE", "DRAFT_MODEL", "GAP_MODEL", "REFINE_MODEL"]:
    value = os.environ.get(key, "")
    if value:
        if key == "DOC_TYPE":
            payload["force_document_type"] = value
        elif key == "DRAFT_MODEL":
            payload["draft_model"] = value
        elif key == "GAP_MODEL":
            payload["gap_model"] = value
        elif key == "REFINE_MODEL":
            payload["refine_model"] = value

print(json.dumps(payload, ensure_ascii=False))
PY
}

export TASK_ID DOC_TYPE RUN_GAPS RUN_REFINE REFINE_INSTRUCTIONS DRAFT_MODEL GAP_MODEL REFINE_MODEL
PAYLOAD="$(build_payload)"

RESPONSE="$(curl -sS -X POST "http://localhost:8000/run-pipeline" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")"

echo "$RESPONSE"

if [[ "$WAIT_MODE" == true ]]; then
  RUN_ID="$(python3 - <<'PY'
import json
import sys

payload = json.loads(sys.stdin.read() or "{}")
print(payload.get("pipeline", {}).get("run_id", ""))
PY <<<"$RESPONSE")"

  if [[ -z "$RUN_ID" ]]; then
    echo "Не удалось получить run_id, ожидание невозможно"
    exit 1
  fi

  echo "Ожидание завершения run_id=${RUN_ID}"
  while true; do
    STATUS_RESPONSE="$(curl -sS -X GET "http://localhost:8000/pipeline-status/${TASK_ID}/${RUN_ID}")"
    STATE="$(python3 - <<'PY'
import json
import sys

payload = json.loads(sys.stdin.read() or "{}")
print(payload.get("pipeline", {}).get("state", ""))
PY <<<"$STATUS_RESPONSE")"

    echo "state=${STATE}"
    echo "$STATUS_RESPONSE" | python3 -m json.tool || true

    if [[ "$STATE" == "completed" || "$STATE" == "failed" ]]; then
      break
    fi
    sleep 2
  done
fi
