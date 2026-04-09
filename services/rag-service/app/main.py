"""
Main application entrypoint for the local analytics RAG service.
"""

from __future__ import annotations

import json
import mimetypes
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.confluence import (
    ConfluenceImportError,
    import_confluence_urls,
    save_analyst_profile,
)
from app.ingest import reindex_all_documents
from app.operations import control_containers, get_operations_status, start_models_pull
from app.search import search_documents
from app.settings import ARTIFACTS_ROOT, SUPPORTED_EXTENSIONS, TASKS_ROOT
from app.workflow import (
    WorkflowError,
    analyze_task,
    build_context_pack,
    create_draft,
    load_pipeline_status,
    prepare_continue_handoff,
    recover_interrupted_pipeline_runs,
    run_pipeline,
    start_pipeline_run,
    refine_draft,
    run_gap_analysis,
    sanitize_task_id,
)

app = FastAPI(title="Analytics RAG Service", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UI_HTML_PATH = Path(__file__).resolve().parent / "static" / "ui.html"
ARTIFACT_KINDS = ("drafts", "reviews", "context_packs", "pipeline_runs", "handoffs")
PREVIEW_CHAR_LIMIT = 12000

DEFAULT_TASK_TEMPLATE = """# Задача

## Что нужно получить
Коротко опишите ожидаемый результат.

## Контекст
Что уже известно и почему задача важна.

## Ограничения
Технические, регуляторные или процессные ограничения (если есть).

## Критерий готовности
Как понять, что документ можно отдавать в работу.
"""


class SearchRequest(BaseModel):
    query: str
    limit: int | None = None


class TaskRequest(BaseModel):
    task_id: str = Field(min_length=1)


class CreateTaskRequest(TaskRequest):
    task_text: str = Field(min_length=1)


class BuildContextPackRequest(TaskRequest):
    section: str | None = None
    limit: int | None = Field(default=None, ge=1, le=50)


class DraftRequest(TaskRequest):
    force_document_type: str | None = None
    sections: list[str] | None = None
    model: str | None = None


class GapAnalysisRequest(TaskRequest):
    draft_path: str | None = None
    model: str | None = None


class RefineRequest(TaskRequest):
    draft_path: str | None = None
    instructions: str | None = None
    model: str | None = None
    target_sections: list[str] | None = None


class RunPipelineRequest(TaskRequest):
    run_gaps: bool = True
    run_refine: bool = False
    force_document_type: str | None = None
    sections: list[str] | None = None
    refine_instructions: str | None = None
    run_target_sections: list[str] | None = None
    draft_model: str | None = None
    gap_model: str | None = None
    refine_model: str | None = None
    async_mode: bool = True


class ContainerControlRequest(BaseModel):
    services: list[str] | None = None


class ModelsPullRequest(BaseModel):
    models: list[str] | None = None
    force: bool = False


class AnalystProfileRequest(BaseModel):
    analyst_id: str = Field(min_length=1)
    login: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ConfluenceImportRequest(TaskRequest):
    analyst_id: str = Field(min_length=1)
    urls: list[str] = Field(min_length=1)


class HandoffRequest(TaskRequest):
    notes: str | None = None


def iso_from_timestamp(timestamp: float) -> str:
    """
    Convert unix timestamp to ISO string.
    """
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def list_regular_files(directory: Path) -> list[Path]:
    """
    List regular files sorted by modification time descending.
    """
    if not directory.exists():
        return []

    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.name != ".gitkeep"
    ]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files


def serialize_file(path: Path) -> dict:
    """
    Serialize file metadata for API responses.
    """
    stat = path.stat()
    return {
        "name": path.name,
        "size_bytes": stat.st_size,
        "modified_at": iso_from_timestamp(stat.st_mtime),
    }


def preview_text(path: Path, max_chars: int = PREVIEW_CHAR_LIMIT) -> str:
    """
    Load and truncate text preview from a file.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    if len(text) <= max_chars:
        return text

    return f"{text[:max_chars]}\n\n...[truncated]"


def read_json(path: Path) -> dict | None:
    """
    Read JSON file into dict when possible.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    return payload if isinstance(payload, dict) else None


def validate_artifact_kind(kind: str) -> str:
    """
    Validate artifact kind.
    """
    if kind not in ARTIFACT_KINDS:
        raise HTTPException(status_code=400, detail=f"Недопустимый вид артефакта: {kind}")
    return kind


