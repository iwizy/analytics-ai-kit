from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.confluence import ConfluenceImportError, load_analyst_profile, save_analyst_profile
from app.environment_state import DEFAULT_ANALYST_ID, build_environment_snapshot, save_environment_settings
from app.operations import get_operations_status

router = APIRouter()


class EnvironmentSettingsRequest(BaseModel):
    confluence_base_url: str = ""
    confluence_login: str = ""
    confluence_password: str = ""
    vscode_ready: bool = False
    continue_ready: bool = False
    syncthing_ready: bool = False
    model_profile: str = "powerful"
    optional_models: list[str] = []
    exchange_folder: str = ""
    exchange_auto_scan: bool = True
    exchange_poll_interval_sec: int = 60


@router.get("/ui/environment-settings")
def ui_environment_settings() -> dict:
    operations = get_operations_status()
    return build_environment_snapshot(operations.get("models") or {})


@router.post("/ui/environment-settings")
def ui_save_environment_settings(request: EnvironmentSettingsRequest) -> dict:
    try:
        existing_profile = load_analyst_profile(DEFAULT_ANALYST_ID) or {}
    except ConfluenceImportError:
        existing_profile = {}
    login = request.confluence_login.strip() or str(existing_profile.get("login") or "")
    password = request.confluence_password or str(existing_profile.get("password") or "")
    if login and password:
        save_analyst_profile(DEFAULT_ANALYST_ID, login, password)
    save_environment_settings(
        confluence_base_url=request.confluence_base_url,
        confluence_login=request.confluence_login,
        vscode_ready=request.vscode_ready,
        continue_ready=request.continue_ready,
        syncthing_ready=request.syncthing_ready,
        model_profile=request.model_profile,
        optional_models=request.optional_models,
        exchange_folder=request.exchange_folder,
        exchange_auto_scan=request.exchange_auto_scan,
        exchange_poll_interval_sec=request.exchange_poll_interval_sec,
    )
    operations = get_operations_status()
    return {
        "status": "ok",
        **build_environment_snapshot(operations.get("models") or {}),
    }
