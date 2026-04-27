from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.confluence import ConfluenceImportError, load_analyst_profile
from app.exchange import build_exchange_status
from app.settings import DOCS_ROOT, SERVICE_STORAGE_ROOT
import yaml

DEFAULT_ANALYST_ID = "default"
_ENVIRONMENT_DIR = SERVICE_STORAGE_ROOT / "environment"
_ENVIRONMENT_FILE = _ENVIRONMENT_DIR / "settings.json"
_CONTINUE_CONFIG_ROOT = Path(os.getenv("CONTINUE_CONFIG_ROOT") or "/host-continue")
_CONTINUE_CONFIG_PATH = _CONTINUE_CONFIG_ROOT / "config.yaml"
_CONTINUE_CONFIG_PATH_LABEL = os.getenv("CONTINUE_CONFIG_HOST_PATH_LABEL") or "~/.continue/config.yaml"
_HOST_OS_NAME = (os.getenv("HOST_OS_NAME") or "unknown").strip().lower()
_CONTINUE_TEMPLATE_PATH = DOCS_ROOT / "continue" / "config.template.yaml"
_CONTINUE_CONFIG_PATHS = {
    "macos": "~/.continue/config.yaml",
    "windows": r"%USERPROFILE%\\.continue\\config.yaml",
    "linux": "~/.continue/config.yaml",
}

