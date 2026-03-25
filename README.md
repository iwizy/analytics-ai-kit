# analytics-ai-kit

Локальная система для аналитиков, которая из `task.md` и вложений автоматически собирает первый черновик документа, делает gap-анализ и помогает итеративно доработать текст.

Система работает полностью локально:
- Docker Compose
- Ollama
- Qdrant
- `rag-service` (FastAPI)
- VS Code + Continue (основной интерфейс аналитика)

Open WebUI в этом workflow не используется.

---

## Что получает аналитик

После запуска pipeline аналитик получает:
1. Первый draft документа.
2. Список gaps и вопросов.
3. Возможность сделать refine без ручной переработки всего текста.

Аналитику не нужно:
- выбирать шаблон вручную,
- писать `curl`,
- вручную искать контекст в документации,
- думать о структуре секций с нуля.

---

## Быстрый сценарий (TL;DR)

1. Создать `task.md`.
2. Добавить файлы в `attachments` (если есть).
3. Запустить 3 команды:

```bash
./scripts/create_draft.sh <task-id>
./scripts/gap_analysis.sh <task-id>
./scripts/refine_draft.sh <task-id> "Что именно улучшить"
```

Результаты появятся в `artifacts/`.

---

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

---

## Подготовка окружения (один раз)

Если среда уже поднята, переходите к разделу "Работа аналитика по задаче".

1. Создайте `.env`:

```bash
cp .env.example .env
```

2. Поднимите сервисы:

```bash
docker compose up -d --build
```

3. Установите модели Ollama:

```bash
./scripts/pull-models.sh
```

Скрипт устанавливает обязательные модели:
- `nomic-embed-text`
- `qwen2.5:7b`
- `qwen3:14b`
- `gpt-oss:20b`

4. Проиндексируйте общий контекст:

```bash
./scripts/reindex.sh
```

5. Проверьте доступность сервисов:

```bash
./scripts/healthcheck.sh
```

---

## Работа аналитика по задаче

## 1. Создать задачу

Создайте папку задачи:

```bash
mkdir -p tasks/inbox/task-001/attachments
cp tasks/task.md.template tasks/inbox/task-001/task.md
```

Где:
- `task-001` — ваш `task-id`.
- `task-id` используйте короткий и стабильный (`letters/digits/-/_/.`).

## 2. Заполнить `task.md`

Минимальный хороший `task.md` должен ответить на 4 вопроса:
1. Что нужно получить?
2. Какой контекст и цель?
3. Какие ограничения?
4. Какой критерий готовности?

Пример:

```md
# Задача

## Что нужно получить
Подготовить функциональные требования для процесса оформления заявки на кредит.

## Контекст
Сейчас часть проверок выполняется вручную операторами, что дает ошибки и задержки.

## Ограничения
Интеграция только с внутренним scoring API.
Персональные данные нельзя хранить в открытых логах.

## Критерий готовности
Документ должен содержать бизнес-сценарии, интеграции, валидации, ошибки и открытые вопросы.
```

Рекомендации:
- Пишите конкретно, без общих формулировок вроде "сделать хорошо".
- Фиксируйте ограничения сразу (security, SLA, регуляторика).
- Если есть неясности — лучше явно указать их в задаче.

## 3. Добавить attachments (опционально)

Положите материалы в:

```text
tasks/inbox/<task-id>/attachments/
```

Поддерживаемые форматы:
- `.md`
- `.txt`
- `.docx`
- `.pdf`

Что полезно добавлять:
- спецификации интеграций,
- описания бизнес-процессов,
- выписки требований,
- регламенты по security/logging/audit,
- примеры похожих документов.

Что лучше не добавлять:
- большие нерелевантные файлы "на всякий случай",
- устаревшие документы без пометки,
- дубли одного и того же текста в 5 вариантах.

## 4. Проверить анализ задачи

```bash
./scripts/analyze_task.sh task-001
```

Что делает команда:
- читает `task.md`,
- определяет тип документа (`ft`/`nft`),
- подбирает список секций.

Если тип определился неверно, при создании draft можно принудительно указать тип.

## 5. Получить первый draft

Автоматический выбор типа:

```bash
./scripts/create_draft.sh task-001
```

Принудительно `ft`:

