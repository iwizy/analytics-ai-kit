#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"
mkdir -p "$ROOT_DIR/storage/team-exchange"

HOST_OS_NAME="linux"
if [[ "$(uname -s)" == "Darwin" ]]; then
  HOST_OS_NAME="macos"
fi

if [[ -n "${HOME:-}" ]]; then
  CONTINUE_CONFIG_HOST_DIR="$HOME/.continue"
  mkdir -p "$CONTINUE_CONFIG_HOST_DIR"
  CONTINUE_CONFIG_HOST_PATH_LABEL="$CONTINUE_CONFIG_HOST_DIR/config.yaml"
else
  CONTINUE_CONFIG_HOST_DIR="$ROOT_DIR/storage/continue-empty"
  mkdir -p "$CONTINUE_CONFIG_HOST_DIR"
  CONTINUE_CONFIG_HOST_PATH_LABEL="~/.continue/config.yaml"
fi

export HOST_OS_NAME
export CONTINUE_CONFIG_HOST_DIR
export CONTINUE_CONFIG_HOST_PATH_LABEL

ENVIRONMENT_SETTINGS_FILE="$ROOT_DIR/storage/rag-service/environment/settings.json"
TEAM_EXCHANGE_HOST_DIR="$ROOT_DIR/storage/team-exchange"
TEAM_EXCHANGE_HOST_PATH_LABEL="$TEAM_EXCHANGE_HOST_DIR"
if [[ -f "$ENVIRONMENT_SETTINGS_FILE" ]]; then
  configured_exchange_dir="$(python3 - <<'PY' "$ENVIRONMENT_SETTINGS_FILE" "$ROOT_DIR"
import json
import os
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
root_dir = Path(sys.argv[2])
try:
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
except Exception:
    payload = {}
configured = str(payload.get("exchange_folder") or "").strip()
if configured:
    resolved = Path(os.path.expanduser(configured))
    if not resolved.is_absolute():
        resolved = root_dir / resolved
    print(resolved)
PY
)"
  if [[ -n "${configured_exchange_dir:-}" ]]; then
    TEAM_EXCHANGE_HOST_DIR="$configured_exchange_dir"
    TEAM_EXCHANGE_HOST_PATH_LABEL="$configured_exchange_dir"
  fi
fi
mkdir -p "$TEAM_EXCHANGE_HOST_DIR"
export TEAM_EXCHANGE_HOST_DIR
export TEAM_EXCHANGE_HOST_PATH_LABEL

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
  frontend_status="$(docker compose "${compose_files[@]}" ps --format json frontend 2>/dev/null | tr -d '\n')"
  if [[ "$frontend_status" == *"restarting"* ]] || [[ "$frontend_status" == *"exited"* ]]; then
    echo "Frontend не поднялся. Последние логи:"
    docker compose "${compose_files[@]}" logs --tail=120 frontend || true
    exit 1
  fi
  sleep 2
done

if ! curl -fsS "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1; then
  echo "Frontend не ответил вовремя. Последние логи:"
  docker compose "${compose_files[@]}" logs --tail=120 frontend || true
  exit 1
fi

CACHE_BUSTER="$(date +%s)"
if command -v open >/dev/null 2>&1; then
  open "http://localhost:${FRONTEND_PORT}/?v=${CACHE_BUSTER}"
fi

echo "Готово. Интерфейс: http://localhost:${FRONTEND_PORT}"
