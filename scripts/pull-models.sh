#!/usr/bin/env bash
set -e

echo "Pulling embedding model..."
ollama pull nomic-embed-text

echo "Pulling fast model..."
ollama pull qwen2.5:7b

echo "Pulling main model..."
ollama pull qwen3:14b

echo "Pulling heavy model..."
ollama pull gpt-oss:20b

echo "Done."