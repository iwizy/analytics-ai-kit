"""
Main application entrypoint for the local analytics RAG service.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.ingest import reindex_all_documents
from app.search import search_documents
from app.workflow import (
    WorkflowError,
    analyze_task,
    build_context_pack,
    create_draft,
    refine_draft,
    run_gap_analysis,
)

app = FastAPI(title="Analytics RAG Service", version="0.2.0")


class SearchRequest(BaseModel):
    query: str
    limit: int | None = None


class TaskRequest(BaseModel):
    task_id: str = Field(min_length=1)


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
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ошибка refine: {exc}") from exc

    return {
        "status": "ok",
        "refine": result,
    }
