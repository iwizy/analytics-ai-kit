Write-Host "Pulling embedding model..."
ollama pull nomic-embed-text

Write-Host "Pulling fast model..."
ollama pull qwen2.5:7b

Write-Host "Pulling main model..."
ollama pull qwen3:14b

Write-Host "Pulling heavy model..."
ollama pull gpt-oss:20b

Write-Host "Done."