from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.environment_state import load_environment_settings
from app.exchange import build_exchange_status, import_bundles, publish_bundle

router = APIRouter()


class PublishBundleRequest(BaseModel):
    author: str = ""
    description: str = ""
    categories: list[str] = []


class ImportBundlesRequest(BaseModel):
    bundle_ids: list[str] = []


def _exchange_status() -> dict:
    settings = load_environment_settings()
    return build_exchange_status(
        configured_path=str(settings.get("exchange_folder") or ""),
        auto_scan=bool(settings.get("exchange_auto_scan", True)),
        poll_interval_sec=int(settings.get("exchange_poll_interval_sec") or 60),
        syncthing_ready=bool(settings.get("syncthing_ready")),
    )


@router.get("/ui/exchange/status")
def ui_exchange_status() -> dict:
    return {
        "status": "ok",
        "exchange": _exchange_status(),
    }


@router.post("/ui/exchange/scan")
def ui_exchange_scan() -> dict:
    return {
        "status": "ok",
        "exchange": _exchange_status(),
    }


@router.post("/ui/exchange/publish")
def ui_exchange_publish(request: PublishBundleRequest) -> dict:
    try:
        bundle = publish_bundle(
            author=request.author,
            description=request.description,
            categories=request.categories,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "bundle": bundle,
        "exchange": _exchange_status(),
    }


@router.post("/ui/exchange/import")
def ui_exchange_import(request: ImportBundlesRequest) -> dict:
    exchange = _exchange_status()
    bundle_ids = request.bundle_ids or [
        item["bundle_id"]
        for item in exchange.get("bundles") or []
        if not item.get("imported")
    ]
    if not bundle_ids:
        raise HTTPException(status_code=400, detail="Нет новых пакетов для импорта")
    try:
        imported = import_bundles(bundle_ids)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "status": "ok",
        "imported": imported,
        "exchange": _exchange_status(),
    }