```bash
./scripts/create_draft.sh task-001 ft
```

Принудительно `nft`:

```bash
./scripts/create_draft.sh task-001 nft
```

Что происходит внутри:
1. Для каждой секции строится `context pack`.
2. Контекст берется из двух уровней:
   - Global: `docs/input`, `docs/examples`, `docs/glossary`.
   - Task: `task.md` + `attachments`.
3. Секция генерируется отдельно.
4. Секции собираются в один markdown draft.

## 6. Сделать gap-analysis

```bash
./scripts/gap_analysis.sh task-001
```

Команда анализирует draft и формирует:
- пробелы в требованиях,
- вопросы к заказчику,
- что нужно уточнить по данным/интеграциям.

## 7. Сделать refine

```bash
./scripts/refine_draft.sh task-001 "Уточни критерии валидации, обработку ошибок и интеграции"
```

Refine выполняется секционно и создает новый файл draft, не затирая старый.

## 8. Повторять цикл до готовности

Рекомендуемый цикл:
1. `draft`
2. `gap-analysis`
3. уточнения от заказчика
4. `refine`
5. финальная ручная проверка аналитика

---

## Где смотреть результаты

Файлы создаются автоматически:

- Draft:
  - `artifacts/drafts/<task-id>/..._draft_ft.md`
  - `artifacts/drafts/<task-id>/..._draft_nft.md`
- Refined drafts:
  - `artifacts/drafts/<task-id>/..._refined_ft.md`
  - `artifacts/drafts/<task-id>/..._refined_nft.md`
- Gap analysis:
  - `artifacts/reviews/<task-id>/..._gaps.md`
- Context packs по секциям:
  - `artifacts/context_packs/<task-id>/..._<section>.json`

---

## Как работать из Continue

Вариант для аналитика в VS Code + Continue:

1. Создайте `task.md` и добавьте вложения.
2. В чате Continue попросите выполнить команду, например:
   - `Запусти ./scripts/create_draft.sh task-001 и покажи где лежит draft`
   - `Запусти gap-analysis для task-001`
   - `Сделай refine draft task-001 с фокусом на security и audit`

Важно: базовые команды и артефакты одинаковые, независимо от того, запускаете вы их в терминале вручную или через Continue.

---

## Логика маршрутизации контекста (routing)

Система автоматически подбирает приоритет источников по секциям.

Примеры:
- `business_requirements`:
  - `task.md`
  - product/process docs
  - examples
- `internal_integrations`:
  - `task.md`
  - docs по внутренним системам
  - integration материалы
- `logging`, `audit`:
  - `task.md`
  - security/NFT docs
  - examples

Это снижает ручную работу: аналитик не собирает контекст вручную под каждую секцию.

---

## Частые ошибки и как исправить

1. Ошибка: `task.md not found`.
   - Проверьте путь `tasks/inbox/<task-id>/task.md`.

2. Ошибка: пустой или слишком общий draft.
   - Уточните `task.md` (цель, ограничения, критерии).
   - Добавьте релевантные attachments.

3. Ошибка: сервисы недоступны.
   - Запустите `docker compose up -d`.
   - Проверьте `./scripts/healthcheck.sh`.

4. Ошибка: модель не найдена в Ollama.
   - Запустите `./scripts/pull-models.sh`.

5. После обновления `docs/input|examples|glossary` результаты не учитывают новые материалы.
   - Запустите `./scripts/reindex.sh`.

---

## Полный список скриптов

- `./scripts/pull-models.sh`
- `./scripts/reindex.sh`
- `./scripts/healthcheck.sh`
- `./scripts/analyze_task.sh <task-id>`
- `./scripts/create_draft.sh <task-id> [ft|nft]`
- `./scripts/gap_analysis.sh <task-id> [draft-path]`
- `./scripts/refine_draft.sh <task-id> [instructions] [draft-path]`

---

## API (для инженерных сценариев)

Существующие endpoints:
- `GET /health`
- `POST /reindex`
- `POST /search`

Workflow endpoints:
- `POST /analyze-task`
- `POST /build-context-pack`
- `POST /draft`
- `POST /gap-analysis`
- `POST /refine`

Если вы аналитик, рекомендуется использовать scripts и Continue, а не прямые API-вызовы.
