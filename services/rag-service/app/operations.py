"""
Operational helpers for container control and Ollama model pull status.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.settings import DOCKER_SOCKET_PATH, OLLAMA_BASE_URL, QDRANT_URL, REQUIRED_MODELS

SERVICE_CONTAINERS = {
    "qdrant": "analytics-qdrant",
    "ollama": "analytics-ollama",
    "rag-service": "analytics-rag-service",
}

DEFAULT_STACK_SERVICES = ("qdrant", "ollama")
_ALLOWED_CONTAINER_ACTIONS = {"start", "stop", "restart"}
_LOG_LIMIT = 300


@dataclass
class ModelPullState:
    """
    Shared state for a background model pull job.
    """

    running: bool = False
    status: str = "idle"
    job_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    requested_models: list[str] = field(default_factory=list)
    per_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


_PULL_LOCK = threading.RLock()
_PULL_STATE = ModelPullState()


def utc_iso() -> str:
    """
    Build ISO timestamp in UTC.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append_pull_log(message: str) -> None:
    """
    Append one log line to shared pull state.
    """
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{timestamp} UTC] {message}"
    with _PULL_LOCK:
        _PULL_STATE.logs.append(line)
        if len(_PULL_STATE.logs) > _LOG_LIMIT:
            _PULL_STATE.logs = _PULL_STATE.logs[-_LOG_LIMIT:]


def _set_model_state(
    model: str,
    *,
    status: str,
    message: str | None = None,
    completed: int | None = None,
    total: int | None = None,
    error: str | None = None,
) -> None:
    """
    Update per-model pull progress snapshot.
    """
    progress: float | None = None
    if total and total > 0 and completed is not None:
        progress = min(max(completed / total, 0.0), 1.0)

    payload = {
        "status": status,
        "message": message or status,
        "completed": completed,
        "total": total,
        "progress": progress,
        "error": error,
        "updated_at": utc_iso(),
    }
    with _PULL_LOCK:
        _PULL_STATE.per_model[model] = payload


def _snapshot_pull_state() -> dict[str, Any]:
    """
    Return a copy of current model pull state.
    """
    with _PULL_LOCK:
        return {
            "running": _PULL_STATE.running,
            "status": _PULL_STATE.status,
            "job_id": _PULL_STATE.job_id,
            "started_at": _PULL_STATE.started_at,
            "finished_at": _PULL_STATE.finished_at,
            "requested_models": list(_PULL_STATE.requested_models),
            "per_model": json.loads(json.dumps(_PULL_STATE.per_model)),
            "logs": list(_PULL_STATE.logs),
        }


def _new_docker_client(timeout: float = 5.0) -> httpx.Client:
    """
    Build Docker Engine API client over unix socket.
    """
    transport = httpx.HTTPTransport(uds=str(DOCKER_SOCKET_PATH))
    return httpx.Client(base_url="http://docker", transport=transport, timeout=timeout)


def docker_daemon_status() -> dict[str, Any]:
    """
    Check Docker socket availability and daemon ping.
    """
    if not Path(DOCKER_SOCKET_PATH).exists():
        return {
            "available": False,
            "socket_path": str(DOCKER_SOCKET_PATH),
            "error": "Docker socket is not mounted",
        }

    try:
        with _new_docker_client(timeout=3.0) as client:
            response = client.get("/_ping")
        if response.status_code == 200 and response.text.strip().lower() == "ok":
            return {
                "available": True,
                "socket_path": str(DOCKER_SOCKET_PATH),
                "error": None,
            }

        return {
            "available": False,
            "socket_path": str(DOCKER_SOCKET_PATH),
            "error": f"Docker ping failed with status {response.status_code}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "socket_path": str(DOCKER_SOCKET_PATH),
            "error": f"Docker daemon is unavailable: {exc}",
        }


def _docker_request(method: str, path: str, timeout: float = 5.0) -> httpx.Response:
    """
    Execute one Docker API request.
    """
    with _new_docker_client(timeout=timeout) as client:
        return client.request(method, path)


def _container_status_by_name(container_name: str) -> dict[str, Any]:
    """
    Read one container status by its name.
    """
    try:
        response = _docker_request("GET", f"/containers/{container_name}/json")
    except Exception as exc:  # noqa: BLE001
        return {
            "container_name": container_name,
            "exists": False,
            "running": False,
            "state": "unknown",
            "status": "docker_error",
            "error": str(exc),
        }

    if response.status_code == 404:
        return {
            "container_name": container_name,
            "exists": False,
            "running": False,
            "state": "not_found",
            "status": "not_found",
            "error": "Container not found",
        }

    if response.status_code != 200:
        return {
            "container_name": container_name,
            "exists": False,
            "running": False,
            "state": "unknown",
            "status": f"docker_http_{response.status_code}",
            "error": f"Docker HTTP {response.status_code}",
        }

    payload = response.json()
    state_payload = payload.get("State") or {}

    return {
        "container_name": payload.get("Name", f"/{container_name}").lstrip("/"),
        "exists": True,
        "running": bool(state_payload.get("Running")),
        "state": state_payload.get("Status") or "unknown",
        "status": state_payload.get("Status") or "unknown",
        "error": None,
    }


