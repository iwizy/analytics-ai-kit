#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"

compose_files=(-f compose.yml)
if [[ "$(uname -s)" == "Darwin" && -f compose.macos.yml ]]; then
  compose_files+=(-f compose.macos.yml)
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker не найден. Установите Docker Desktop и повторите попытку."
  exit 1
fi

echo "Поднимаю стек проекта..."
docker compose "${compose_files[@]}" up -d --build --remove-orphans

echo "Жду готовности backend..."
for _ in {1..120}; do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "Жду готовности frontend..."
for _ in {1..120}; do
  if curl -fsS "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if command -v open >/dev/null 2>&1; then
  open "http://localhost:${FRONTEND_PORT}"
fi

echo "Готово. Интерфейс: http://localhost:${FRONTEND_PORT}"
