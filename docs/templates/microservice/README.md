# Шаблон документации по микросервису

Этот пакет шаблонов повторяет структуру, показанную на скриншоте, и собран по рекомендациям из предоставленных PDF.

## Рекомендуемая структура

```text
<Наименование микросервиса>/
  00_service_overview.md
  10_architecture_decisions.md
  20_business_requirements.md
  30_release_documentation.md
  40_integrations/
    41_external_integrations.md
    42_internal_integrations.md
  50_non_functional_requirements.md
  60_api/
    61_api_overview.md
    62_rest_api.md
    63_kafka_topics.md
  70_db_schema.md
  80_deployment_scheme.md
  90_functional_requirements.md
```

## Как использовать

1. Скопируйте нужные шаблоны в папку конкретного микросервиса.
2. Удалите подсказки и оставьте только заполненный контент.
3. Заполните все блоки `TO-DO`.
4. Для схем используйте PlantUML (`.puml`) и прикладывайте ссылку на исходник.

## Правило для диаграмм (PlantUML)

- Исходник диаграммы храните в `.puml`.
- В Markdown добавляйте:
  - путь к `.puml` файлу,
  - `plantuml` блок (черновик или финальная версия),
  - при необходимости ссылку на экспорт (`.png`/`.svg`).
- Для каждого документа диаграммы именуйте предсказуемо:
  - `architecture_as_is.puml`
  - `architecture_to_be.puml`
  - `db_schema.puml`
  - `deployment_scheme.puml`
  - `process_flow.puml`

## Общие правила заполнения

- Пишите конкретные и проверяемые формулировки.
- Если данных не хватает, фиксируйте это в `Открытых вопросах`.
- В таблицах всегда указывайте версии/даты/ответственных.
- Для интеграций обязательно приводите пример запроса/события и ответа.