def get_containers_state() -> dict[str, dict[str, Any]]:
    """
    Return state for managed service containers.
    """
    state: dict[str, dict[str, Any]] = {}
    for service, container_name in SERVICE_CONTAINERS.items():
        info = _container_status_by_name(container_name)
        info["service"] = service
        state[service] = info

    return state


def _normalize_services(services: list[str] | None, *, default_stack: bool) -> list[str]:
    """
    Validate and normalize service list.
    """
    if services is None or len(services) == 0:
        return list(DEFAULT_STACK_SERVICES if default_stack else SERVICE_CONTAINERS.keys())

    normalized: list[str] = []
    for service in services:
        key = service.strip().lower()
        if key not in SERVICE_CONTAINERS:
            supported = ", ".join(SERVICE_CONTAINERS.keys())
            raise ValueError(f"Unsupported service '{service}'. Supported values: {supported}")
        if key not in normalized:
            normalized.append(key)

    return normalized


def control_containers(
    action: str,
    *,
    services: list[str] | None = None,
    default_stack: bool = True,
) -> dict[str, Any]:
    """
    Start/stop/restart selected containers.
    """
    action_name = action.strip().lower()
    if action_name not in _ALLOWED_CONTAINER_ACTIONS:
        raise ValueError(f"Unsupported action '{action}'. Allowed: {', '.join(sorted(_ALLOWED_CONTAINER_ACTIONS))}")

    daemon = docker_daemon_status()
    if not daemon["available"]:
        raise RuntimeError(daemon["error"] or "Docker daemon is unavailable")

    targets = _normalize_services(services, default_stack=default_stack)
    results: list[dict[str, Any]] = []

    for service in targets:
        container_name = SERVICE_CONTAINERS[service]
        state_before = _container_status_by_name(container_name)

        if not state_before["exists"]:
            results.append(
                {
                    "service": service,
                    "container_name": container_name,
                    "ok": False,
                    "message": "Container not found. Run docker compose up -d --build once.",
                    "status_code": 404,
                }
            )
            continue

        try:
            response = _docker_request("POST", f"/containers/{container_name}/{action_name}")
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "service": service,
                    "container_name": container_name,
                    "ok": False,
                    "message": f"Docker request failed: {exc}",
                    "status_code": None,
                }
            )
            continue

        ok = response.status_code in {204, 304}
        if response.status_code == 204:
            message = f"{action_name} executed"
        elif response.status_code == 304:
            message = "Already in target state"
        elif response.status_code == 404:
            message = "Container not found"
        else:
            message = f"Docker HTTP {response.status_code}: {response.text[:300]}"

        results.append(
            {
                "service": service,
                "container_name": container_name,
                "ok": ok,
                "message": message,
                "status_code": response.status_code,
            }
        )

    return {
        "action": action_name,
        "targets": targets,
        "results": results,
        "containers": get_containers_state(),
    }


