# analytics-ai-kit

Локальный AI-контур для работы с аналитической документацией:
- хранение контекста в Qdrant
- локальные модели через Ollama
- индексация документов через RAG service
- локальный UI через Open WebUI

---

## Что уже реализовано

- Индексация документов из локальных папок
- Поддержка:
  - `.md`
  - `.txt`
  - `.docx`
  - `.pdf`
- Разбиение текста на чанки
- Генерация embedding через Ollama
- Загрузка embedding и metadata в Qdrant
- Семантический поиск по индексированным документам
- Локальный запуск через Docker Compose
- macOS-сценарий с нативным Ollama

---

## Архитектура

### Сервисы
- `qdrant` — векторная база для хранения контекста
- `open-webui` — локальный веб-интерфейс
- `rag-service` — backend для индексации и поиска
- `ollama` — запускается нативно на macOS

### Папки с документами
- `docs/input` — основная проектная документация
- `docs/templates` — шаблоны ФТ / НФТ
- `docs/glossary` — словарь терминов
- `docs/examples` — хорошие примеры документов

### Persistent storage
- `storage/qdrant`
- `storage/open-webui`
- `storage/ollama`

---

## Требования

### macOS
- Docker Desktop
- Ollama (нативно)
- Git
- Terminal / iTerm

---

## Установка

### 1. Установить Docker Desktop
Скачать и установить Docker Desktop для macOS.

Проверка:
```bash
docker --version
docker compose version