@app.get("/ui", response_class=HTMLResponse)
def ui_page() -> str:
    """
    Serve analyst web interface.
    """
    if not UI_HTML_PATH.exists():
        raise HTTPException(status_code=500, detail="UI file is missing")

    return UI_HTML_PATH.read_text(encoding="utf-8")


@app.on_event("startup")
def startup_recover_pipeline_runs() -> None:
    """
    Mark in-progress pipeline runs as interrupted when service restarts.
    """
    recover_interrupted_pipeline_runs()


@app.get("/ui/task-template")
def ui_task_template() -> dict:
    """
    Return default task.md template.
    """
    template_path = TASKS_ROOT / "task.md.template"
    if template_path.exists():
        template_text = template_path.read_text(encoding="utf-8", errors="ignore")
    else:
        template_text = DEFAULT_TASK_TEMPLATE

    return {
        "status": "ok",
        "template": template_text,
    }


@app.post("/ui/create-task")
def ui_create_task(request: CreateTaskRequest) -> dict:
    """
    Create or update task.md file for a task.
    """
    safe_task_id = sanitize_task_id(request.task_id)
    if not request.task_text.strip():
        raise HTTPException(status_code=400, detail="Содержимое task.md не должно быть пустым")

    task_dir = TASKS_ROOT / "inbox" / safe_task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    attachments_dir = task_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    task_path = task_dir / "task.md"
    task_content = request.task_text.rstrip() + "\n"
    task_path.write_text(task_content, encoding="utf-8")

    return {
        "status": "ok",
        "task_id": safe_task_id,
        "task_path": str(task_path),
        "attachments_dir": str(attachments_dir),
    }


@app.post("/ui/upload-attachments/{task_id}")
async def ui_upload_attachments(task_id: str, files: list[UploadFile] = File(...)) -> dict:
    """
    Upload attachments for task context.
    """
    safe_task_id = sanitize_task_id(task_id)
    attachments_dir = TASKS_ROOT / "inbox" / safe_task_id / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    uploaded: list[dict] = []
    rejected: list[dict] = []

    for upload in files:
        original_name = upload.filename or ""
        safe_name = Path(original_name).name

        if not safe_name:
            rejected.append({
                "filename": original_name,
                "reason": "Пустое имя файла",
            })
            await upload.close()
            continue

        extension = Path(safe_name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            rejected.append({
                "filename": safe_name,
                "reason": f"Неподдерживаемый формат: {extension or 'без расширения'}",
            })
            await upload.close()
            continue

        target_path = attachments_dir / safe_name
        existed_before = target_path.exists()

        content = await upload.read()
        target_path.write_bytes(content)
        await upload.close()

        uploaded.append({
            "filename": safe_name,
            "size_bytes": len(content),
            "overwritten": existed_before,
        })

    return {
        "status": "ok",
        "task_id": safe_task_id,
        "uploaded": uploaded,
        "rejected": rejected,
    }


@app.post("/ui/analyst-profiles")
def ui_save_analyst_profile(request: AnalystProfileRequest) -> dict:
    """
    Save or update per-analyst Confluence credentials.
    """
    try:
        profile = save_analyst_profile(
            analyst_id=request.analyst_id,
            login=request.login,
            password=request.password,
        )
    except ConfluenceImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "ok",
        "profile": profile,
    }


@app.post("/ui/import-confluence")
def ui_import_confluence(request: ConfluenceImportRequest) -> dict:
    """
    Import Confluence pages into task attachments using stored analyst credentials.
    """
    safe_task_id = sanitize_task_id(request.task_id)
    task_dir = TASKS_ROOT / "inbox" / safe_task_id
    attachments_dir = task_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = import_confluence_urls(
            analyst_id=request.analyst_id,
            urls=request.urls,
            attachments_dir=attachments_dir,
        )
    except ConfluenceImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ошибка импорта Confluence: {exc}") from exc

    return {
        "status": "ok",
        "task_id": safe_task_id,
        **result,
    }


