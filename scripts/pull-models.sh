#!/usr/bin/env bash
set -euo pipefail

OLLAMA_URL="http://127.0.0.1:11434"
MODELS=(
  "nomic-embed-text"
  "qwen2.5:7b"
  "qwen2.5-coder:14b"
  "gpt-oss:20b"
)

echo "[1/3] Проверка Ollama CLI..."
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ошибка: команда ollama не найдена. Установите Ollama и повторите запуск."
  exit 1
fi

echo "[2/3] Проверка доступности Ollama API (${OLLAMA_URL})..."
if ! curl -fsS "${OLLAMA_URL}/api/tags" >/dev/null; then
  echo "Ошибка: Ollama API недоступен. Запустите Ollama и повторите попытку."
  exit 1
fi
echo "Ollama API доступен."

echo "[3/3] Загрузка моделей..."
for model in "${MODELS[@]}"; do
  echo "→ Pull: ${model}"
  if ollama pull "${model}"; then
    echo "  OK: ${model}"
  else
    echo "  FAIL: ${model}"
    exit 1
  fi
done

echo
echo "Текущий список моделей:"
ollama list || true

echo "Готово: все обязательные модели установлены."
