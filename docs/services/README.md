# База контекста по микросервисам

В этой папке лучше хранить документы, которые относятся к конкретным сервисам:

- бизнес- и функциональные требования,
- интеграционные контракты (внутренние и внешние),
- нефункциональные требования,
- документация API/событий,
- схемы и архитектурные материалы.

Рекомендуемый путь:

```text
docs/services/<service-name>/
  00_service_overview.md
  20_business_requirements.md
  90_functional_requirements.md
  50_non_functional_requirements.md
  42_internal_integrations.md
  41_external_integrations.md
  63_kafka_topics.md
  80_deployment_scheme.md
```

Можно копировать заготовки из `docs/templates/microservice/`.

Файлы здесь автоматически участвуют в сборе контекста для соответствующего документа, если в `task.md` указан блок `Сервис:`.
