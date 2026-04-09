#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

compose_files=(-f compose.yml)
if [[ "$(uname -s)" == "Darwin" && -f compose.macos.yml ]]; then
  compose_files+=(-f compose.macos.yml)
fi

docker compose "${compose_files[@]}" down
