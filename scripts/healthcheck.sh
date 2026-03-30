#!/usr/bin/env bash
set -euo pipefail

echo "Проверка Ollama API..."
curl -fsS http://127.0.0.1:11434/api/tags > /dev/null
echo "Ollama API: OK"

echo "Проверка Qdrant..."
curl -fsS http://localhost:6333 > /dev/null
echo "Qdrant: OK"

echo "Проверка RAG service..."
curl -fsS http://localhost:8000/health > /dev/null
echo "RAG service: OK"

echo "Проверка новых workflow endpoints..."
status_code="$(
  curl -sS -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/analyze-task \
    -H "Content-Type: application/json" \
    -d '{"task_id":"healthcheck-sample"}' || true
)"

if [[ "${status_code}" != "200" && "${status_code}" != "400" ]]; then
  echo "Проверка workflow endpoints не пройдена, HTTP статус: ${status_code}"
  exit 1
fi

echo "Workflow endpoints доступны (HTTP ${status_code})"

echo "Проверка веб-интерфейса аналитика..."
ui_status="$(curl -sS -o /dev/null -w "%{http_code}" http://localhost:8000/ui || true)"
if [[ "${ui_status}" != "200" ]]; then
  echo "UI недоступен, HTTP статус: ${ui_status}"
  exit 1
fi
echo "UI доступен (HTTP ${ui_status})"

echo "Проверка Ops endpoints..."
ops_status="$(curl -sS -o /dev/null -w "%{http_code}" http://localhost:8000/ui/ops/status || true)"
if [[ "${ops_status}" != "200" ]]; then
  echo "Ops status endpoint недоступен, HTTP статус: ${ops_status}"
  exit 1
fi
echo "Ops status endpoint: OK (HTTP ${ops_status})"

echo "Установленные модели Ollama:"
ollama list || true

echo "Базовые сервисы доступны."
