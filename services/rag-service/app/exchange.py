from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.settings import DOCS_ROOT, SERVICE_STORAGE_ROOT

EXCHANGE_ROOT = Path(os.getenv("EXCHANGE_ROOT") or "/data/team-exchange")
EXCHANGE_HOST_PATH_LABEL = os.getenv("EXCHANGE_HOST_PATH_LABEL") or str(EXCHANGE_ROOT)
EXCHANGE_DOC_PATH = "docs/team-exchange.md"
SYNC_STATE_ROOT = SERVICE_STORAGE_ROOT / "sync"
IMPORT_STATE_PATH = SYNC_STATE_ROOT / "import-state.json"
VALID_CATEGORIES = ("context", "templates", "glossary")
RECOMMENDED_DIFF_TOOL = {
    "key": "vscode",
    "title": "VS Code Compare",
    "description": "Рекомендуемый способ разбирать расхождения: открывать локальный файл и incoming-версию через встроенное сравнение VS Code.",
}
LOCAL_SHARED_SOURCES = {
    "context": {
        "title": "Общий контекст проекта",
        "root": DOCS_ROOT / "shared-context",
        "repo_path": "docs/shared-context",
    },
    "templates": {
        "title": "Шаблоны",
        "root": DOCS_ROOT / "templates",
        "repo_path": "docs/templates",
    },
    "glossary": {
        "title": "Глоссарий",
        "root": DOCS_ROOT / "glossary",
        "repo_path": "docs/glossary",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return normalized or "analyst"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_exchange_layout() -> None:
    (EXCHANGE_ROOT / "bundles").mkdir(parents=True, exist_ok=True)
    SYNC_STATE_ROOT.mkdir(parents=True, exist_ok=True)
    for item in LOCAL_SHARED_SOURCES.values():
        Path(item["root"]).mkdir(parents=True, exist_ok=True)


def _load_import_state() -> dict[str, Any]:
    ensure_exchange_layout()
    payload = {
        "last_scan_at": "",
        "imported_bundles": {},
    }
    payload.update(_read_json(IMPORT_STATE_PATH))
    if not isinstance(payload.get("imported_bundles"), dict):
        payload["imported_bundles"] = {}
    return payload


def _save_import_state(payload: dict[str, Any]) -> None:
    _write_json(IMPORT_STATE_PATH, payload)


def _bundle_directory(bundle_id: str) -> Path:
    return EXCHANGE_ROOT / "bundles" / bundle_id


def _bundle_manifest_path(bundle_id: str) -> Path:
    return _bundle_directory(bundle_id) / "manifest.json"


def _load_manifest(bundle_id: str) -> dict[str, Any]:
    payload = _read_json(_bundle_manifest_path(bundle_id))
    if payload:
        return payload
    raise FileNotFoundError(f"Manifest for bundle '{bundle_id}' not found")


def _list_category_files(category: str) -> list[Path]:
    source = LOCAL_SHARED_SOURCES[category]
    root = Path(source["root"])
    if not root.exists():
        return []
    return sorted([path for path in root.rglob("*") if path.is_file()])


def _serialize_local_sources() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key, source in LOCAL_SHARED_SOURCES.items():
        files = _list_category_files(key)
        items.append(
            {
                "key": key,
                "title": str(source["title"]),
                "repo_path": str(source["repo_path"]),
                "file_count": len(files),
            }
        )
    return items


def _serialize_bundle(payload: dict[str, Any], import_state: dict[str, Any]) -> dict[str, Any]:
    bundle_id = str(payload.get("bundle_id") or "")
    imported_meta = import_state.get("imported_bundles", {}).get(bundle_id) or {}
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    conflicts = imported_meta.get("conflicts") if isinstance(imported_meta.get("conflicts"), list) else []
    return {
        "bundle_id": bundle_id,
        "created_at": str(payload.get("created_at") or ""),
        "created_by": str(payload.get("created_by") or "unknown"),
        "description": str(payload.get("description") or ""),
        "type": str(payload.get("type") or "shared_context"),
        "categories": [str(item) for item in payload.get("categories") or []],
        "file_count": len(files),
        "imported": bool(imported_meta),
        "imported_at": str(imported_meta.get("imported_at") or ""),
        "has_conflicts": bool(conflicts),
        "conflict_count": len(conflicts),
        "path_label": f"{EXCHANGE_HOST_PATH_LABEL}/bundles/{bundle_id}",
    }


def list_exchange_bundles() -> list[dict[str, Any]]:
    ensure_exchange_layout()
    state = _load_import_state()
    bundles: list[dict[str, Any]] = []
    bundles_dir = EXCHANGE_ROOT / "bundles"
    for bundle_dir in sorted(
        [path for path in bundles_dir.iterdir() if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    ):
        payload = _read_json(bundle_dir / "manifest.json")
        if not payload:
            continue
        bundles.append(_serialize_bundle(payload, state))
    state["last_scan_at"] = _now_iso()
    _save_import_state(state)
    return bundles


def build_exchange_status(
    *,
    configured_path: str,
    auto_scan: bool,
    poll_interval_sec: int,
    syncthing_ready: bool,
) -> dict[str, Any]:
    bundles = list_exchange_bundles()
    pending = [bundle for bundle in bundles if not bundle["imported"]]
    accessible = EXCHANGE_ROOT.exists()
    configured = configured_path.strip() or EXCHANGE_HOST_PATH_LABEL
    requires_restart = os.path.normpath(configured) != os.path.normpath(EXCHANGE_HOST_PATH_LABEL)
    status = "ready"
    if requires_restart:
        status = "restart_required"
    elif not syncthing_ready or not accessible:
        status = "needs_attention"
    return {
        "status": status,
        "configured_path": configured,
        "mounted_path": EXCHANGE_HOST_PATH_LABEL,
        "mounted": accessible,
        "requires_restart": requires_restart,
        "syncthing_ready": bool(syncthing_ready),
        "auto_scan": bool(auto_scan),
        "poll_interval_sec": int(poll_interval_sec),
        "doc_path": EXCHANGE_DOC_PATH,
        "recommended_diff_tool": dict(RECOMMENDED_DIFF_TOOL),
        "local_sources": _serialize_local_sources(),
        "new_bundles_count": len(pending),
        "total_bundles_count": len(bundles),
        "last_scan_at": _load_import_state().get("last_scan_at") or "",
        "bundles": bundles,
    }


def publish_bundle(
    *,
    author: str,
    description: str,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    ensure_exchange_layout()
    selected = [item for item in (categories or list(VALID_CATEGORIES)) if item in VALID_CATEGORIES]
    if not selected:
        raise ValueError("Не выбраны категории для публикации")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bundle_id = f"{timestamp}_{_slug(author or 'analyst')}"
    bundle_dir = _bundle_directory(bundle_id)
    files: list[dict[str, Any]] = []

    for category in selected:
        source_root = Path(LOCAL_SHARED_SOURCES[category]["root"])
        for source_path in _list_category_files(category):
            relative_path = source_path.relative_to(source_root).as_posix()
            bundle_relative_path = Path("files") / category / relative_path
            target_path = bundle_dir / bundle_relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            files.append(
                {
                    "category": category,
                    "relative_path": relative_path,
                    "bundle_path": bundle_relative_path.as_posix(),
                    "sha256": _hash_file(target_path),
                }
            )

    if not files:
        raise ValueError("В локальных общих папках пока нет файлов для публикации")

    manifest = {
        "bundle_id": bundle_id,
        "created_at": _now_iso(),
        "created_by": author.strip() or "unknown",
        "description": description.strip(),
        "type": "shared_context",
        "categories": selected,
        "diff_tool": RECOMMENDED_DIFF_TOOL["key"],
        "files": files,
    }
    _write_json(bundle_dir / "manifest.json", manifest)
    state = _load_import_state()
    return _serialize_bundle(manifest, state)


def import_bundles(bundle_ids: list[str]) -> list[dict[str, Any]]:
    ensure_exchange_layout()
    state = _load_import_state()
    results: list[dict[str, Any]] = []

    for bundle_id in bundle_ids:
        manifest = _load_manifest(bundle_id)
        copied: list[str] = []
        skipped: list[str] = []
        conflicts: list[dict[str, str]] = []
        for file_entry in manifest.get("files") or []:
            category = str(file_entry.get("category") or "")
            relative_path = str(file_entry.get("relative_path") or "")
            bundle_path = str(file_entry.get("bundle_path") or "")
            if category not in LOCAL_SHARED_SOURCES or not relative_path or not bundle_path:
                continue
            source_path = _bundle_directory(bundle_id) / bundle_path
            target_root = Path(LOCAL_SHARED_SOURCES[category]["root"])
            target_path = target_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                if _hash_file(target_path) == _hash_file(source_path):
                    skipped.append(f"{LOCAL_SHARED_SOURCES[category]['repo_path']}/{relative_path}")
                    continue
                incoming_path = target_path.with_name(f"{target_path.stem}.incoming_{bundle_id}{target_path.suffix}")
                shutil.copy2(source_path, incoming_path)
                conflicts.append(
                    {
                        "target": f"{LOCAL_SHARED_SOURCES[category]['repo_path']}/{relative_path}",
                        "incoming": f"{LOCAL_SHARED_SOURCES[category]['repo_path']}/{incoming_path.relative_to(target_root).as_posix()}",
                    }
                )
                continue
            shutil.copy2(source_path, target_path)
            copied.append(f"{LOCAL_SHARED_SOURCES[category]['repo_path']}/{relative_path}")

        state.setdefault("imported_bundles", {})[bundle_id] = {
            "imported_at": _now_iso(),
            "copied": copied,
            "skipped": skipped,
            "conflicts": conflicts,
        }
        results.append(
            {
                "bundle_id": bundle_id,
                "copied": copied,
                "skipped": skipped,
                "conflicts": conflicts,
            }
        )

    _save_import_state(state)
    return results
