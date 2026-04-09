# analytics-ai-kit

Локальная система для системных аналитиков, которая автоматически строит черновики статьи по задаче из `task.md`, подбирает релевантные шаблоны секций, собирает контекст и генерирует `draft` + `gaps` + `refine`.

Стек локальный:

- Docker Compose
- Ollama
- Qdrant
- rag-service (FastAPI)
- UI в браузере (`http://localhost:8000/ui`)
- VS Code + Continue

Ограничения:

- Нет Open WebUI
- Нет внешних SaaS
- Код и комментарии на английском
- Тексты для пользователя и промпты на русском

## 1. Обязательная структура репозитория

```text
tasks/
  inbox/
    <task-id>/
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
  services/
  templates/
    sections/
      ft/
      nft/
    prompts/
```

- `tasks/inbox/<task-id>/task.md` — описание задачи.
- `tasks/inbox/<task-id>/attachments/` — 1..N вложений (pdf/docx/txt/md).
- `artifacts/*` — артефакты генерации.
- `docs/*` — общий контекст системы.
- `docs/services/<service>/...` — контекст по конкретному микросервису.

## 2. Как быстро запустить стек

```bash
docker compose up -d --build
```

```bash
./scripts/pull-models.sh
```

```bash
./scripts/reindex.sh
```

```bash
./scripts/healthcheck.sh
```

После этого UI должен открыться по `http://localhost:8000/ui`.

## 3. Установка и конфиг Continue

1. Установите в VS Code расширение **Continue**.
2. Откройте `Continue: Open Config File`.
3. Добавьте блок конфигурации моделей:

```yaml
models:
  - name: qwen3-coder-30b
    provider: ollama
    model: qwen3-coder:30b
    apiBase: http://127.0.0.1:11434
  - name: qwen2.5-7b
    provider: ollama
    model: qwen2.5:7b
    apiBase: http://127.0.0.1:11434
  - name: gpt-oss-20b
    provider: ollama
    model: gpt-oss:20b
    apiBase: http://127.0.0.1:11434

context:
  - provider: code
  - provider: docs
  - provider: folder
```

## 4. Как начать работу над новой статьей (без CLI)

### Шаг 1. Подготовить задачу

1. Откройте `http://localhost:8000/ui`.
2. Укажите `Task ID` (например, `operation-history-ft-v1`).
3. Нажмите `Загрузить шаблон task.md`.
4. Заполните минимум 5 блоков:
   - цель и ожидаемый результат,
   - бизнес-контекст,
   - исходные документы сервиса,
   - ограничения,
   - критерий готовности.

### Шаг 2. Подготовить контекст (микросервисно)

Система лучше работает, когда исходники есть в двух местах:

- task-контекст: `tasks/inbox/<task-id>/task.md` + `attachments/`
- микросервисный контекст: `docs/services/<service>/...`

Рекомендуемая вложенная структура для сервиса:

```text
docs/services/operation-history/
  00_service_overview.md
  20_business_requirements.md
  90_functional_requirements.md
  42_internal_integrations.md
  41_external_integrations.md
  50_non_functional_requirements.md
  63_kafka_topics.md
  80_deployment_scheme.md
```

Эти файлы можно быстро скопировать из `docs/templates/microservice/` и заполнить.

Вложения можно добавить через UI (`Attachments`) или напрямую в папку `tasks/inbox/<task-id>/attachments/`.

### Шаг 3. Проверить инфраструктуру

Нажмите в блоке `Operations`:

- `Update/Обновить Ops статус` — проверить Docker + сервисы + модели,
- `Скачать обязательные модели` — задать прогресс загрузки,
- `Запустить стек`/`Перезапустить стек`/`Остановить стек` — управление контейнерами (`qdrant`, `ollama`, `rag-service`).

### Шаг 4. Получить черновой draft

1. Нажмите `Create draft`.
2. При необходимости задайте `Тип документа` (`auto/ft/nft`).
3. Система:
   - анализирует задачу,
   - определяет тип и секции,
   - собирает `context pack` для каждой секции,
   - генерирует текст секционно,
   - собирает итоговый документ.
4. Артефакт сохранится в:

```text
artifacts/drafts/<task-id>/<timestamp>_draft_<ft|nft>.md
```

### Шаг 5. Получить gaps / вопросы

Нажмите `Gap analysis`.

Результат будет в:

```text
artifacts/reviews/<task-id>/<timestamp>_gaps.md
```

### Шаг 6. Refine

1. Заполните `Инструкции для refine`.
2. Нажмите `Refine draft`.
3. Система создаст новый refinement-файл и не перезатрёт предыдущий draft.

### Шаг 7. Полный pipeline в одном клике

`Run full pipeline` запускает все этапы последовательно:
- analyze
- draft
- gaps (по флагу `Запустить gap-analysis`)
- refine (по флагу `Запустить refine`)
- finalize

По завершению показывается прогресс и список артефактов.

### Шаг 8. Что именно делает система под капотом

- `task.md`, `docs/input`, `docs/examples`, `docs/glossary`, `docs/services/<service>` и `attachments` — это уровни контекста.
- Для каждого раздела выбирается отдельный шаблон секции.
- `context pack` собирается автоматически и хранится в `artifacts/context_packs/<task-id>/`.
- Генерация идёт секционно, без ручного выбора шаблонов и без ручного поиска контекста.

## 5. Поддержка PDF

Да, PDF как источник поддерживается:
- извлечение текста идёт на стороне rag-service через `pymupdf`.
- поддерживаемые расширения: `.md`, `.txt`, `.docx`, `.pdf`.

## 6. Scripts (для автотестирования и редких ручных запусков)

```bash
./scripts/analyze_task.sh <task-id>
./scripts/create_draft.sh <task-id> [ft|nft]
./scripts/gap_analysis.sh <task-id> [draft-path]
./scripts/refine_draft.sh <task-id> "Уточни ..."
./scripts/run_pipeline.sh <task-id> --wait
```

## 7. Endpoints

- `GET /health`
- `POST /search`
- `POST /reindex`
- `POST /analyze-task`
- `POST /build-context-pack`
- `POST /draft`
- `POST /gap-analysis`
- `POST /refine`
- `POST /run-pipeline`
- `GET /pipeline-status/{task_id}/{run_id}`
- `GET /ui`
- `GET /ui/task-template`
- `POST /ui/create-task`
- `POST /ui/upload-attachments/{task_id}`
- `GET /ui/state/{task_id}`
- `GET /ui/artifacts/{kind}/{task_id}/{filename}`
- `GET /ui/ops/status`
- `POST /ui/ops/containers/{action}` (`start|stop|restart`)
- `POST /ui/ops/models/pull`
- `GET /ui/ops/models/status`

## 8. Шаблоны и промпты

- `tasks/task.md.template` — минимальный шаблон для `task.md`.
- `docs/templates/sections/ft/*` — секционные шаблоны FT.
- `docs/templates/sections/nft/*` — секционные шаблоны NFT.
- `docs/templates/prompts/draft_ft.md` — промпт для секций FT.
- `docs/templates/prompts/draft_nft.md` — промпт для секций NFT.
- `docs/templates/prompts/gap_finder.md` — промпт для gap-анализa.
- `docs/templates/prompts/refine.md` — промпт для refine.
- `docs/templates/microservice/*` — шаблоны для микросервисного набора документов.