def _safe_http_probe(url: str, *, timeout: float = 2.5) -> dict[str, Any]:
    """
    Probe one HTTP endpoint with short timeout.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
        return {
            "ok": 200 <= response.status_code < 500,
            "status_code": response.status_code,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status_code": None,
            "error": str(exc),
        }


def get_installed_models() -> list[str]:
    """
    Return model names available in Ollama.
    """
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{OLLAMA_BASE_URL}/api/tags")
        response.raise_for_status()
        payload = response.json()

    installed: list[str] = []
    for model in payload.get("models", []):
        name = str(model.get("name") or "").strip()
        if name:
            installed.append(name)

    return sorted(set(installed))


def _model_variants(name: str) -> set[str]:
    """
    Return acceptable model names for matching required entries.
    """
    normalized = name.strip()
    if ":" in normalized:
        return {normalized}
    return {normalized, f"{normalized}:latest"}


def _is_model_available(required_model: str, installed_set: set[str]) -> bool:
    """
    Check if a required model exists in installed model names.
    """
    variants = _model_variants(required_model)
    return any(variant in installed_set for variant in variants)


def get_models_inventory(required_models: list[str] | None = None) -> dict[str, Any]:
    """
    Return installed and missing model lists.
    """
    required = list(required_models or REQUIRED_MODELS)

    try:
        installed = get_installed_models()
        installed_set = set(installed)
        missing = [model for model in required if not _is_model_available(model, installed_set)]
        ready = [model for model in required if _is_model_available(model, installed_set)]
        return {
            "required": required,
            "installed": installed,
            "ready_required": ready,
            "missing": missing,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "required": required,
            "installed": [],
            "ready_required": [],
            "missing": required,
            "error": str(exc),
        }


def _reset_pull_state(models: list[str]) -> None:
    """
    Reset shared pull state before a new run.
    """
    _PULL_STATE.running = True
    _PULL_STATE.status = "running"
    _PULL_STATE.job_id = f"pull-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    _PULL_STATE.started_at = utc_iso()
    _PULL_STATE.finished_at = None
    _PULL_STATE.requested_models = list(models)
    _PULL_STATE.per_model = {}
    _PULL_STATE.logs = []


def _run_pull_stream(model: str) -> None:
    """
    Pull one model from Ollama with stream progress.
    """
    _set_model_state(model, status="starting", message="Starting pull")
    _append_pull_log(f"Start pull: {model}")

    with httpx.Client(timeout=None) as client:
        with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/pull",
            json={"name": model, "stream": True},
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "error" in event:
                    raise RuntimeError(str(event["error"]))

                status = str(event.get("status") or "pulling")
                completed = event.get("completed")
                total = event.get("total")

                _set_model_state(
                    model,
                    status=status,
                    message=status,
                    completed=completed if isinstance(completed, int) else None,
                    total=total if isinstance(total, int) else None,
                )

    _set_model_state(model, status="done", message="Model is ready", completed=1, total=1)
    _append_pull_log(f"Done: {model}")


def _pull_models_worker(models: list[str], *, force: bool) -> None:
    """
    Background worker for sequential model pulls.
    """
    failed = False

    try:
        inventory = get_models_inventory(models)
        installed = set(inventory.get("installed") or [])

        for model in models:
            if _is_model_available(model, installed) and not force:
                _set_model_state(model, status="skipped", message="Already installed")
                _append_pull_log(f"Skip (already installed): {model}")
                continue

            try:
                _run_pull_stream(model)
            except Exception as exc:  # noqa: BLE001
                failed = True
                _set_model_state(model, status="failed", message="Pull failed", error=str(exc))
                _append_pull_log(f"Fail: {model}: {exc}")

        with _PULL_LOCK:
            _PULL_STATE.running = False
            _PULL_STATE.status = "failed" if failed else "completed"
            _PULL_STATE.finished_at = utc_iso()
            if failed:
                _append_pull_log("Model pull finished with errors")
            else:
                _append_pull_log("Model pull completed successfully")
    except Exception as exc:  # noqa: BLE001
        with _PULL_LOCK:
            _PULL_STATE.running = False
            _PULL_STATE.status = "failed"
            _PULL_STATE.finished_at = utc_iso()
            _append_pull_log(f"Unexpected model pull failure: {exc}")


def start_models_pull(
    models: list[str] | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Start async pull for required or explicit model list.
    """
    selected: list[str]
    if models is None or len(models) == 0:
        selected = list(REQUIRED_MODELS)
    else:
        selected = []
        for model in models:
            name = model.strip()
            if name and name not in selected:
                selected.append(name)

    if not selected:
        raise ValueError("Model list is empty")

    with _PULL_LOCK:
        if _PULL_STATE.running:
            return {
                "started": False,
                "message": "Model pull is already running",
                "model_pull": _snapshot_pull_state(),
            }

        _reset_pull_state(selected)
        thread = threading.Thread(
            target=_pull_models_worker,
            args=(selected,),
            kwargs={"force": force},
            daemon=True,
            name="model-pull-worker",
        )
        thread.start()

    return {
        "started": True,
        "message": "Model pull started",
        "model_pull": _snapshot_pull_state(),
    }


def get_operations_status() -> dict[str, Any]:
    """
    Build consolidated status payload for UI operations panel.
    """
    docker = docker_daemon_status()

    containers = get_containers_state() if docker["available"] else {
        service: {
            "service": service,
            "container_name": container,
            "exists": False,
            "running": False,
            "state": "docker_unavailable",
            "status": "docker_unavailable",
            "error": docker["error"],
        }
        for service, container in SERVICE_CONTAINERS.items()
    }

    ollama_probe = _safe_http_probe(f"{OLLAMA_BASE_URL}/api/tags")
    qdrant_probe = _safe_http_probe(QDRANT_URL)
    rag_probe = _safe_http_probe("http://127.0.0.1:8000/health")

    models = get_models_inventory()

    return {
        "docker": docker,
        "containers": containers,
        "services": {
            "ollama_api": ollama_probe,
            "qdrant_api": qdrant_probe,
            "rag_service_api": rag_probe,
        },
        "models": models,
        "model_pull": _snapshot_pull_state(),
    }
