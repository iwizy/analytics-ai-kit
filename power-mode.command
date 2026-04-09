#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
TASK_ID="${1:-}"

if ! command -v code >/dev/null 2>&1; then
  echo "Команда 'code' не найдена. Включите Shell Command в VS Code и повторите."
  exit 1
fi

if [[ -n "$TASK_ID" ]]; then
  HANDOFF_FILE="$(find "$ROOT_DIR/artifacts/handoffs/$TASK_ID" -type f -name '*_handoff.md' 2>/dev/null | sort | tail -n 1 || true)"
  WORKING_COPY_FILE="$(find "$ROOT_DIR/artifacts/drafts/$TASK_ID" -type f -name '*_continue_workspace_*.md' 2>/dev/null | sort | tail -n 1 || true)"

  if [[ -n "$HANDOFF_FILE" && -n "$WORKING_COPY_FILE" ]]; then
    code "$ROOT_DIR" "$HANDOFF_FILE" "$WORKING_COPY_FILE"
    exit 0
  fi

  if [[ -n "$HANDOFF_FILE" ]]; then
    code "$ROOT_DIR" "$HANDOFF_FILE"
    exit 0
  fi
fi

code "$ROOT_DIR"
