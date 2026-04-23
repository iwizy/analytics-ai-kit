# analytics-ai-kit

Локальная on-prem система для системных аналитиков.

Она помогает:

- подготовить задачу и контекст,
- импортировать статьи и документы из Confluence и файлов,
- собрать дерево Confluence-страниц в общий контекст проекта,
- собрать `draft + gaps + refine`,
- подготовить handoff для `VS Code + Continue`,
- обмениваться общим контекстом между аналитиками без облака и без `git`,
- проводить отдельное `ревью аналитики` по готовой статье.

## Что внутри

- `FastAPI` backend в `services/rag-service`
- `Ant Design Pro` frontend в `frontend`
- `Ollama` для локальных моделей
- `Qdrant` для локального контекстного поиска
- `Playwright` для чтения закрытого Confluence
- `VS Code + Continue` для power mode
- `Syncthing` как рекомендованный транспорт для общей папки обмена

## Основные разделы UI

- `Подготовка окружения`
- `Подготовка статьи`
- `Модели и контекст`
- `Сбор контекста`
- `Ревью аналитики`
- `Обмен контекстом`

## Быстрый запуск

Запуск:

```bash
./start.command
```

Остановка:

```bash
./stop.command
```

После запуска:

- backend: [http://localhost:8000](http://localhost:8000)
- frontend: [http://localhost:3001](http://localhost:3001)

## Что нужно установить на машину аналитика

Обязательно:

- `Docker Desktop`
- `Ollama`
- `VS Code`
- расширение `Continue`

Если нужен обмен между аналитиками без сервера:

- `Syncthing`

## Структура данных проекта

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
  handoffs/
  pipeline_runs/
  analytics_reviews/
  review_sources/

docs/
  input/
  examples/
  glossary/
  services/
  templates/
  shared-context/
    confluence_collections/
  continue/
```

### Что где лежит

- `tasks/inbox/<task-id>/task.md` — постановка задачи
- `tasks/inbox/<task-id>/attachments/` — локальные вложения и импортированные страницы Confluence
- `artifacts/drafts/<task-id>/` — черновики и refine-версии
- `artifacts/reviews/<task-id>/` — gaps и дополнительное review второго мнения
- `artifacts/context_packs/<task-id>/` — собранный контекст для секций
- `artifacts/handoffs/<task-id>/` — handoff в `VS Code + Continue`
- `artifacts/pipeline_runs/<task-id>/` — статусы pipeline
- `artifacts/review_sources/<review-id>/` — источники для отдельного ревью статьи
- `artifacts/analytics_reviews/<review-id>/` — отчёты `Ревью аналитики`
- `docs/shared-context/` — общий контекст, который можно публиковать коллегам через обмен
- `docs/shared-context/confluence_collections/` — собранные деревья Confluence-страниц
- `docs/templates/` — шаблоны секций и промпты

## Подготовка окружения

В разделе `Подготовка окружения` настраиваются:

- `Base URL Confluence`
- логин и пароль Confluence
- готовность `VS Code`
- готовность `Continue`
- готовность `Syncthing`
- путь к папке обмена
- профиль производительности машины
- дополнительные модели для ревью

### Continue

Репозиторный шаблон конфига:

- [docs/continue/config.template.yaml](/Users/iwizard/Dev/analytics-ai-kit/docs/continue/config.template.yaml)

Ожидаемые пути:

- macOS: `~/.continue/config.yaml`
- Windows: `%USERPROFILE%\.continue\config.yaml`

Для слабых машин используется `gemma4:e2b`, для стандартного профиля `qwen2.5-coder:14b`, для мощного — `qwen3-coder:30b`.

## Подготовка статьи

Раздел `Подготовка статьи` ведёт аналитика по шагам:

1. указать `Task ID`
2. подложить и сохранить `task.md`
3. добавить контекст файлами или ссылками
4. запустить `Analyze`
5. собрать `Draft`
6. найти `Gaps`
7. сделать `Refine`
8. подготовить `handoff`

### Источники

Поддерживаются:

- `.md`
- `.txt`
- `.docx`
- `.pdf`
- ссылки Confluence

Импортированные ссылки сохраняются локально как `.md` в `attachments`.

## Сбор контекста

Раздел `Сбор контекста` обходит корневую страницу Confluence и найденные дочерние ссылки.

Результат сохраняется в:

- `docs/shared-context/confluence_collections/<collection-id>/context_index.md`
- `docs/shared-context/confluence_collections/<collection-id>/manifest.json`
- `docs/shared-context/confluence_collections/<collection-id>/pages/`

После этого коллекцию можно передать коллегам через `Обмен контекстом`, выбрав категорию `Общий контекст`.

Подробности:

- [docs/context-collection.md](/Users/iwizard/Dev/analytics-ai-kit/docs/context-collection.md)

## Ревью аналитики

Раздел `Ревью аналитики` — это отдельный режим проверки уже готовой статьи.

Что умеет:

- принять статью файлом или ссылкой Confluence
- определить `FT` или `NFT` автоматически или взять тип вручную
- проверить соответствие шаблону
- найти противоречия
- найти недоработки и слабые разделы
- выдать рекомендации по доработке

Артефакты:

- `artifacts/review_sources/<review-id>/` — загруженные источники
- `artifacts/analytics_reviews/<review-id>/` — итоговые markdown-отчёты ревью

Подробности:

- [docs/review-analytics.md](/Users/iwizard/Dev/analytics-ai-kit/docs/review-analytics.md)

## Обмен контекстом без облака и без git

Раздел `Обмен контекстом` работает через отдельную папку обмена.

Рекомендуемая схема:

- `Syncthing` синхронизирует только папку обмена
- система публикует туда immutable `bundle`-пакеты
- коллеги видят новые пакеты и забирают их к себе кнопкой

Что публикуется:

- `docs/shared-context`
- `docs/templates`
- `docs/glossary`

Что не публикуется:

- секреты
- `Playwright` state
- `.continue/config.yaml`
- модели `Ollama`
- временные рабочие файлы

Подробности:

- [docs/team-exchange.md](/Users/iwizard/Dev/analytics-ai-kit/docs/team-exchange.md)

## Модели

### Профили производительности

`Лёгкий`

- обязательные: `nomic-embed-text`, `gemma4:e2b`

`Стандартный`

- обязательные: `nomic-embed-text`, `qwen2.5:7b`, `qwen2.5-coder:14b`

`Мощный`

- обязательные: `nomic-embed-text`, `qwen2.5:7b`, `qwen3-coder:30b`

### Дополнительные модели

Сейчас опционально поддерживается:

- `gpt-oss:20b`

Она нужна как второе мнение и дополнительная review-модель.

## Power mode

Когда UI уже подготовил задачу и handoff:

```bash
./power-mode.command <task-id>
```

Дальше аналитик работает в `VS Code + Continue` поверх созданной рабочей копии.

## Основные endpoints

Базовые:

- `GET /health`
- `POST /reindex`
- `POST /search`

По статье:

- `GET /ui/task-template`
- `POST /ui/create-task`
- `POST /ui/upload-attachments/{task_id}`
- `POST /ui/import-confluence`
- `GET /ui/state/{task_id}`
- `POST /analyze-task`
- `POST /draft`
- `POST /gap-analysis`
- `POST /refine`
- `POST /prepare-handoff`
- `POST /run-pipeline`
- `GET /pipeline-status/{task_id}/{run_id}`

По ревью аналитики:

- `GET /ui/review-state/{review_id}`
- `POST /ui/review-upload/{review_id}`
- `POST /ui/review-import-confluence`
- `POST /review-analytics`

По окружению и обмену:

- `GET /ui/environment-settings`
- `POST /ui/environment-settings`
- `GET /ui/exchange/status`
- `POST /ui/exchange/scan`
- `POST /ui/exchange/publish`
- `POST /ui/exchange/import`

По ops:

- `GET /ui/ops/status`
- `POST /ui/ops/containers/{action}`
- `POST /ui/ops/models/pull`
- `GET /ui/ops/models/status`

## Полезные документы

- [docs/continue/config.template.yaml](/Users/iwizard/Dev/analytics-ai-kit/docs/continue/config.template.yaml)
- [docs/team-exchange.md](/Users/iwizard/Dev/analytics-ai-kit/docs/team-exchange.md)
- [docs/review-analytics.md](/Users/iwizard/Dev/analytics-ai-kit/docs/review-analytics.md)
- [docs/services/README.md](/Users/iwizard/Dev/analytics-ai-kit/docs/services/README.md)
