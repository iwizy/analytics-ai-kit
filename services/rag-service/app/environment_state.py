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
        "required_models": ["nomic-embed-text", "qwen2.5:7b"],
        "deferred_models": ["qwen2.5-coder:14b", "qwen3-coder:30b"],
        "draft_model": "qwen2.5:7b",
        "review_model": "qwen2.5:7b",
        "refine_model": "qwen2.5:7b",
    },
    {
        "key": "standard",
        "title": "Стандартный профиль",
        "description": "Компромисс между скоростью и качеством. Подходит для большинства рабочих ноутбуков и повседневной аналитики.",
        "continue_model": "qwen2.5-coder:14b",
        "pipeline_hint": "Хороший безопасный вариант, если не хочется перегружать машину, но нужен более собранный текст.",
        "required_models": ["nomic-embed-text", "qwen2.5:7b", "qwen2.5-coder:14b"],
        "deferred_models": ["qwen3-coder:30b"],
        "draft_model": "qwen2.5-coder:14b",
        "review_model": "qwen2.5:7b",
        "refine_model": "qwen2.5-coder:14b",
    },
    {
        "key": "powerful",
        "title": "Мощная машина",
        "description": "Для мощных Mac и рабочих станций. Можно смело использовать qwen3-coder:30b для черновиков и разговорного режима в Continue.",
        "continue_model": "qwen3-coder:30b",
        "pipeline_hint": "Рекомендуемый вариант для твоего сценария, если машина тянет heavy-модель без заметных тормозов.",
        "required_models": ["nomic-embed-text", "qwen2.5:7b", "qwen3-coder:30b"],
        "deferred_models": ["qwen2.5-coder:14b"],
        "draft_model": "qwen3-coder:30b",
        "review_model": "qwen2.5:7b",
        "refine_model": "qwen3-coder:30b",
    },
]

_OPTIONAL_MODELS = [
    {
        "model": "gpt-oss:20b",
        "title": "GPT OSS 20B",
        "description": "Опциональная reasoning-модель для второго мнения, дополнительного ревью и более критичного анализа спорных мест.",
        "purpose": "review",
        "review_capable": True,
    },
]


def _defaults() -> dict[str, Any]:
    return {
        "confluence_base_url": "",
        "vscode_ready": False,
        "continue_ready": False,
        "model_profile": "powerful",
        "optional_models": [],
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


def save_environment_settings(
    *,
    confluence_base_url: str,
    vscode_ready: bool,
    continue_ready: bool,
    model_profile: str,
    optional_models: list[str] | None = None,
) -> dict[str, Any]:
    _ENVIRONMENT_DIR.mkdir(parents=True, exist_ok=True)
    selected_optional = []
    seen_optional: set[str] = set()
    for model in optional_models or []:
        name = str(model).strip()
        if name and name not in seen_optional:
            selected_optional.append(name)
            seen_optional.add(name)
    payload = {
        "confluence_base_url": confluence_base_url.strip(),
        "vscode_ready": bool(vscode_ready),
        "continue_ready": bool(continue_ready),
        "model_profile": model_profile.strip() or "powerful",
        "optional_models": selected_optional,
        "templates_mode": "power_only",
    }
    _ENVIRONMENT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_environment_settings()


def recommended_model_profiles() -> list[dict[str, str]]:
    return list(_MODEL_RECOMMENDATIONS)


def _model_variants(name: str) -> set[str]:
    normalized = name.strip()
    if ":" in normalized:
        return {normalized}
    return {normalized, f"{normalized}:latest"}


def _is_model_available(required_model: str, installed_set: set[str]) -> bool:
    return any(variant in installed_set for variant in _model_variants(required_model))


def get_model_profile(profile_key: str | None) -> dict[str, Any]:
    selected_key = (profile_key or "powerful").strip().lower()
    for profile in _MODEL_RECOMMENDATIONS:
        if profile["key"] == selected_key:
            return dict(profile)
    return dict(_MODEL_RECOMMENDATIONS[-1])


def build_optional_models_catalog(*, selected_models: list[str] | None, installed_models: list[str] | None) -> list[dict[str, Any]]:
    selected_set = {str(item).strip() for item in (selected_models or []) if str(item).strip()}
    installed_set = set(installed_models or [])
    catalog: list[dict[str, Any]] = []
    for item in _OPTIONAL_MODELS:
        model = str(item["model"])
        catalog.append(
            {
                **item,
                "selected": model in selected_set,
                "installed": _is_model_available(model, installed_set),
            }
        )
    return catalog


def build_model_plan(*, profile_key: str | None, installed_models: list[str] | None) -> dict[str, Any]:
    profile = get_model_profile(profile_key)
    installed = list(installed_models or [])
    installed_set = set(installed)
    required_models = list(profile.get("required_models") or [])
    ready_models = [model for model in required_models if _is_model_available(model, installed_set)]
    missing_models = [model for model in required_models if not _is_model_available(model, installed_set)]
    deferred_models = list(profile.get("deferred_models") or [])
    return {
        "profile_key": profile["key"],
        "required_models": required_models,
        "ready_models": ready_models,
        "missing_models": missing_models,
        "deferred_models": deferred_models,
        "download_models": missing_models,
        "draft_model": profile["draft_model"],
        "review_model": profile["review_model"],
        "refine_model": profile["refine_model"],
        "continue_model": profile["continue_model"],
    }


def get_runtime_model_bundle(profile_key: str | None = None) -> dict[str, str]:
    profile = get_model_profile(profile_key or load_environment_settings().get("model_profile"))
    return {
        "draft_model": str(profile["draft_model"]),
        "review_model": str(profile["review_model"]),
        "refine_model": str(profile["refine_model"]),
    }


def build_environment_snapshot(models: dict[str, Any]) -> dict[str, Any]:
    settings = load_environment_settings()
    installed_models = list(models.get("installed") or [])
    model_plan = build_model_plan(
        profile_key=str(settings.get("model_profile") or "powerful"),
        installed_models=installed_models,
    )
    optional_catalog = build_optional_models_catalog(
        selected_models=list(settings.get("optional_models") or []),
        installed_models=installed_models,
    )
    selected_optional = [item for item in optional_catalog if item["selected"]]
    installed_optional_review_models = [
        item["model"]
        for item in selected_optional
        if item.get("review_capable") and item.get("installed")
    ]
    review_models: list[str] = []
    for model_name in [model_plan["review_model"], *installed_optional_review_models]:
        if model_name and model_name not in review_models:
            review_models.append(model_name)
    confluence_ready = bool(
        settings.get("confluence_base_url")
        and settings.get("confluence_login")
        and settings.get("has_confluence_password")
    )
    vscode_ready = bool(settings.get("vscode_ready"))
    continue_ready = bool(settings.get("continue_ready"))
    models_ready = not model_plan["missing_models"]

    missing_items: list[str] = []
    if not confluence_ready:
        missing_items.append("Заполнить Base URL, логин и пароль Confluence")
    if not vscode_ready:
        missing_items.append("Отметить готовность VS Code")
    if not continue_ready:
        missing_items.append("Отметить готовность Continue")
    if not models_ready:
        missing_items.append("Скачать модели для выбранного профиля")

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
        "model_plan": model_plan,
        "optional_models": optional_catalog,
        "review_models": review_models,
        "readiness": readiness,
        "recommended_profiles": recommended_model_profiles(),
        "commands": {
            "start": "./start.command",
            "stop": "./stop.command",
            "power_mode": "./power-mode.command <task-id>",
        },
    }
