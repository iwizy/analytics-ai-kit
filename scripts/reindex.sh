#!/usr/bin/env bash
set -euo pipefail

echo "Запуск переиндексации..."
curl -sS -X POST http://localhost:8000/reindex
echo
echo "Переиндексация завершена."