@app.get("/ui/state/{task_id}")
def ui_state(task_id: str) -> dict:
    """
    Return task state, analysis and generated artifacts.
    """
    safe_task_id = sanitize_task_id(task_id)

    task_dir = TASKS_ROOT / "inbox" / safe_task_id
    task_path = task_dir / "task.md"
    attachments_dir = task_dir / "attachments"

    task_exists = task_path.exists()
    task_text = task_path.read_text(encoding="utf-8", errors="ignore") if task_exists else ""

    attachments = [serialize_file(path) for path in list_regular_files(attachments_dir)]

    analysis = None
    analysis_error = None
    if task_exists:
        try:
            analysis = analyze_task(safe_task_id)
        except WorkflowError as exc:
            analysis_error = str(exc)

    artifacts: dict[str, list[dict]] = {}
    for kind in ARTIFACT_KINDS:
        kind_dir = ARTIFACTS_ROOT / kind / safe_task_id
        artifacts[kind] = [serialize_file(path) for path in list_regular_files(kind_dir)]

    latest_draft_preview = ""
    latest_review_preview = ""
    latest_handoff_preview = ""
    latest_pipeline = None

    draft_files = list_regular_files(ARTIFACTS_ROOT / "drafts" / safe_task_id)
    if draft_files:
        latest_draft_preview = preview_text(draft_files[0])

    review_files = list_regular_files(ARTIFACTS_ROOT / "reviews" / safe_task_id)
    if review_files:
        latest_review_preview = preview_text(review_files[0])

    handoff_files = list_regular_files(ARTIFACTS_ROOT / "handoffs" / safe_task_id)
    if handoff_files:
        latest_handoff_preview = preview_text(handoff_files[0])

    pipeline_files = list_regular_files(ARTIFACTS_ROOT / "pipeline_runs" / safe_task_id)
    if pipeline_files:
        latest_pipeline = read_json(pipeline_files[0])

    return {
        "status": "ok",
        "task_id": safe_task_id,
        "task_exists": task_exists,
        "task_path": str(task_path),
        "task_text": task_text,
        "attachments": attachments,
        "analysis": analysis,
        "analysis_error": analysis_error,
        "artifacts": artifacts,
        "latest_pipeline": latest_pipeline,
        "latest": {
            "draft_preview": latest_draft_preview,
            "gaps_preview": latest_review_preview,
            "handoff_preview": latest_handoff_preview,
        },
    }


@app.get("/ui/artifacts/{kind}/{task_id}/{filename}")
def ui_artifact_file(kind: str, task_id: str, filename: str):
    """
    Serve artifact file from allowed storage directories.
    """
    safe_kind = validate_artifact_kind(kind)
    safe_task_id = sanitize_task_id(task_id)

    safe_name = Path(filename).name
    if safe_name != filename or not safe_name:
        raise HTTPException(status_code=400, detail="Некорректное имя файла")

    artifact_path = ARTIFACTS_ROOT / safe_kind / safe_task_id / safe_name
    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Файл артефакта не найден")

    media_type = mimetypes.guess_type(artifact_path.name)[0] or "application/octet-stream"
    if artifact_path.suffix.lower() == ".md":
        media_type = "text/markdown"
    elif artifact_path.suffix.lower() == ".json":
        media_type = "application/json"

    return FileResponse(
        path=str(artifact_path),
        media_type=media_type,
        filename=safe_name,
    )


@app.get("/ui/ops/status")
def ui_operations_status() -> dict:
    """
    Return stack/container/model operational status for UI.
    """
    return {
        "status": "ok",
        "operations": get_operations_status(),
    }


