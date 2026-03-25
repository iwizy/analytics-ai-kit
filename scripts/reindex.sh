#!/usr/bin/env bash
set -e

echo "Starting reindex..."
curl -sS -X POST http://localhost:8000/reindex
echo
echo "Reindex finished."