# analytics-ai-kit

Локальная AI-система для аналитиков, которая автоматически собирает черновик документа из `task.md` и вложений, затем делает gap-analysis и refine.

Система работает полностью локально и не требует внешних SaaS:
- Docker Compose
- Ollama
- Qdrant
- `rag-service` (FastAPI)
- VS Code + Continue

Open WebUI в этом процессе не используется.

## Что получает аналитик

После запуска пайплайна аналитик получает:
1. Первый draft документа.
2. Список gaps/вопросов на уточнение.
3. Возможность итеративного refine без переписывания текста с нуля.

## Главное: как работать аналитику (UI-first)

Ежедневный сценарий аналитика:
1. Создать/заполнить `task.md`.
2. Добавить 1-N файлов в `attachments`.
3. Нажать кнопки в локальном UI (`/ui`) и получить draft + gaps.

## Подготовка окружения (один раз)

Если стек уже поднят, переходите к разделу "Пошаговая работа аналитика".

1. Поднять сервисы:
```bash
docker compose up -d --build
```

2. Подтянуть модели в Ollama:
```bash
./scripts/pull-models.sh
```

Скрипт устанавливает:
- `nomic-embed-text`
- `qwen2.5:7b`
- `qwen3:14b`
- `gpt-oss:20b`

3. Проиндексировать общий контекст:
```bash
./scripts/reindex.sh
```

4. Проверить, что всё доступно:
```bash
./scripts/healthcheck.sh
```

5. Открыть интерфейс аналитика:
```text
http://localhost:8000/ui
```

## Пошаговая работа аналитика над статьей

### Шаг 1. Создайте задачу в UI

1. Откройте `http://localhost:8000/ui`.
2. Введите `Task ID` (пример: `operation-history-ft-v1`).
3. Нажмите `Load task template` (подставится минимальный шаблон).
4. Заполните текст и нажмите `Сохранить task.md`.

### Шаг 2. Заполните `task.md` (минимально, но конкретно)

Хороший `task.md` отвечает на 4 вопроса:
1. Что нужно получить на выходе?
2. Какой контекст и цель?
3. Какие ограничения есть (интеграции, безопасность, сроки, регуляторика)?
4. Что считается "готово"?

Короткий пример:

```md
# Задача

## Что нужно получить
Подготовить документацию по микросервису истории операций: FT, интеграции, API и ключевые NFT.

## Контекст
Сервис объединяет операции из нескольких источников и отдает историю в личный кабинет.

## Ограничения
Нельзя логировать персональные данные в открытом виде. SLA чтения истории: p95 < 300 мс.

## Критерий готовности
Есть структурированный draft по секциям, список gaps и план доработки.
```

### Шаг 3. Добавьте вложения

В UI загрузите файлы через `Upload attachments`.

Поддерживаемые форматы:
- `.md`
- `.txt`
- `.docx`
- `.pdf`

Рекомендация для микросервисной аналитики: держать вложения структурированно.

Пример логичной структуры внутри `attachments`:
```text
attachments/
  00-overview/
  10-business/
  20-architecture/
  30-integrations-internal/
  40-integrations-external/
  50-api/
  60-data-model/
  70-deployment/
  80-nfr-security-audit/
```

### Шаг 4. Запустите анализ задачи

Нажмите `Analyze task`.

Что делает система:
- читает `task.md`;
- определяет тип документа (`ft`/`nft`);
- выбирает нужные секции для генерации.

### Шаг 5. Запустите секционную генерацию draft

Нажмите `Create draft`.

Что происходит внутри:
1. Для каждой секции строится context pack.
2. Контекст берется из двух уровней:
   - общий: `docs/input`, `docs/examples`, `docs/glossary`;
   - task-контекст: `tasks/inbox/<task-id>/task.md` + `attachments`.
3. Каждая секция генерируется отдельно.
4. Секции собираются в единый markdown-документ.

### Шаг 6. Запустите gap-analysis

Нажмите `Gap analysis`.

Результат:
- список пробелов в требованиях;
- вопросы к заказчику;
- что именно нужно уточнить перед финализацией.

### Шаг 7. Запустите refine

1. В поле инструкций укажите, что улучшить (например: `Уточни ошибки, валидации и внутренние интеграции`).
2. Нажмите `Refine draft`.

Refine создает новый вариант draft, не затирая предыдущие.

### Шаг 8. Повторяйте цикл до финала

Рабочий цикл:
1. Draft
2. Gap analysis
3. Уточнения от заказчика
4. Refine
5. Финальная редактура аналитиком

## Где лежат результаты

Все артефакты сохраняются автоматически:

- Drafts: `artifacts/drafts/<task-id>/`
- Gap reviews: `artifacts/reviews/<task-id>/`
- Context packs: `artifacts/context_packs/<task-id>/`

UI показывает последние файлы и дает быстрый доступ к ним.

## Что система делает автоматически

Система автоматически:
- определяет тип документа;
- выбирает секции;
- применяет секционные шаблоны;
- подбирает релевантный контекст;
- генерирует секции;
- собирает финальный draft;
- строит gaps;
- поддерживает refine.

Аналитик не делает `curl`, не выбирает шаблоны вручную и не собирает контекст руками.

## Шаблоны и промпты

Шаблоны секций лежат в:
- `docs/templates/sections/ft/`
- `docs/templates/sections/nft/`

Промпты пайплайна лежат в:
- `docs/templates/prompts/draft_ft.md`
- `docs/templates/prompts/draft_nft.md`
- `docs/templates/prompts/gap_finder.md`
- `docs/templates/prompts/refine.md`

Правило языка:
- код и технические комментарии: английский;
- пользовательские тексты и prompts: русский.

## CLI (опционально, если UI недоступен)

```bash
./scripts/analyze_task.sh <task-id>
./scripts/create_draft.sh <task-id> [ft|nft]
./scripts/gap_analysis.sh <task-id> [draft-path]
./scripts/refine_draft.sh <task-id> [instructions] [draft-path]
```

## API endpoints

Сервис сохраняет базовые и workflow endpoints:

- `GET /health`
- `POST /reindex`
- `POST /search`
- `POST /analyze-task`
- `POST /build-context-pack`
- `POST /draft`
- `POST /gap-analysis`
- `POST /refine`

UI endpoints:
- `GET /ui`
- `GET /ui/task-template`
- `POST /ui/create-task`
- `POST /ui/upload-attachments/{task_id}`
- `GET /ui/state/{task_id}`
- `GET /ui/artifacts/{kind}/{task_id}/{filename}`

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