_MODEL_RECOMMENDATIONS = [
    {
        "key": "light",
        "title": "Легкий профиль",
        "description": "Для ноутбуков с ограниченной памятью. В основе — Gemma 4 E2B: она легче по памяти и лучше подходит для слабых машин.",
        "continue_model": "gemma4:e2b",
        "pipeline_hint": "Если машина начинает шуметь или упирается в память, начни с Gemma 4 E2B. Это самый щадящий профиль для локальной работы.",
        "required_models": ["nomic-embed-text", "gemma4:e2b"],
        "deferred_models": ["qwen2.5:7b", "qwen2.5-coder:14b", "qwen3-coder:30b"],
        "draft_model": "gemma4:e2b",
        "review_model": "gemma4:e2b",
        "refine_model": "gemma4:e2b",
    },
    {
        "key": "standard",
        "title": "Стандартный профиль",
        "description": "Компромисс между скоростью и качеством. Подходит для большинства рабочих ноутбуков и повседневной аналитики.",
        "continue_model": "qwen2.5-coder:14b",
        "pipeline_hint": "Хороший безопасный вариант, если не хочется перегружать машину, но нужен более собранный текст.",
        "required_models": ["nomic-embed-text", "qwen2.5:7b", "qwen2.5-coder:14b"],
        "deferred_models": ["gemma4:e2b", "qwen3-coder:30b"],
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
        "deferred_models": ["gemma4:e2b", "qwen2.5-coder:14b"],
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


def _continue_api_base() -> str:
    return "http://127.0.0.1:11434"


def _defaults() -> dict[str, Any]:
    return {
        "confluence_base_url": "",
        "vscode_ready": False,
        "continue_ready": False,
        "syncthing_ready": False,
        "model_profile": "powerful",
        "optional_models": [],
        "exchange_folder": "",
        "exchange_auto_scan": True,
        "exchange_poll_interval_sec": 60,
        "diff_tool": "vscode",
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
    saved_login = str(payload.get("confluence_login") or "")
    try:
        profile = load_analyst_profile(DEFAULT_ANALYST_ID)
    except ConfluenceImportError:
        profile = None
    payload["confluence_login"] = str(profile.login or "") if profile else saved_login
    payload["has_confluence_password"] = bool(profile and profile.password)
    return payload


def save_environment_settings(
    *,
    confluence_base_url: str,
    confluence_login: str,
    vscode_ready: bool,
    continue_ready: bool,
    syncthing_ready: bool,
    model_profile: str,
    optional_models: list[str] | None = None,
    exchange_folder: str = "",
    exchange_auto_scan: bool = True,
    exchange_poll_interval_sec: int = 60,
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
        "confluence_login": confluence_login.strip(),
        "vscode_ready": bool(vscode_ready),
        "continue_ready": bool(continue_ready),
        "syncthing_ready": bool(syncthing_ready),
        "model_profile": model_profile.strip() or "powerful",
        "optional_models": selected_optional,
        "exchange_folder": exchange_folder.strip(),
        "exchange_auto_scan": bool(exchange_auto_scan),
        "exchange_poll_interval_sec": max(15, int(exchange_poll_interval_sec or 60)),
        "diff_tool": "vscode",
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


def _continue_model_specs(profile_key: str | None, optional_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profile = get_model_profile(profile_key)
    specs: list[dict[str, Any]] = [
        {
            "alias": "fast",
            "model": "gemma4:e2b" if profile["key"] == "light" else "qwen2.5:7b",
            "required": True,
            "purpose": "Быстрые ответы и лёгкие правки в Continue.",
        },
        {
            "alias": "main",
            "model": str(profile["continue_model"]),
            "required": True,
            "purpose": "Основной разговорный режим в Continue для текущего профиля машины.",
        },
        {
            "alias": "heavy",
            "model": "qwen3-coder:30b",
            "required": profile["key"] == "powerful",
            "purpose": "Тяжёлый режим для глубокой переработки документа и длинного контекста.",
        },
    ]
    review_model = next(
        (
            item["model"]
            for item in optional_catalog
            if item.get("purpose") == "review" and item.get("selected")
        ),
        "",
    )
    if review_model:
        specs.append(
            {
                "alias": "review",
                "model": review_model,
                "required": False,
                "purpose": "Второе мнение и дополнительное ревью после основного пайплайна.",
            }
        )
    return specs


def _dump_continue_template(profile_key: str | None, optional_catalog: list[dict[str, Any]]) -> str:
    api_base = _continue_api_base()
    models: list[dict[str, Any]] = []
    for spec in _continue_model_specs(profile_key, optional_catalog):
        entry: dict[str, Any] = {
            "name": spec["alias"],
            "provider": "ollama",
            "model": spec["model"],
            "apiBase": api_base,
        }
        if spec["alias"] in {"main", "heavy", "review"}:
            entry["capabilities"] = ["tool_use"]
        models.append(entry)
    payload = {
        "name": "Analytics AI Kit",
        "version": "1.0.0",
        "schema": "v1",
        "models": models,
        "context": [
            {"provider": "code"},
            {"provider": "docs"},
            {"provider": "diff"},
            {"provider": "terminal"},
            {"provider": "problems"},
            {"provider": "folder"},
        ],
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _load_continue_config() -> dict[str, Any]:
    path = _CONTINUE_CONFIG_PATH
    exists = path.exists()
    payload: dict[str, Any] = {}
    parse_error = ""
    if exists:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                payload = loaded
            else:
                parse_error = "Файл Continue найден, но его структура не похожа на YAML-объект."
        except Exception as exc:
            parse_error = str(exc)
    return {
        "exists": exists,
        "payload": payload,
        "parse_error": parse_error,
    }


def build_continue_config_snapshot(*, profile_key: str | None, optional_catalog: list[dict[str, Any]]) -> dict[str, Any]:
    loaded = _load_continue_config()
    payload = dict(loaded.get("payload") or {})
    current_models: list[dict[str, Any]] = []
    for item in payload.get("models") or []:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("name") or "").strip()
        model = str(item.get("model") or "").strip()
        provider = str(item.get("provider") or "").strip()
        api_base = str(item.get("apiBase") or "").strip()
        if alias:
            current_models.append(
                {
                    "alias": alias,
                    "model": model,
                    "provider": provider,
                    "api_base": api_base,
                }
            )
    current_aliases = {item["alias"]: item for item in current_models}
    recommended = _continue_model_specs(profile_key, optional_catalog)
    missing_aliases: list[str] = []
    mismatched_aliases: list[dict[str, str]] = []
    ready = True
    for spec in recommended:
        current = current_aliases.get(spec["alias"])
        if current is None:
            if spec["required"]:
                ready = False
                missing_aliases.append(spec["alias"])
            continue
        if current.get("model") != spec["model"]:
            ready = False
            mismatched_aliases.append(
                {
                    "alias": spec["alias"],
                    "expected_model": spec["model"],
                    "actual_model": str(current.get("model") or ""),
                }
            )
    if loaded["parse_error"] or not loaded["exists"]:
        ready = False
    status = "ready" if ready else "needs_attention"
    return {
        "status": status,
        "host_os": _HOST_OS_NAME,
        "detected_path": _CONTINUE_CONFIG_PATH_LABEL,
        "known_paths": dict(_CONTINUE_CONFIG_PATHS),
        "exists": bool(loaded["exists"]),
        "parse_error": str(loaded["parse_error"] or ""),
        "template_repo_path": "docs/continue/config.template.yaml",
        "current_models": current_models,
        "recommended_models": recommended,
        "missing_aliases": missing_aliases,
        "mismatched_aliases": mismatched_aliases,
        "recommended_yaml": _dump_continue_template(profile_key, optional_catalog),
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
    continue_config = build_continue_config_snapshot(
        profile_key=str(settings.get("model_profile") or "powerful"),
        optional_catalog=optional_catalog,
    )
    exchange = build_exchange_status(
        configured_path=str(settings.get("exchange_folder") or ""),
        auto_scan=bool(settings.get("exchange_auto_scan", True)),
        poll_interval_sec=int(settings.get("exchange_poll_interval_sec") or 60),
        syncthing_ready=bool(settings.get("syncthing_ready")),
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
    continue_ready = bool(settings.get("continue_ready")) and continue_config["status"] == "ready"
    models_ready = not model_plan["missing_models"]

    missing_items: list[str] = []
    if not confluence_ready:
        missing_items.append("Заполнить Base URL, логин и пароль Confluence")
    if not vscode_ready:
        missing_items.append("Отметить готовность VS Code")
    if not settings.get("continue_ready"):
        missing_items.append("Отметить готовность Continue")
    elif continue_config["status"] != "ready":
        missing_items.append("Привести config.yaml Continue к рекомендуемому виду")
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
        "continue_config": continue_config,
        "exchange": exchange,
        "review_models": review_models,
        "readiness": readiness,
        "recommended_profiles": recommended_model_profiles(),
        "commands": {
            "start": "./start.command",
            "stop": "./stop.command",
            "power_mode": "./power-mode.command <task-id>",
        },
    }
