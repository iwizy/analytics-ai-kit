"""
Application settings and shared constants for the RAG workflow.
"""

import os
from pathlib import Path

DOCS_ROOT = Path(os.getenv("DOCS_ROOT") or "/data/docs")
TASKS_ROOT = Path(os.getenv("TASKS_ROOT") or "/data/tasks")
ARTIFACTS_ROOT = Path(os.getenv("ARTIFACTS_ROOT") or "/data/artifacts")
SERVICE_STORAGE_ROOT = Path(os.getenv("SERVICE_STORAGE_ROOT") or "/data/storage")
DOCKER_SOCKET_PATH = Path(os.getenv("DOCKER_SOCKET_PATH") or "/var/run/docker.sock")
ANALYST_PROFILES_ROOT = SERVICE_STORAGE_ROOT / "analyst_profiles"
PLAYWRIGHT_STATE_ROOT = SERVICE_STORAGE_ROOT / "playwright"

QDRANT_URL = os.getenv("QDRANT_URL") or "http://localhost:6333"
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION") or "analytics_context"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or "nomic-embed-text"
DRAFT_MODEL = os.getenv("DRAFT_MODEL") or "qwen2.5-coder:14b"
REVIEW_MODEL = os.getenv("REVIEW_MODEL") or "qwen2.5:7b"
REFINE_MODEL = os.getenv("REFINE_MODEL") or "qwen2.5-coder:14b"
PIPELINE_DRAFT_MODEL = os.getenv("PIPELINE_DRAFT_MODEL") or DRAFT_MODEL
PIPELINE_GAP_MODEL = os.getenv("PIPELINE_GAP_MODEL") or REVIEW_MODEL
PIPELINE_REFINE_MODEL = os.getenv("PIPELINE_REFINE_MODEL") or REFINE_MODEL

REQUIRED_MODELS = (
    "nomic-embed-text",
    "qwen2.5:7b",
    "qwen2.5-coder:14b",
    "gpt-oss:20b",
)

SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT") or "8")
CONTEXT_PACK_LIMIT = int(os.getenv("CONTEXT_PACK_LIMIT") or "12")
PIPELINE_SECTION_WORKERS = int(os.getenv("PIPELINE_SECTION_WORKERS") or "4")
PIPELINE_STAGE_TIMEOUT_SEC = int(os.getenv("PIPELINE_STAGE_TIMEOUT_SEC") or "240")
PIPELINE_MAX_RETRIES = int(os.getenv("PIPELINE_MAX_RETRIES") or "1")

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
