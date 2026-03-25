#!/usr/bin/env bash
set -e

echo "Checking Ollama API..."
curl -fsS http://127.0.0.1:11434/api/tags > /dev/null
echo "Ollama API OK"

echo "Checking Qdrant..."
curl -fsS http://localhost:6333 > /dev/null
echo "Qdrant OK"

echo "Checking RAG service..."
curl -fsS http://localhost:8000/health > /dev/null
echo "RAG service OK"

echo "Checking Open WebUI..."
curl -fsS http://localhost:3000 > /dev/null
echo "Open WebUI OK"

echo "Installed Ollama models:"
ollama list || true

echo "All core services look healthy."