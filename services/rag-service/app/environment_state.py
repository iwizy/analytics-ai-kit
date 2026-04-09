from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.confluence import ConfluenceImportError, load_analyst_profile
from app.settings import SERVICE_STORAGE_ROOT

DEFAULT_ANALYST_ID = "default"
_ENVIRONMENT_DIR = SERVICE_STORAGE_ROOT / "environment"
_ENVIRONMENT_FILE = _ENVIRONMENT_DIR / "settings.json"

_MODEL_RECOMMENDATIONS = [
    {
        "key": "light",
        "title": "Легкий профиль",
        "description": "Для ноутбуков с ограниченной памятью. Быстрее отвечает, но глубина проработки и качество формулировок могут быть проще.",
        "continue_model": "qwen2.5:7b",
        "pipeline_hint": "Если машина начинает шуметь или упирается в память, начни с облегченной модели в Continue и только потом повышай качество.",
    },
    {
        "key": "standard",
        "title": "Стандартный профиль",
        "description": "Компромисс между скоростью и качеством. Подходит для большинства рабочих ноутбуков и повседневной аналитики.",
        "continue_model": "qwen2.5-coder:14b",
        "pipeline_hint": "Хороший безопасный вариант, если не хочется перегружать машину, но нужен более собранный текст.",
    },
    {
        "key": "powerful",
        "title": "Мощная машина",
        "description": "Для мощных Mac и рабочих станций. Можно смело использовать qwen3-coder:30b для черновиков и разговорного режима в Continue.",
        "continue_model": "qwen3-coder:30b",
        "pipeline_hint": "Рекомендуемый вариант для твоего сценария, если машина тянет heavy-модель без заметных тормозов.",
    },
]


def _defaults() -> dict[str, Any]:
    return {
        "confluence_base_url": "",
        "vscode_ready": False,
        "continue_ready": False,
        "model_profile": "powerful",
        "templates_mode": "power_only",
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def load_environment_settings() -> dict[str, Any]:
    _ENVIRONMENT_DIR.mkdir(parents=True, exist_ok=True)
    payload = _defaults()
    payload.update(_read_json(_ENVIRONMENT_FILE))
    try:
        profile = load_analyst_profile(DEFAULT_ANALYST_ID)
    except ConfluenceImportError:
        profile = None
    payload["confluence_login"] = str(profile.get("login") or "") if profile else ""
    payload["has_confluence_password"] = bool(profile and profile.get("password"))
    return payload


def save_environment_settings(*, confluence_base_url: str, vscode_ready: bool, continue_ready: bool, model_profile: str) -> dict[str, Any]:
    _ENVIRONMENT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "confluence_base_url": confluence_base_url.strip(),
        "vscode_ready": bool(vscode_ready),
        "continue_ready": bool(continue_ready),
        "model_profile": model_profile.strip() or "powerful",
        "templates_mode": "power_only",
    }
    _ENVIRONMENT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_environment_settings()


def recommended_model_profiles() -> list[dict[str, str]]:
    return list(_MODEL_RECOMMENDATIONS)


def build_environment_snapshot(models: dict[str, Any]) -> dict[str, Any]:
    settings = load_environment_settings()
    missing_models = list(models.get("missing") or [])
    confluence_ready = bool(
        settings.get("confluence_base_url")
        and settings.get("confluence_login")
        and settings.get("has_confluence_password")
    )
    vscode_ready = bool(settings.get("vscode_ready"))
    continue_ready = bool(settings.get("continue_ready"))
    models_ready = not missing_models

    missing_items: list[str] = []
    if not confluence_ready:
        missing_items.append("Заполнить Base URL, логин и пароль Confluence")
    if not vscode_ready:
        missing_items.append("Отметить готовность VS Code")
    if not continue_ready:
        missing_items.append("Отметить готовность Continue")
    if not models_ready:
        missing_items.append("Скачать обязательные модели")

    readiness = {
        "confluence_ready": confluence_ready,
        "vscode_ready": vscode_ready,
        "continue_ready": continue_ready,
        "models_ready": models_ready,
        "article_ready": confluence_ready and vscode_ready and continue_ready and models_ready,
        "all_ready": confluence_ready and vscode_ready and continue_ready and models_ready,
        "missing_items": missing_items,
    }
    return {
        "settings": settings,
        "readiness": readiness,
        "recommended_profiles": recommended_model_profiles(),
        "commands": {
            "start": "./start.command",
            "stop": "./stop.command",
            "power_mode": "./power-mode.command <task-id>",
        },
    }
