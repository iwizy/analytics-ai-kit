"""
Application settings and shared constants for the RAG workflow.
"""

import os
from pathlib import Path

DOCS_ROOT = Path(os.getenv("DOCS_ROOT") or "/data/docs")
TASKS_ROOT = Path(os.getenv("TASKS_ROOT") or "/data/tasks")
ARTIFACTS_ROOT = Path(os.getenv("ARTIFACTS_ROOT") or "/data/artifacts")

QDRANT_URL = os.getenv("QDRANT_URL") or "http://localhost:6333"
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION") or "analytics_context"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or "nomic-embed-text"
DRAFT_MODEL = os.getenv("DRAFT_MODEL") or "qwen3:14b"
REVIEW_MODEL = os.getenv("REVIEW_MODEL") or "qwen2.5:7b"
REFINE_MODEL = os.getenv("REFINE_MODEL") or "qwen3:14b"

SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT") or "8")
CONTEXT_PACK_LIMIT = int(os.getenv("CONTEXT_PACK_LIMIT") or "12")

GLOBAL_CONTEXT_CATEGORIES = ("input", "examples", "glossary")
SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx", ".pdf"}

FT_SECTIONS = [
    "business_requirements",
    "internal_integrations",
    "external_integrations",
    "validations",
    "errors",
    "open_questions",
]

NFT_SECTIONS = [
    "performance",
    "availability",
    "security",
    "logging",
    "audit",
    "retention",
    "constraints",
    "open_questions",
]

SECTION_DISPLAY_NAMES = {
    "business_requirements": "Бизнес-требования",
    "internal_integrations": "Внутренние интеграции",
    "external_integrations": "Внешние интеграции",
    "validations": "Валидации",
    "errors": "Ошибки",
    "open_questions": "Открытые вопросы",
    "performance": "Производительность",
    "availability": "Доступность",
    "security": "Безопасность",
    "logging": "Логирование",
    "audit": "Аудит",
    "retention": "Хранение данных",
    "constraints": "Ограничения",
}
