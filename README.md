# analytics-ai-kit

Локальная система для аналитиков: из `task.md` и вложений автоматически собрать первый черновик документа, показать gaps и поддержать refine.

## Что делает система

- читает `task.md`
- автоматически определяет тип документа (`FT` или `NFT`)
- автоматически выбирает секции
- для каждой секции собирает context pack
- генерирует черновик по секциям
- собирает итоговый markdown-документ
- делает gap analysis
- поддерживает refine существующего draft

## Стек (локально)

- Docker Compose
- Ollama
- Qdrant
- `rag-service` (Python + FastAPI)
- VS Code + Continue как интерфейс аналитика

Open WebUI не используется.

## Структура проекта

```text
tasks/
  inbox/<task-id>/
    task.md
    attachments/

artifacts/
  drafts/
  reviews/
  context_packs/

docs/
  input/
  examples/
  glossary/
  templates/
    sections/
      ft/
      nft/
    prompts/
```

## Быстрый старт

1. Подготовить `.env`:

```bash
cp .env.example .env
```

2. Поднять сервисы:

```bash
docker compose up -d --build
```

3. Установить модели Ollama:

```bash
./scripts/pull-models.sh
```

4. Проиндексировать общий контекст:

```bash
./scripts/reindex.sh
```

## UX аналитика (только 3 шага)

1. Создать `task.md`
2. Добавить файлы в `attachments` (если есть)
3. Выполнить команду в Continue/Terminal

### Шаг 1. Создать задачу

```bash
mkdir -p tasks/inbox/task-001/attachments
cp tasks/task.md.template tasks/inbox/task-001/task.md
```

Заполните `tasks/inbox/task-001/task.md`.

### Шаг 2. Добавить вложения

Положите 1..N файлов в:

```text
tasks/inbox/task-001/attachments/
```

Поддерживаются: `.md`, `.txt`, `.docx`, `.pdf`.

### Шаг 3. Запустить pipeline

Анализ задачи:

```bash
./scripts/analyze_task.sh task-001
```

Создать draft:

```bash
./scripts/create_draft.sh task-001
```

Сделать gap analysis:

```bash
./scripts/gap_analysis.sh task-001
```

Refine draft:

```bash
./scripts/refine_draft.sh task-001 "Уточни интеграции и критерии валидации"
```

## Где результаты

- Draft: `artifacts/drafts/<task-id>/..._draft_*.md`
- Gap analysis: `artifacts/reviews/<task-id>/..._gaps.md`
- Context packs: `artifacts/context_packs/<task-id>/..._<section>.json`
- Refined draft: `artifacts/drafts/<task-id>/..._refined_*.md`

## API endpoints

Существующие:

- `GET /health`
- `POST /reindex`
- `POST /search`

Новые:

- `POST /analyze-task`
- `POST /build-context-pack`
- `POST /draft`
- `POST /gap-analysis`
- `POST /refine`

## Routing и контекст

Система использует два уровня контекста:

1. Global context:
   - `docs/input`
   - `docs/examples`
   - `docs/glossary`
2. Task context:
   - `tasks/inbox/<task-id>/task.md`
   - `tasks/inbox/<task-id>/attachments/*`

Для каждой секции применяется routing-логика с приоритетом релевантных источников (например, `business_requirements` тянет `task + product docs + examples`, `logging/audit` — `task + security/NFT docs + examples`).

## Полезные скрипты

- `./scripts/pull-models.sh`
- `./scripts/reindex.sh`
- `./scripts/analyze_task.sh <task-id>`
- `./scripts/create_draft.sh <task-id>`
- `./scripts/gap_analysis.sh <task-id> [draft-path]`
- `./scripts/refine_draft.sh <task-id> [instructions] [draft-path]`
- `./scripts/healthcheck.sh`
