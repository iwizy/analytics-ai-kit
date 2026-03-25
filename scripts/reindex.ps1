Write-Host "Запуск переиндексации..."
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/reindex"
Write-Host "Переиндексация завершена."
