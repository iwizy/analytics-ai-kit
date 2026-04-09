$ErrorActionPreference = "Stop"

$ollamaUrl = "http://127.0.0.1:11434"
$models = @(
  "nomic-embed-text",
  "qwen2.5:7b",
  "qwen3-coder:30b",
  "gpt-oss:20b"
)

Write-Host "[1/3] Проверка Ollama CLI..."
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  throw "Ошибка: команда ollama не найдена. Установите Ollama и повторите запуск."
}

Write-Host "[2/3] Проверка доступности Ollama API ($ollamaUrl)..."
try {
  Invoke-RestMethod -Method GET -Uri "$ollamaUrl/api/tags" | Out-Null
}
catch {
  throw "Ошибка: Ollama API недоступен. Запустите Ollama и повторите попытку."
}
Write-Host "Ollama API доступен."

Write-Host "[3/3] Загрузка моделей..."
foreach ($model in $models) {
  Write-Host "→ Pull: $model"
  ollama pull $model
  if ($LASTEXITCODE -ne 0) {
    throw "Ошибка загрузки модели: $model"
  }
  Write-Host "  OK: $model"
}

Write-Host ""
Write-Host "Текущий список моделей:"
ollama list
Write-Host "Готово: все обязательные модели установлены."