@app.post("/ui/ops/containers/{action}")
def ui_control_containers(
    action: str,
    request: ContainerControlRequest | None = Body(default=None),
) -> dict:
    """
    Start/stop/restart selected containers through Docker API.
    """
    payload = request or ContainerControlRequest()

    try:
        result = control_containers(action, services=payload.services, default_stack=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Container operation failed: {exc}") from exc

    return {
        "status": "ok",
        "operation": result,
    }


@app.post("/ui/ops/models/pull")
def ui_pull_models(request: ModelsPullRequest | None = Body(default=None)) -> dict:
    """
    Start background pull for required or selected models.
    """
    payload = request or ModelsPullRequest()

    try:
        result = start_models_pull(models=payload.models, force=payload.force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Unable to start model pull: {exc}") from exc

    return {
        "status": "ok",
        **result,
    }


@app.get("/ui/ops/models/status")
def ui_models_status() -> dict:
    """
    Return model inventory and background pull status.
    """
    operations = get_operations_status()
    return {
        "status": "ok",
        "models": operations["models"],
        "model_pull": operations["model_pull"],
    }


@app.get("/health")
def health() -> dict:
    """
    Health check endpoint.
    """
    return {"status": "ok"}


@app.post("/reindex")
def reindex() -> dict:
    """
    Full reindex of global docs for semantic search.
    """
    result = reindex_all_documents()
    return {
        "status": "ok",
        "details": result,
    }


@app.post("/search")
def search(request: SearchRequest) -> dict:
    """
    Semantic search across indexed documents.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Поле `query` не должно быть пустым")

    try:
        results = search_documents(query=request.query, limit=request.limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ошибка поиска: {exc}") from exc

    return {
        "status": "ok",
        "results": results,
    }


@app.post("/analyze-task")
def analyze_task_endpoint(request: TaskRequest) -> dict:
    """
    Analyze task.md and detect document type + section plan.
    """
    try:
        result = analyze_task(request.task_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "ok",
        "analysis": result,
    }


@app.post("/build-context-pack")
def build_context_pack_endpoint(request: BuildContextPackRequest) -> dict:
    """
    Build context pack for one section or all detected sections.
    """
    try:
        analysis = analyze_task(request.task_id)

        if request.section:
            pack = build_context_pack(
                task_id=request.task_id,
                section=request.section,
                limit=request.limit,
                analysis=analysis,
            )
            return {
                "status": "ok",
                "context_packs": {request.section: pack},
            }

        packs: dict[str, dict] = {}
        for section in analysis["sections"]:
            packs[section] = build_context_pack(
                task_id=request.task_id,
                section=section,
                limit=request.limit,
                analysis=analysis,
            )

    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Не удалось собрать context pack: {exc}") from exc

    return {
        "status": "ok",
        "context_packs": packs,
    }


@app.post("/prepare-handoff")
def prepare_handoff_endpoint(request: HandoffRequest) -> dict:
    """
    Create Continue handoff and working copy for a task.
    """
    try:
        result = prepare_continue_handoff(
            task_id=request.task_id,
            notes=request.notes,
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Не удалось подготовить handoff: {exc}") from exc

    return {
        "status": "ok",
        "handoff": result,
    }


@app.post("/run-pipeline")
def run_pipeline_endpoint(request: RunPipelineRequest) -> dict:
    """
    Run full pipeline: analyze -> draft -> gap analysis -> optional refine.
    """
    if request.force_document_type and request.force_document_type not in {"ft", "nft"}:
        raise HTTPException(
            status_code=400,
            detail="`force_document_type` должен быть `ft` или `nft`",
        )

    if request.async_mode:
        return {
            "status": "ok",
            "pipeline": start_pipeline_run(
                task_id=request.task_id,
                run_gaps=request.run_gaps,
                run_refine=request.run_refine,
                force_document_type=request.force_document_type,
                sections=request.sections,
                refine_instructions=request.refine_instructions,
                run_target_sections=request.run_target_sections,
                draft_model=request.draft_model,
                gap_model=request.gap_model,
                refine_model=request.refine_model,
            ),
        }

    try:
        result = run_pipeline(
            task_id=request.task_id,
            run_gaps=request.run_gaps,
            run_refine=request.run_refine,
            force_document_type=request.force_document_type,
            sections=request.sections,
            refine_instructions=request.refine_instructions,
            run_target_sections=request.run_target_sections,
            draft_model=request.draft_model,
            gap_model=request.gap_model,
            refine_model=request.refine_model,
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}") from exc

    return {"status": "ok", "pipeline": result}


@app.get("/pipeline-status/{task_id}/{run_id}")
def pipeline_status(task_id: str, run_id: str) -> dict:
    """
    Read pipeline run state for UI polling.
    """
    safe_task_id = sanitize_task_id(task_id)
    try:
        payload = load_pipeline_status(safe_task_id, run_id)
        return {"status": "ok", "pipeline": payload}
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Cannot load pipeline status: {exc}") from exc


@app.post("/draft")
def draft_endpoint(request: DraftRequest) -> dict:
    """
    Generate section-based draft from task + context packs.
    """
    try:
        result = create_draft(
            task_id=request.task_id,
            force_document_type=request.force_document_type,
            sections=request.sections,
            model=request.model,
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ошибка генерации черновика: {exc}") from exc

    return {
        "status": "ok",
        "draft": result,
    }


@app.post("/gap-analysis")
def gap_analysis_endpoint(request: GapAnalysisRequest) -> dict:
    """
    Generate gap analysis for a draft.
    """
    try:
        result = run_gap_analysis(
            task_id=request.task_id,
            draft_path=request.draft_path,
            model=request.model,
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ошибка gap-analysis: {exc}") from exc

    return {
        "status": "ok",
        "gap_analysis": result,
    }


@app.post("/refine")
def refine_endpoint(request: RefineRequest) -> dict:
    """
    Refine latest or provided draft section-by-section.
    """
    try:
        result = refine_draft(
            task_id=request.task_id,
            draft_path=request.draft_path,
            instructions=request.instructions,
            model=request.model,
            target_sections=request.target_sections,
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ошибка refine: {exc}") from exc

    return {
        "status": "ok",
        "refine": result,
    }
