"""
Task-to-draft workflow with section routing, context packs, gap analysis, and refine.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml

from app.chunking import chunk_text
from app.documents import collect_supported_files, extract_text
from app.environment_state import get_runtime_model_bundle
from app.llm import generate_text, load_text_file, render_template
from app.search import search_documents
from app.settings import (
    ARTIFACTS_ROOT,
    CONTEXT_PACK_LIMIT,
    DOCS_ROOT,
    DRAFT_MODEL,
    PIPELINE_DRAFT_MODEL,
    PIPELINE_GAP_MODEL,
    PIPELINE_REFINE_MODEL,
    PIPELINE_SECTION_WORKERS,
    FT_SECTIONS,
    GLOBAL_CONTEXT_CATEGORIES,
    NFT_SECTIONS,
    REFINE_MODEL,
    REVIEW_MODEL,
    SECTION_DISPLAY_NAMES,
    TASKS_ROOT,
)


class WorkflowError(ValueError):
    """
    Raised when workflow input is invalid or required files are missing.
    """


GENERATION_CATALOG_PATH = DOCS_ROOT / "templates" / "catalog.yaml"
GENERATION_PROMPT_PATH = DOCS_ROOT / "templates" / "prompts" / "draft_document.md"


@dataclass(frozen=True)
class RoutingRule:
    """
    Routing settings for section-level context retrieval.
    """

    global_categories: tuple[str, ...]
    query_hint: str
    path_keywords: tuple[str, ...]


@dataclass
class ScoredSnippet:
    """
    Context snippet with ranking score and source metadata.
    """

    source_level: str
    source_path: str
    category: str
    score: float
    text: str


SECTION_ROUTING: dict[str, RoutingRule] = {
    "business_requirements": RoutingRule(
        global_categories=("input", "examples"),
        query_hint="бизнес требования процесс сценарий пользователь ценность",
        path_keywords=("business", "product", "requirement", "feature", "use", "пример", "процесс"),
    ),
    "internal_integrations": RoutingRule(
        global_categories=("input", "glossary", "examples"),
        query_hint="внутренние интеграции системы api сервис контракт данные",
        path_keywords=("integration", "internal", "system", "api", "service", "интеграц", "система"),
    ),
    "external_integrations": RoutingRule(
        global_categories=("input", "examples", "glossary"),
        query_hint="внешние интеграции провайдер партнер api webhook обмен",
        path_keywords=("external", "partner", "vendor", "gateway", "api", "интеграц", "внеш"),
    ),
    "validations": RoutingRule(
        global_categories=("input", "examples", "glossary"),
        query_hint="валидация проверка правило формат обязательность ошибка",
        path_keywords=("validation", "rule", "check", "schema", "валид", "правил"),
    ),
    "errors": RoutingRule(
        global_categories=("input", "examples", "glossary"),
        query_hint="ошибка исключение сбой retry отказ",
        path_keywords=("error", "exception", "fail", "retry", "ошиб", "сбой"),
    ),
    "open_questions": RoutingRule(
        global_categories=("input", "examples", "glossary"),
        query_hint="неопределенность допущение риск вопрос",
        path_keywords=("risk", "assumption", "unknown", "gap", "вопрос", "риск"),
    ),
    "performance": RoutingRule(
        global_categories=("input", "examples", "glossary"),
        query_hint="производительность latency throughput нагрузка rps",
        path_keywords=("performance", "latency", "load", "capacity", "производ", "нагруз"),
    ),
    "availability": RoutingRule(
        global_categories=("input", "examples", "glossary"),
        query_hint="доступность sla slo failover отказоустойчивость",
        path_keywords=("availability", "sla", "slo", "uptime", "failover", "доступ"),
    ),
    "security": RoutingRule(
        global_categories=("input", "glossary", "examples"),
        query_hint="безопасность доступ роли секреты pii комплаенс",
        path_keywords=("security", "auth", "permission", "secret", "pii", "безопас", "доступ"),
    ),
    "logging": RoutingRule(
        global_categories=("input", "examples", "glossary"),
        query_hint="логирование события журнал trace correlation",
        path_keywords=("logging", "log", "trace", "observability", "лог", "трасс"),
    ),
    "audit": RoutingRule(
        global_categories=("input", "examples", "glossary"),
        query_hint="аудит действия изменения расследование",
        path_keywords=("audit", "history", "investigation", "аудит", "расслед"),
    ),
    "retention": RoutingRule(
        global_categories=("input", "glossary", "examples"),
        query_hint="retention хранение архивирование удаление срок",
        path_keywords=("retention", "archive", "delete", "storage", "хранен", "архив"),
    ),
    "constraints": RoutingRule(
        global_categories=("input", "examples", "glossary"),
        query_hint="ограничения допущения зависимости риск",
        path_keywords=("constraint", "limitation", "dependency", "огранич", "зависим"),
    ),
}

_PIPELINE_LOCK = threading.RLock()
PIPELINE_STAGE_NAMES = ["analyze", "draft", "gaps", "refine", "finalize"]
INTERRUPTED_PIPELINE_MESSAGE = (
    "Пайплайн был прерван перезапуском сервиса. Запустите его повторно."
)


@dataclass
class PipelineRun:
    """
    Runtime metadata for a pipeline job.
    """

    task_id: str
    run_id: str
    state: str
    started_at: str
    finished_at: str | None = None
    stages: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")
TOKEN_PATTERN = re.compile(r"[a-zA-Zа-яА-Я0-9_]{3,}")
SERVICE_HINT_PATTERN = re.compile(r"(?im)^\s*(?:сервис|service|component)\s*[:\-]\s*(.+)$")
TYPE_HINT_PATTERN = re.compile(
    r"(?im)^\s*(?:тип\s+документа|документ|document\s*type|document_type)\s*[:\-]\s*(ft|nft|auto)$"
)

FT_HINTS = (
    "бизнес",
    "функц",
    "сценар",
    "пользоват",
    "валидац",
    "интеграц",
    "процесс",
)

NFT_HINTS = (
    "производ",
    "доступност",
    "безопас",
    "лог",
    "аудит",
    "retention",
    "sla",
    "slo",
    "latency",
    "throughput",
)


def utc_timestamp() -> str:
    """
    Build a filesystem-safe UTC timestamp.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def utc_iso() -> str:
    """
    Build ISO UTC timestamp for response payloads.
    """
    return datetime.now(timezone.utc).isoformat()


def sanitize_task_id(task_id: str) -> str:
    """
    Validate task id and strip spaces.
    """
    normalized = task_id.strip()
    if not normalized:
        raise WorkflowError("`task_id` не должен быть пустым")

    if not TASK_ID_PATTERN.match(normalized):
        raise WorkflowError(
            "`task_id` содержит недопустимые символы; используйте буквы, цифры, точку, underscore и дефис"
        )

    return normalized


def detect_pipeline_patterns(task_text: str) -> dict[str, str | None]:
    """
    Parse lightweight metadata from task.md to improve routing and auto-discovery.
    """
    lowered = task_text.lower()
    service_match = SERVICE_HINT_PATTERN.search(task_text)
    type_match = TYPE_HINT_PATTERN.search(task_text)

    service = None
    if service_match:
        service = service_match.group(1).strip().splitlines()[0].strip()
    elif "микросервис" in lowered and "сервис" in lowered:
        header_match = re.search(r"(?mi)^#\s*(?:микро)?сервис[:\s-]*(.+)$", task_text)
        if header_match:
            service = header_match.group(1).strip()

    if service:
        service = service.split(" ")[0].strip().lower().replace("`", "")

    detected_type = None
    if type_match:
        detected_type = type_match.group(1).lower()
        if detected_type == "auto":
            detected_type = None

    return {
        "service": service,
        "document_type": detected_type,
    }


def resolve_task_paths(task_id: str) -> tuple[Path, Path, Path]:
    """
    Resolve task directory, task.md and attachments folder.
    """
    safe_task_id = sanitize_task_id(task_id)
    task_dir = TASKS_ROOT / "inbox" / safe_task_id
    task_path = task_dir / "task.md"
    attachments_dir = task_dir / "attachments"

    if not task_path.exists():
        raise WorkflowError(f"Файл task.md не найден для task_id='{safe_task_id}'")

    return task_dir, task_path, attachments_dir


def normalize_service_fragment(value: str | None) -> str | None:
    """
    Normalize service token for filesystem matching and routing.
    """
    if not value:
        return None

    normalized = re.sub(r"[^a-zа-я0-9._-]", "-", value.strip().lower(), flags=re.IGNORECASE)
    normalized = normalized.strip(".-_")
    return normalized or None


def collect_service_context_candidates(task_dir: Path, service: str | None) -> list[Path]:
    """
    Find service-scoped docs from task-specific files and docs hierarchy.
    """
    normalized = normalize_service_fragment(service)
    if not normalized:
        return []

    tokens = set(normalize_service_fragment(service).split("-")) if normalized else set()
    if not tokens:
        return []

    candidates: list[Path] = []
    search_roots = [DOCS_ROOT / category for category in GLOBAL_CONTEXT_CATEGORIES]
    search_roots.append(DOCS_ROOT / "services")
    search_roots.append(task_dir)

    service_markers = (
        "service",
        "microservice",
        "внутрен",
        "интегра",
        "business",
        "architecture",
        "overview",
        "api",
        "requirements",
        "integration",
    )

    for root in search_roots:
        if not root.exists():
            continue
        for path in collect_supported_files(root):
            rel_path = str(path.relative_to(root)).lower()
            if any(token in rel_path for token in tokens) and any(
                marker in rel_path for marker in service_markers
            ):
                if path.name.lower() != "task.md":
                    candidates.append(path)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path not in seen:
            deduped.append(path)
            seen.add(path)

    return deduped


def tokenize(text: str) -> set[str]:
    """
    Tokenize text for lightweight lexical ranking.
    """
    return {token.lower() for token in TOKEN_PATTERN.findall(text.lower())}


def lexical_score(chunk: str, query_tokens: set[str], extra_tokens: set[str]) -> float:
    """
    Score a chunk by overlap with query and section-specific tokens.
    """
    chunk_tokens = tokenize(chunk)
    if not chunk_tokens:
        return 0.0

    query_overlap = len(chunk_tokens & query_tokens)
    extra_overlap = len(chunk_tokens & extra_tokens)
    return (query_overlap * 2.0) + (extra_overlap * 1.0)


def run_id() -> str:
    """
    Build unique pipeline run identifier.
    """
    return f"{utc_timestamp()}_{datetime.now(timezone.utc).microsecond:06d}"


def pipeline_status_path(task_id: str, run_id_value: str) -> Path:
    """
    Build pipeline status file path.
    """
    return ensure_artifacts_dir("pipeline_runs", task_id) / f"{run_id_value}.json"


def init_pipeline_status(task_id: str, run_id_value: str, *, stage_names: list[str]) -> PipelineRun:
    """
    Initialize on-disk pipeline status.
    """
    existing_path = pipeline_status_path(task_id, run_id_value)
    if existing_path.exists():
        payload = json.loads(existing_path.read_text(encoding="utf-8"))
        return PipelineRun(
            task_id=str(payload.get("task_id") or task_id),
            run_id=str(payload.get("run_id") or run_id_value),
            state=str(payload.get("state") or "running"),
            started_at=str(payload.get("started_at") or utc_iso()),
            finished_at=payload.get("finished_at"),
            stages=list(payload.get("stages") or []),
            result=dict(payload.get("result") or {}),
            errors=list(payload.get("errors") or []),
        )

    status = PipelineRun(
        task_id=task_id,
        run_id=run_id_value,
        state="running",
        started_at=utc_iso(),
        stages=[
            {
                "name": name,
                "state": "pending",
                "started_at": None,
                "finished_at": None,
                "error": None,
            }
            for name in stage_names
        ],
        result={},
        errors=[],
    )
    write_pipeline_status(task_id, run_id_value, status)
    return status


def write_pipeline_status(task_id: str, run_id_value: str, status: PipelineRun) -> None:
    """
    Persist pipeline status to artifact for UI polling and recovery.
    """
    payload = {
        "task_id": status.task_id,
        "run_id": status.run_id,
        "state": status.state,
        "started_at": status.started_at,
        "finished_at": status.finished_at,
        "stages": status.stages or [],
        "result": status.result or {},
        "errors": status.errors or [],
    }
    pipeline_status_path(task_id, run_id_value).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_pipeline_status_record(task_id: str, run_id_value: str) -> PipelineRun:
    """
    Read pipeline status from disk and convert it to dataclass form.
    """
    path = pipeline_status_path(task_id, run_id_value)
    if not path.exists():
        raise WorkflowError(f"Запись о пайплайне не найдена: {run_id_value}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    return PipelineRun(
        task_id=str(payload.get("task_id") or task_id),
        run_id=str(payload.get("run_id") or run_id_value),
        state=str(payload.get("state") or "running"),
        started_at=str(payload.get("started_at") or utc_iso()),
        finished_at=payload.get("finished_at"),
        stages=list(payload.get("stages") or []),
        result=dict(payload.get("result") or {}),
        errors=list(payload.get("errors") or []),
    )


def update_pipeline_stage(
    task_id: str,
    run_id_value: str,
    stage_name: str,
    *,
    state: str,
    details: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """
    Update one pipeline stage and persist status.
    """
    with _PIPELINE_LOCK:
        try:
            run = read_pipeline_status_record(task_id, run_id_value)
        except WorkflowError:
            return

        for stage in run.stages or []:
            if stage["name"] == stage_name:
                if state == "running" and stage.get("started_at") is None:
                    stage["started_at"] = utc_iso()
                if state in {"done", "failed", "skipped"}:
                    stage["finished_at"] = utc_iso()
                stage["state"] = state
                if details is not None:
                    stage["details"] = details
                if error is not None:
                    stage["error"] = error

        if error is not None:
            run.errors.append(error)

        write_pipeline_status(task_id, run_id_value, run)


def complete_pipeline_status(task_id: str, run_id_value: str, *, state: str, result: dict[str, Any]) -> None:
    """
    Finish pipeline and persist final status.
    """
    with _PIPELINE_LOCK:
        try:
            run = read_pipeline_status_record(task_id, run_id_value)
        except WorkflowError:
            return
        run.state = state
        run.finished_at = utc_iso()
        run.result = result
        write_pipeline_status(task_id, run_id_value, run)


def load_pipeline_status(task_id: str, run_id_value: str) -> dict[str, Any]:
    """
    Load pipeline status from disk for UI polling.
    """
    path = pipeline_status_path(task_id, run_id_value)
    if not path.exists():
        raise WorkflowError(f"Запись о пайплайне не найдена: {run_id_value}")

    return json.loads(path.read_text(encoding="utf-8"))


def recover_interrupted_pipeline_runs() -> int:
    """
    Mark stale in-progress pipeline runs as interrupted after service restart.
    """
    pipeline_root = ARTIFACTS_ROOT / "pipeline_runs"
    if not pipeline_root.exists():
        return 0

    recovered = 0
    for path in pipeline_root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if payload.get("state") != "running":
            continue

        finished_at = utc_iso()
        payload["state"] = "interrupted"
        payload["finished_at"] = finished_at

        errors = list(payload.get("errors") or [])
        if INTERRUPTED_PIPELINE_MESSAGE not in errors:
            errors.append(INTERRUPTED_PIPELINE_MESSAGE)
        payload["errors"] = errors

        for stage in payload.get("stages") or []:
            stage_state = stage.get("state")
            if stage_state == "running":
                stage["state"] = "interrupted"
                stage["finished_at"] = finished_at
                stage["error"] = INTERRUPTED_PIPELINE_MESSAGE
            elif stage_state == "pending":
                stage["state"] = "skipped"
                stage["finished_at"] = finished_at
                stage.setdefault("details", {"reason": "service_restarted"})

        result = dict(payload.get("result") or {})
        result["status"] = "interrupted"
        result["error"] = INTERRUPTED_PIPELINE_MESSAGE
        payload["result"] = result

        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        recovered += 1

    return recovered


def to_relative_label(path: Path, root: Path) -> str:
    """
    Convert path to human-readable relative label.
    """
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def file_text_chunks(path: Path) -> list[str]:
    """
    Load a document and split it into chunks.
    """
    text = extract_text(path)
    if not text.strip():
        return []

    return chunk_text(text)


def detect_document_type(task_text: str) -> tuple[str, dict[str, Any]]:
    """
    Detect document type from task text using heuristic keyword scoring.
    """
    lowered = task_text.lower()

    ft_hits = [hint for hint in FT_HINTS if hint in lowered]
    nft_hits = [hint for hint in NFT_HINTS if hint in lowered]

    ft_score = len(ft_hits)
    nft_score = len(nft_hits)

    if nft_score > ft_score:
        return "nft", {
            "ft_score": ft_score,
            "nft_score": nft_score,
            "matched_ft_hints": ft_hits,
            "matched_nft_hints": nft_hits,
        }

    return "ft", {
        "ft_score": ft_score,
        "nft_score": nft_score,
        "matched_ft_hints": ft_hits,
        "matched_nft_hints": nft_hits,
    }


def build_task_summary(task_text: str) -> str:
    """
    Build short task summary from first non-empty lines.
    """
    clean_lines = [line.strip() for line in task_text.splitlines() if line.strip()]
    if not clean_lines:
        return ""

    summary = " ".join(clean_lines[:4])
    return summary[:500]


def analyze_task(task_id: str) -> dict[str, Any]:
    """
    Analyze task.md and return document type, sections and metadata.
    """
    safe_task_id = sanitize_task_id(task_id)
    task_dir, task_path, attachments_dir = resolve_task_paths(safe_task_id)

    task_text = task_path.read_text(encoding="utf-8", errors="ignore")
    if not task_text.strip():
        raise WorkflowError("Файл task.md пустой")

    attachment_files = collect_supported_files(attachments_dir)
    parsed = detect_pipeline_patterns(task_text)
    force_type = parsed.get("document_type")
    service = parsed.get("service")

    document_type, detection_meta = (force_type, {}) if force_type else detect_document_type(task_text)
    if force_type:
        detection_meta = {
            "ft_score": None,
            "nft_score": None,
            "matched_ft_hints": [],
            "matched_nft_hints": [],
            "forced_by_task": force_type,
        }

    sections = FT_SECTIONS if document_type == "ft" else NFT_SECTIONS

    service_docs = collect_service_context_candidates(task_dir, service)

    return {
        "task_id": safe_task_id,
        "task_dir": str(task_dir),
        "task_path": str(task_path),
        "attachments_dir": str(attachments_dir),
        "attachments": [to_relative_label(path, TASKS_ROOT) for path in attachment_files],
        "attachments_count": len(attachment_files),
        "task_summary": build_task_summary(task_text),
        "document_type": document_type,
        "service": service,
        "service_context_candidates": [to_relative_label(path, TASKS_ROOT) for path in service_docs],
        "service_context_count": len(service_docs),
        "sections": sections,
        "section_display_names": {
            section: SECTION_DISPLAY_NAMES.get(section, section) for section in sections
        },
        "detection": detection_meta,
    }


def default_routing_rule(section: str) -> RoutingRule:
    """
    Provide fallback routing rule for unknown section names.
    """
    return RoutingRule(
        global_categories=GLOBAL_CONTEXT_CATEGORIES,
        query_hint=section,
        path_keywords=(),
    )


def choose_rule(section: str) -> RoutingRule:
    """
    Get a routing rule for a section.
    """
    return SECTION_ROUTING.get(section, default_routing_rule(section))


def collect_task_snippets(
    *,
    task_path: Path,
    attachments_dir: Path,
    query_text: str,
    section: str,
    service_paths: list[Path] | None = None,
) -> list[ScoredSnippet]:
    """
    Collect and rank snippets from task.md and task attachments.
    """
    query_tokens = tokenize(query_text)
    section_tokens = tokenize(section)
    snippets: list[ScoredSnippet] = []

    task_text = task_path.read_text(encoding="utf-8", errors="ignore")
    for chunk in chunk_text(task_text):
        score = lexical_score(chunk, query_tokens, section_tokens) + 3.0
        snippets.append(
            ScoredSnippet(
                source_level="task",
                source_path=to_relative_label(task_path, TASKS_ROOT),
                category="task",
                score=score,
                text=chunk,
            )
        )

    for file_path in collect_supported_files(attachments_dir):
        rel_path = to_relative_label(file_path, TASKS_ROOT)
        file_path_lower = rel_path.lower()
        path_boost = 1.5 if any(token in file_path_lower for token in section_tokens) else 0.0

        for chunk in file_text_chunks(file_path):
            score = lexical_score(chunk, query_tokens, section_tokens) + 2.0 + path_boost
            snippets.append(
                ScoredSnippet(
                    source_level="attachment",
                    source_path=rel_path,
                    category="attachment",
                    score=score,
                    text=chunk,
                )
            )

    for file_path in service_paths or []:
        rel_path = to_relative_label(file_path, TASKS_ROOT if TASKS_ROOT in file_path.parents else DOCS_ROOT)
        file_path_lower = rel_path.lower()
        path_boost = 2.0 if any(token in file_path_lower for token in section_tokens) else 0.5

        for chunk in file_text_chunks(file_path):
            score = lexical_score(chunk, query_tokens, section_tokens) + 1.8 + path_boost
            snippets.append(
                ScoredSnippet(
                    source_level="service_context",
                    source_path=rel_path,
                    category="service",
                    score=score,
                    text=chunk,
                )
            )

    snippets.sort(key=lambda item: item.score, reverse=True)
    return snippets


def collect_global_snippets_from_qdrant(
    *,
    query_text: str,
    rule: RoutingRule,
    limit: int,
) -> list[ScoredSnippet]:
    """
    Pull semantic snippets from indexed global docs in Qdrant.
    """
    snippets: list[ScoredSnippet] = []

    try:
        hits = search_documents(query=query_text, limit=max(limit * 4, 12))
    except Exception:
        return []

    for hit in hits:
        category = str(hit.get("category") or "")
        source_path = str(hit.get("source_path") or "")
        text = str(hit.get("text") or "").strip()

        if category not in rule.global_categories:
            continue

        if not text:
            continue

        source_path_lower = source_path.lower()
        path_boost = 0.35 if any(keyword in source_path_lower for keyword in rule.path_keywords) else 0.0

        snippets.append(
            ScoredSnippet(
                source_level="global_index",
                source_path=source_path,
                category=category,
                score=float(hit.get("score") or 0.0) + path_boost,
                text=text,
            )
        )

    snippets.sort(key=lambda item: item.score, reverse=True)
    return snippets[:limit]


def collect_global_snippets_from_files(
    *,
    query_text: str,
    rule: RoutingRule,
    limit: int,
) -> list[ScoredSnippet]:
    """
    Fallback lexical retrieval directly from global docs files.
    """
    query_tokens = tokenize(query_text)
    section_tokens = tokenize(rule.query_hint)
    snippets: list[ScoredSnippet] = []

    for category in rule.global_categories:
        category_dir = DOCS_ROOT / category
        for file_path in collect_supported_files(category_dir):
            rel_path = to_relative_label(file_path, DOCS_ROOT)
            rel_path_lower = rel_path.lower()
            path_boost = 2.0 if any(keyword in rel_path_lower for keyword in rule.path_keywords) else 0.0

            for chunk in file_text_chunks(file_path):
                score = lexical_score(chunk, query_tokens, section_tokens) + path_boost
                if score <= 0:
                    continue

                snippets.append(
                    ScoredSnippet(
                        source_level="global_files",
                        source_path=rel_path,
                        category=category,
                        score=score,
                        text=chunk,
                    )
                )

    snippets.sort(key=lambda item: item.score, reverse=True)
    return snippets[:limit]


def deduplicate_snippets(snippets: list[ScoredSnippet], limit: int) -> list[ScoredSnippet]:
    """
    Deduplicate snippets by source+text and keep best-ranked items.
    """
    deduped: list[ScoredSnippet] = []
    seen: set[str] = set()

    for snippet in snippets:
        key = f"{snippet.source_path}::{snippet.text[:200]}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(snippet)
        if len(deduped) >= limit:
            break

    return deduped


def format_context_block(snippets: list[ScoredSnippet]) -> str:
    """
    Convert snippets into LLM-friendly context text block.
    """
    lines: list[str] = []

    for index, snippet in enumerate(snippets, start=1):
        preview = snippet.text.strip()
        if len(preview) > 1500:
            preview = f"{preview[:1500]}..."

        lines.append(
            (
                f"[{index}] source_level={snippet.source_level}; "
                f"category={snippet.category}; source={snippet.source_path}\n{preview}"
            )
        )

    return "\n\n".join(lines)


def ensure_artifacts_dir(kind: str, task_id: str) -> Path:
    """
    Ensure per-task artifacts folder exists.
    """
    path = ARTIFACTS_ROOT / kind / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """
    Write JSON payload with UTF-8 and stable formatting.
    """
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def latest_artifact_path(task_id: str, kind: str, pattern: str = "*") -> Path | None:
    """
    Return latest artifact file for task and kind.
    """
    artifact_dir = ARTIFACTS_ROOT / kind / task_id
    if not artifact_dir.exists():
        return None

    candidates = [path for path in artifact_dir.glob(pattern) if path.is_file()]
    if not candidates:
        return None

    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0]


def build_continue_working_copy(
    *,
    task_id: str,
    source_draft_path: Path | None,
    document_type: str,
) -> Path | None:
    """
    Create analyst-editable draft copy for Continue sessions.
    """
    if source_draft_path is None or not source_draft_path.exists():
        return None

    drafts_dir = ensure_artifacts_dir("drafts", task_id)
    working_copy_path = drafts_dir / f"{utc_timestamp()}_continue_workspace_{document_type}.md"
    working_copy_path.write_text(
        source_draft_path.read_text(encoding="utf-8", errors="ignore"),
        encoding="utf-8",
    )
    return working_copy_path


def render_continue_handoff(
    *,
    task_id: str,
    analysis: dict[str, Any],
    task_path: Path,
    attachment_labels: list[str],
    confluence_labels: list[str],
    latest_draft_path: Path | None,
    latest_gaps_path: Path | None,
    latest_context_pack_path: Path | None,
    latest_pipeline_path: Path | None,
    working_copy_path: Path | None,
    notes: str | None,
) -> str:
    """
    Render markdown handoff for VS Code + Continue workflow.
    """
    sections = analysis.get("sections") or []
    document_type = analysis.get("document_type") or "unknown"
    service = analysis.get("service") or "not detected"

    lines = [
        "# Continue handoff",
        "",
        f"Generated at: {utc_iso()}",
        f"Task ID: {task_id}",
        f"Task file: {task_path}",
        f"Detected document type: {document_type}",
        f"Detected service: {service}",
        f"Sections: {', '.join(sections) if sections else '-'}",
        "",
        "## Ready files",
        f"- Latest system draft: {latest_draft_path or '-'}",
        f"- Continue working copy: {working_copy_path or '-'}",
        f"- Latest gaps: {latest_gaps_path or '-'}",
        f"- Latest context pack: {latest_context_pack_path or '-'}",
        f"- Latest pipeline status: {latest_pipeline_path or '-'}",
        "",
        "## Source files",
        f"- task.md: {task_path}",
        f"- Attachments count: {len(attachment_labels)}",
    ]

    if attachment_labels:
        lines.extend([f"- attachment: {label}" for label in attachment_labels[:20]])

    if confluence_labels:
        lines.extend(["", "## Imported from Confluence"])
        lines.extend([f"- {label}" for label in confluence_labels[:20]])

    if notes:
        lines.extend(["", "## Notes", notes.strip()])

    lines.extend(
        [
            "",
            "## Suggested Continue prompts",
            (
                f"1. Прочитай этот handoff и открой рабочую копию "
                f"`{working_copy_path or latest_draft_path or task_path}`. "
                "Продолжи доработку документа без вымышленных фактов."
            ),
            (
                f"2. Сравни `{working_copy_path or latest_draft_path or task_path}` "
                f"c `{latest_gaps_path or task_path}` и устрани критичные пробелы."
            ),
            (
                "3. Если информации не хватает, сформулируй список открытых вопросов "
                "для аналитика в конце документа."
            ),
            "",
            "## Power mode workflow",
            "- Открой workspace в VS Code с установленным Continue.",
            "- Начни работу с этого handoff файла как точки входа.",
            "- Редактируй только рабочую копию или создавай новую версию рядом, не перетирая системные артефакты.",
        ]
    )

    return "\n".join(lines).strip() + "\n"


def prepare_continue_handoff(
    *,
    task_id: str,
    analysis: dict[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """
    Build handoff artifact and analyst-editable draft copy for Continue.
    """
    safe_task_id = sanitize_task_id(task_id)
    resolved_analysis = analysis or analyze_task(safe_task_id)
    _, task_path, attachments_dir = resolve_task_paths(safe_task_id)

    attachment_files = collect_supported_files(attachments_dir)
    attachment_labels = [to_relative_label(path, TASKS_ROOT) for path in attachment_files]
    confluence_labels = [
        to_relative_label(path, TASKS_ROOT)
        for path in attachment_files
        if path.name.startswith("confluence_")
    ]

    latest_draft_path = None
    drafts_dir = ARTIFACTS_ROOT / "drafts" / safe_task_id
    if drafts_dir.exists():
        draft_candidates = [
            path
            for path in drafts_dir.glob("*.md")
            if path.is_file() and "_continue_workspace_" not in path.name
        ]
        draft_candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        if draft_candidates:
            latest_draft_path = draft_candidates[0]

    latest_gaps_path = latest_artifact_path(safe_task_id, "reviews", "*.md")
    latest_context_pack_path = latest_artifact_path(safe_task_id, "context_packs", "*.json")
    latest_pipeline_path = latest_artifact_path(safe_task_id, "pipeline_runs", "*.json")

    document_type = resolved_analysis.get("document_type") or "ft"
    if latest_draft_path and latest_draft_path.suffix.lower() == ".md":
        draft_type = extract_draft_document_type(
            latest_draft_path.read_text(encoding="utf-8", errors="ignore")
        )
        if draft_type:
            document_type = draft_type

    working_copy_path = build_continue_working_copy(
        task_id=safe_task_id,
        source_draft_path=latest_draft_path,
        document_type=document_type,
    )

    handoff_dir = ensure_artifacts_dir("handoffs", safe_task_id)
    handoff_path = handoff_dir / f"{utc_timestamp()}_handoff.md"
    handoff_path.write_text(
        render_continue_handoff(
            task_id=safe_task_id,
            analysis=resolved_analysis,
            task_path=task_path,
            attachment_labels=attachment_labels,
            confluence_labels=confluence_labels,
            latest_draft_path=latest_draft_path,
            latest_gaps_path=latest_gaps_path,
            latest_context_pack_path=latest_context_pack_path,
            latest_pipeline_path=latest_pipeline_path,
            working_copy_path=working_copy_path,
            notes=notes,
        ),
        encoding="utf-8",
    )

    return {
        "task_id": safe_task_id,
        "handoff_path": str(handoff_path),
        "working_copy_path": str(working_copy_path) if working_copy_path else None,
        "latest_draft_path": str(latest_draft_path) if latest_draft_path else None,
        "latest_gaps_path": str(latest_gaps_path) if latest_gaps_path else None,
    }


def build_context_pack(
    *,
    task_id: str,
    section: str,
    limit: int | None = None,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build section-level context pack from global docs and task attachments.
    """
    safe_task_id = sanitize_task_id(task_id)
    resolved_analysis = analysis or analyze_task(safe_task_id)

    task_dir, task_path, attachments_dir = resolve_task_paths(safe_task_id)
    task_text = task_path.read_text(encoding="utf-8", errors="ignore")

    context_limit = limit or CONTEXT_PACK_LIMIT
    rule = choose_rule(section)
    service_files: list[Path] = []
    service = (resolved_analysis.get("service") or "").strip() if isinstance(resolved_analysis, dict) else ""
    if service:
        service_files = collect_service_context_candidates(task_dir, service)

    query_text = "\n".join(
        [
            section,
            rule.query_hint,
            resolved_analysis.get("task_summary") or "",
            task_text[:2000],
        ]
    )

    task_snippets = collect_task_snippets(
        task_path=task_path,
        attachments_dir=attachments_dir,
        query_text=query_text,
        section=section,
        service_paths=service_files,
    )

    global_quota = max(2, context_limit // 2)
    task_quota = max(2, context_limit - global_quota)

    global_index_snippets = collect_global_snippets_from_qdrant(
        query_text=query_text,
        rule=rule,
        limit=global_quota,
    )

    remaining_global = max(0, global_quota - len(global_index_snippets))
    global_file_snippets: list[ScoredSnippet] = []
    if remaining_global > 0:
        global_file_snippets = collect_global_snippets_from_files(
            query_text=query_text,
            rule=rule,
            limit=remaining_global * 2,
        )

    selected: list[ScoredSnippet] = []
    selected.extend(task_snippets[:task_quota])
    selected.extend(global_index_snippets[:global_quota])
    selected.extend(global_file_snippets[:remaining_global])

    if len(selected) < context_limit:
        spillover = (
            task_snippets[task_quota:]
            + global_index_snippets[global_quota:]
            + global_file_snippets[remaining_global:]
        )
        selected.extend(spillover)

    selected.sort(key=lambda item: item.score, reverse=True)
    selected = deduplicate_snippets(selected, context_limit)

    context_pack = {
        "task_id": safe_task_id,
        "section": section,
        "document_type": resolved_analysis["document_type"],
        "created_at": utc_iso(),
        "routing": {
            "global_categories": list(rule.global_categories),
            "query_hint": rule.query_hint,
            "path_keywords": list(rule.path_keywords),
        },
        "sources": [
            {
                "source_level": snippet.source_level,
                "source_path": snippet.source_path,
                "category": snippet.category,
                "score": round(snippet.score, 4),
                "text": snippet.text,
            }
            for snippet in selected
        ],
        "debug": {
            "task_dir": str(task_dir),
            "docs_root": str(DOCS_ROOT),
        },
    }

    task_level_snippets = [snippet for snippet in task_snippets if snippet.source_level in {"task", "attachment"}]
    context_pack["coverage"] = {
        "source_count": len(selected),
        "task_level_snippets": len(task_level_snippets),
        "service_snippets": len([snippet for snippet in selected if snippet.source_level == "service_context"]),
        "global_snippets": len([snippet for snippet in selected if snippet.source_level.startswith("global")]),
        "limit": context_limit,
    }

    context_dir = ensure_artifacts_dir("context_packs", safe_task_id)
    context_path = context_dir / f"{utc_timestamp()}_{section}.json"
    write_json(context_path, context_pack)

    context_pack["context_pack_path"] = str(context_path)
    return context_pack


def load_generation_catalog() -> dict[str, Any]:
    """
    Load document generation target catalog from docs/templates/catalog.yaml.
    """
    if not GENERATION_CATALOG_PATH.exists():
        raise WorkflowError(f"Каталог документов не найден: {GENERATION_CATALOG_PATH}")

    try:
        payload = yaml.safe_load(GENERATION_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise WorkflowError(f"Не удалось прочитать каталог документов: {exc}") from exc

    targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
    presets = payload.get("presets") if isinstance(payload.get("presets"), list) else []
    return {
        "targets": targets,
        "presets": presets,
    }


def list_generation_targets() -> dict[str, Any]:
    """
    Return serializable generation targets and presets for UI.
    """
    catalog = load_generation_catalog()
    target_ids = {str(item.get("id") or "") for item in catalog["targets"]}
    presets: list[dict[str, Any]] = []
    for preset in catalog["presets"]:
        targets = [target for target in preset.get("targets") or [] if target in target_ids]
        presets.append({**preset, "targets": targets})
    return {
        "targets": catalog["targets"],
        "presets": presets,
    }


def _targets_by_id() -> dict[str, dict[str, Any]]:
    catalog = load_generation_catalog()
    result: dict[str, dict[str, Any]] = {}
    for target in catalog["targets"]:
        target_id = str(target.get("id") or "").strip()
        if target_id:
            result[target_id] = dict(target)
    return result


def validate_generation_targets(targets: list[str] | None) -> list[dict[str, Any]]:
    """
    Validate selected generation target IDs against catalog.
    """
    by_id = _targets_by_id()
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_target in targets or []:
        target_id = str(raw_target).strip()
        if not target_id or target_id in seen:
            continue
        if target_id not in by_id:
            raise WorkflowError(f"Неизвестный тип документа для генерации: {target_id}")
        selected.append(by_id[target_id])
        seen.add(target_id)

    if not selected:
        raise WorkflowError("Выберите хотя бы один документ для генерации")

    return selected


def _target_template_text(target: dict[str, Any]) -> str:
    template_value = str(target.get("template") or "").strip()
    if not template_value:
        raise WorkflowError(f"Для документа {target.get('id')} не указан шаблон")

    template_path = DOCS_ROOT / template_value
    if not template_path.exists():
        raise WorkflowError(f"Шаблон документа не найден: {template_path}")
    return load_text_file(template_path)


def _target_context_pack(
    *,
    task_id: str,
    target: dict[str, Any],
    analysis: dict[str, Any],
) -> tuple[str, str]:
    target_id = str(target.get("id") or "")
    query_hint = str(target.get("query_hint") or target.get("title") or target_id)
    if target_id and target_id not in SECTION_ROUTING:
        SECTION_ROUTING[target_id] = RoutingRule(
            global_categories=GLOBAL_CONTEXT_CATEGORIES,
            query_hint=query_hint,
            path_keywords=tuple(tokenize(query_hint)[:12]),
        )
    context_pack = build_context_pack(
        task_id=task_id,
        section=target_id,
        analysis=analysis,
    )
    context_snippets = [
        ScoredSnippet(
            source_level=item["source_level"],
            source_path=item["source_path"],
            category=item["category"],
            score=float(item["score"]),
            text=item["text"],
        )
        for item in context_pack["sources"]
    ]
    return format_context_block(context_snippets), str(context_pack["context_pack_path"])


def render_document_prompt(
    *,
    target: dict[str, Any],
    document_template: str,
    task_text: str,
    context_block: str,
) -> str:
    """
    Render prompt for full-document generation target.
    """
    prompt_template = load_text_file(GENERATION_PROMPT_PATH)
    return render_template(
        prompt_template,
        {
            "document_id": str(target.get("id") or ""),
            "document_title": str(target.get("title") or target.get("id") or ""),
            "document_description": str(target.get("description") or ""),
            "document_template": document_template,
            "task_text": task_text,
            "context_block": context_block,
        },
    )


def generate_document_package(
    *,
    task_id: str,
    targets: list[str],
    model: str | None = None,
) -> dict[str, Any]:
    """
    Generate selected document targets as separate markdown artifacts.
    """
    safe_task_id = sanitize_task_id(task_id)
    selected_targets = validate_generation_targets(targets)
    analysis = analyze_task(safe_task_id)
    _, task_path, _ = resolve_task_paths(safe_task_id)
    task_text = task_path.read_text(encoding="utf-8", errors="ignore")

    profile_models = get_runtime_model_bundle()
    generation_model = model or profile_models["draft_model"] or PIPELINE_DRAFT_MODEL or DRAFT_MODEL
    drafts_dir = ensure_artifacts_dir("drafts", safe_task_id)
    timestamp = utc_timestamp()
    prompt_base = load_text_file(GENERATION_PROMPT_PATH)

    generated: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for target in selected_targets:
        target_id = str(target.get("id") or "")
        try:
            document_template = _target_template_text(target)
            context_block, context_pack_path = _target_context_pack(
                task_id=safe_task_id,
                target=target,
                analysis=analysis,
            )
            prompt = render_template(
                prompt_base,
                {
                    "document_id": target_id,
                    "document_title": str(target.get("title") or target_id),
                    "document_description": str(target.get("description") or ""),
                    "document_template": document_template,
                    "task_text": task_text,
                    "context_block": context_block,
                },
            )
            body = generate_text(
                model=generation_model,
                prompt=prompt,
                system_prompt=(
                    "Ты senior системный аналитик. Готовь документ на русском языке, "
                    "по шаблону и только на основе задачи и контекста."
                ),
                temperature=0.1,
            ).strip()
            output_path = drafts_dir / f"{timestamp}_{target_id}.md"
            output_path.write_text(body.rstrip() + "\n", encoding="utf-8")
            generated.append(
                {
                    "target_id": target_id,
                    "title": str(target.get("title") or target_id),
                    "path": str(output_path),
                    "file_name": output_path.name,
                    "template": str(target.get("template") or ""),
                    "context_pack_path": context_pack_path,
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"target_id": target_id, "error": str(exc)})

    index_lines = [
        "# Сгенерированный комплект документов",
        "",
        f"_task_id: {safe_task_id}_",
        f"_generated_at: {utc_iso()}_",
        f"_model: {generation_model}_",
        "",
    ]
    for item in generated:
        index_lines.append(f"- [{item['title']}]({item['file_name']})")
    if errors:
        index_lines.extend(["", "## Ошибки генерации", ""])
        for item in errors:
            index_lines.append(f"- `{item['target_id']}`: {item['error']}")

    index_path = drafts_dir / f"{timestamp}_documents_index.md"
    index_path.write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")

    manifest_path = drafts_dir / f"{timestamp}_documents_manifest.json"
    manifest = {
        "task_id": safe_task_id,
        "generated_at": utc_iso(),
        "model": generation_model,
        "targets": [str(target.get("id") or "") for target in selected_targets],
        "generated": generated,
        "errors": errors,
        "index_path": str(index_path),
    }
    write_json(manifest_path, manifest)

    return {
        "task_id": safe_task_id,
        "model": generation_model,
        "generated": generated,
        "errors": errors,
        "index_path": str(index_path),
        "manifest_path": str(manifest_path),
        "analysis": analysis,
    }


def load_section_template(document_type: str, section: str) -> str:
    """
    Load section template from docs/templates/sections.
    """
    path = DOCS_ROOT / "templates" / "sections" / document_type / f"{section}.md"
    if not path.exists():
        raise WorkflowError(f"Шаблон секции не найден: {path}")
    return load_text_file(path)


def render_draft_prompt(
    *,
    document_type: str,
    section: str,
    section_template: str,
    task_text: str,
    context_block: str,
) -> str:
    """
    Render draft prompt for FT or NFT section generation.
    """
    prompt_name = "draft_ft.md" if document_type == "ft" else "draft_nft.md"
    prompt_path = DOCS_ROOT / "templates" / "prompts" / prompt_name
    prompt_template = load_text_file(prompt_path)

    return render_template(
        prompt_template,
        {
            "section_name": section,
            "section_template": section_template,
            "task_text": task_text,
            "context_block": context_block,
        },
    )


def assemble_document(
    *,
    title: str,
    task_id: str,
    document_type: str,
    sections: list[str],
    bodies: dict[str, str],
) -> str:
    """
    Assemble final markdown document from generated sections.
    """
    lines: list[str] = [
        title,
        "",
        f"_task_id: {task_id}_",
        f"_document_type: {document_type}_",
        f"_generated_at: {utc_iso()}_",
        "",
    ]

    for section in sections:
        lines.append(f"## {section}")
        lines.append(bodies.get(section, ""))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def validate_sections(document_type: str, sections: list[str] | None) -> list[str]:
    """
    Validate requested sections against document type defaults.
    """
    allowed = FT_SECTIONS if document_type == "ft" else NFT_SECTIONS

    if not sections:
        return list(allowed)

    unsupported = [section for section in sections if section not in allowed]
    if unsupported:
        raise WorkflowError(f"Для типа {document_type} не поддерживаются секции: {', '.join(unsupported)}")

    return sections


def extract_draft_document_type(markdown: str) -> str | None:
    """
    Read document_type value from draft metadata block.
    """
    for line in markdown.splitlines():
        normalized = line.strip()
        if normalized.startswith("_document_type:") and normalized.endswith("_"):
            value = normalized[len("_document_type:") : -1].strip()
            candidate = value.strip("_").lower()
            if candidate in {"ft", "nft"}:
                return candidate
        if normalized.startswith("## "):
            continue
        if normalized.startswith("# "):
            continue
    return None


def generate_section_body(
    *,
    task_id: str,
    section: str,
    document_type: str,
    task_text: str,
    analysis: dict[str, Any],
    model: str,
    section_template: str,
) -> tuple[str, dict[str, str]]:
    """
    Generate one section text and persist it as intermediate artifact.
    """
    context_pack = build_context_pack(
        task_id=task_id,
        section=section,
        analysis=analysis,
    )
    context_pack_paths = {section: context_pack["context_pack_path"]}

    context_snippets = [
        ScoredSnippet(
            source_level=item["source_level"],
            source_path=item["source_path"],
            category=item["category"],
            score=float(item["score"]),
            text=item["text"],
        )
        for item in context_pack["sources"]
    ]

    prompt = render_draft_prompt(
        document_type=document_type,
        section=section,
        section_template=section_template,
        task_text=task_text,
        context_block=format_context_block(context_snippets),
    )

    generated = generate_text(
        model=model,
        prompt=prompt,
        system_prompt=(
            "Ты senior системный аналитик. Пиши на русском языке, "
            "строго по входному контексту, без вымышленных фактов."
        ),
        temperature=0.1,
    )
    return generated.strip(), context_pack_paths


def create_draft(
    *,
    task_id: str,
    force_document_type: str | None = None,
    sections: list[str] | None = None,
    model: str | None = None,
    analysis: dict[str, Any] | None = None,
    generate_handoff: bool = True,
) -> dict[str, Any]:
    """
    Generate a section-based draft document for the task.
    """
    safe_task_id = sanitize_task_id(task_id)
    resolved_analysis = analysis or analyze_task(safe_task_id)

    if force_document_type and force_document_type not in {"ft", "nft"}:
        raise WorkflowError("`force_document_type` должен быть `ft` или `nft`")

    document_type = force_document_type or resolved_analysis["document_type"]
    target_sections = validate_sections(document_type, sections)

    _, task_path, _ = resolve_task_paths(safe_task_id)
    task_text = task_path.read_text(encoding="utf-8", errors="ignore")

    profile_models = get_runtime_model_bundle()
    generation_model = model or profile_models["draft_model"] or PIPELINE_DRAFT_MODEL or DRAFT_MODEL
    section_bodies: dict[str, str] = {}
    context_pack_paths: dict[str, str] = {}
    section_timings: dict[str, float] = {}
    generation_errors: dict[str, str] = {}

    draft_tmp_dir = ensure_artifacts_dir("drafts", safe_task_id) / "tmp"
    draft_tmp_dir.mkdir(parents=True, exist_ok=True)

    def _section_worker(section: str) -> tuple[str, str, dict[str, str], float]:
        section_start = datetime.now(timezone.utc)
        section_template = load_section_template(document_type, section)
        body, pack_paths = generate_section_body(
            task_id=safe_task_id,
            section=section,
            document_type=document_type,
            task_text=task_text,
            analysis=resolved_analysis,
            model=generation_model,
            section_template=section_template,
        )
        section_file = draft_tmp_dir / f"{section}.md"
        section_file.write_text(body, encoding="utf-8")
        elapsed = (datetime.now(timezone.utc) - section_start).total_seconds()
        return section, body, pack_paths, round(elapsed, 3)

    with ThreadPoolExecutor(max_workers=max(1, PIPELINE_SECTION_WORKERS)) as executor:
        futures = {executor.submit(_section_worker, section): section for section in target_sections}
        for future in as_completed(futures):
            section = futures[future]
            try:
                section_name, generated, pack_paths, elapsed = future.result()
                section_bodies[section_name] = generated
                section_timings[section_name] = elapsed
                context_pack_paths.update(pack_paths)
            except Exception as exc:  # noqa: BLE001
                generation_errors[section] = str(exc)
                section_bodies[section] = (
                    f"_Не удалось сгенерировать секцию {section}: {exc}_"
                )

    title = "# Черновик аналитического документа"
    draft_markdown = assemble_document(
        title=title,
        task_id=safe_task_id,
        document_type=document_type,
        sections=target_sections,
        bodies=section_bodies,
    )

    drafts_dir = ensure_artifacts_dir("drafts", safe_task_id)
    draft_path = drafts_dir / f"{utc_timestamp()}_draft_{document_type}.md"
    draft_path.write_text(draft_markdown, encoding="utf-8")

    result = {
        "task_id": safe_task_id,
        "document_type": document_type,
        "model": generation_model,
        "sections": target_sections,
        "draft_path": str(draft_path),
        "context_pack_paths": context_pack_paths,
        "analysis": resolved_analysis,
        "section_timings": section_timings,
        "section_errors": generation_errors,
    }
    if generate_handoff:
        result["handoff"] = prepare_continue_handoff(
            task_id=safe_task_id,
            analysis=resolved_analysis,
            notes="Черновик подготовлен. Дальше можно переходить в VS Code + Continue.",
        )
    return result


def resolve_existing_draft(task_id: str, draft_path: str | None) -> Path:
    """
    Resolve draft path or discover latest draft for task.
    """
    safe_task_id = sanitize_task_id(task_id)

    if draft_path:
        candidate = Path(draft_path).expanduser()
        if not candidate.is_absolute():
            candidate = ARTIFACTS_ROOT / "drafts" / safe_task_id / candidate

        if not candidate.exists():
            raise WorkflowError(f"Черновик не найден: {candidate}")

        return candidate

    draft_dir = ARTIFACTS_ROOT / "drafts" / safe_task_id
    candidates = sorted(draft_dir.glob("*.md"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise WorkflowError(f"Для task_id='{safe_task_id}' не найдено черновиков")

    return candidates[-1]


def run_gap_analysis(
    *,
    task_id: str,
    draft_path: str | None = None,
    model: str | None = None,
    generate_handoff: bool = True,
) -> dict[str, Any]:
    """
    Run gap analysis for a draft and save result into reviews artifacts.
    """
    safe_task_id = sanitize_task_id(task_id)
    _, task_path, _ = resolve_task_paths(safe_task_id)
    resolved_draft_path = resolve_existing_draft(safe_task_id, draft_path)

    task_text = task_path.read_text(encoding="utf-8", errors="ignore")
    draft_text = resolved_draft_path.read_text(encoding="utf-8", errors="ignore")

    prompt_template = load_text_file(DOCS_ROOT / "templates" / "prompts" / "gap_finder.md")
    prompt = render_template(
        prompt_template,
        {
            "task_text": task_text,
            "draft_text": draft_text,
        },
    )

    profile_models = get_runtime_model_bundle()
    review_model = model or profile_models["review_model"] or PIPELINE_GAP_MODEL or REVIEW_MODEL
    gaps_markdown = generate_text(
        model=review_model,
        prompt=prompt,
        system_prompt=(
            "Ты senior системный аналитик. Проводи критичный gap-анализ "
            "и отвечай только на русском языке."
        ),
        temperature=0.0,
    )

    reviews_dir = ensure_artifacts_dir("reviews", safe_task_id)
    gaps_path = reviews_dir / f"{utc_timestamp()}_gaps.md"
    gaps_path.write_text(gaps_markdown.strip() + "\n", encoding="utf-8")

    result = {
        "task_id": safe_task_id,
        "draft_path": str(resolved_draft_path),
        "gaps_path": str(gaps_path),
        "model": review_model,
    }
    if generate_handoff:
        result["handoff"] = prepare_continue_handoff(
            task_id=safe_task_id,
            notes="Gap analysis подготовлен. Сверьте рабочую копию документа с найденными пробелами.",
        )
    return result


def split_markdown_sections(markdown: str) -> dict[str, str]:
    """
    Split markdown by second-level headings: ## section_name.
    """
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        match = re.match(r"^##\s+([a-z_]+)$", line)

        if match:
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = match.group(1)
            current_lines = []
            continue

        if current_key is not None:
            current_lines.append(raw_line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def refine_draft(
    *,
    task_id: str,
    draft_path: str | None = None,
    instructions: str | None = None,
    model: str | None = None,
    target_sections: list[str] | None = None,
    analysis: dict[str, Any] | None = None,
    generate_handoff: bool = True,
) -> dict[str, Any]:
    """
    Refine existing draft section-by-section using refine prompt.
    """
    safe_task_id = sanitize_task_id(task_id)
    resolved_analysis = analysis or analyze_task(safe_task_id)
    _, task_path, _ = resolve_task_paths(safe_task_id)

    resolved_draft_path = resolve_existing_draft(safe_task_id, draft_path)
    draft_text = resolved_draft_path.read_text(encoding="utf-8", errors="ignore")
    task_text = task_path.read_text(encoding="utf-8", errors="ignore")

    latest_doc_type = extract_draft_document_type(draft_text)
    document_type = latest_doc_type or resolved_analysis["document_type"]
    target_sections = validate_sections(document_type, target_sections or resolved_analysis.get("sections"))

    existing_sections = split_markdown_sections(draft_text)
    refine_prompt_template = load_text_file(DOCS_ROOT / "templates" / "prompts" / "refine.md")
    profile_models = get_runtime_model_bundle()
    refine_model = model or profile_models["refine_model"] or PIPELINE_REFINE_MODEL or REFINE_MODEL
    refine_notes = (instructions or "Уточни формулировки, добавь проверяемость и убери неоднозначности.").strip()

    refined_bodies: dict[str, str] = {}
    context_pack_paths: dict[str, str] = {}

    for section in target_sections:
        current_section = existing_sections.get(section, "")

        context_pack = build_context_pack(
            task_id=safe_task_id,
            section=section,
            analysis=analysis,
        )
        context_pack_paths[section] = context_pack["context_pack_path"]

        context_snippets = [
            ScoredSnippet(
                source_level=item["source_level"],
                source_path=item["source_path"],
                category=item["category"],
                score=float(item["score"]),
                text=item["text"],
            )
            for item in context_pack["sources"]
        ]

        prompt = render_template(
            refine_prompt_template,
            {
                "section_name": section,
                "current_section": current_section or "Раздел пока не заполнен.",
                "task_text": task_text,
                "context_block": format_context_block(context_snippets),
                "refine_instructions": refine_notes,
            },
        )

        refined = generate_text(
            model=refine_model,
            prompt=prompt,
            system_prompt=(
                "Ты senior системный аналитик. Улучшай текст раздела строго "
                "по контексту и отвечай только на русском языке."
            ),
            temperature=0.1,
        )
        refined_bodies[section] = refined.strip()

    refined_markdown = assemble_document(
        title="# Доработанный аналитический документ",
        task_id=safe_task_id,
        document_type=document_type,
        sections=target_sections,
        bodies=refined_bodies,
    )

    drafts_dir = ensure_artifacts_dir("drafts", safe_task_id)
    refined_path = drafts_dir / f"{utc_timestamp()}_refined_{document_type}.md"
    refined_path.write_text(refined_markdown, encoding="utf-8")

    result = {
        "task_id": safe_task_id,
        "document_type": document_type,
        "refined_path": str(refined_path),
        "source_draft_path": str(resolved_draft_path),
        "sections": target_sections,
        "model": refine_model,
        "context_pack_paths": context_pack_paths,
    }
    if generate_handoff:
        result["handoff"] = prepare_continue_handoff(
            task_id=safe_task_id,
            analysis=resolved_analysis,
            notes="Refine завершен. Продолжайте ручную доработку в рабочей копии через Continue.",
        )
    return result


def run_pipeline(
    *,
    task_id: str,
    run_gaps: bool = True,
    run_refine: bool = False,
    force_document_type: str | None = None,
    sections: list[str] | None = None,
    refine_instructions: str | None = None,
    run_target_sections: list[str] | None = None,
    draft_model: str | None = None,
    gap_model: str | None = None,
    refine_model: str | None = None,
    run_id_value: str | None = None,
) -> dict[str, Any]:
    """
    Execute end-to-end pipeline and return artifact paths.
    """
    safe_task_id = sanitize_task_id(task_id)
    run_identifier = run_id_value or run_id()

    analysis = analyze_task(safe_task_id)

    resolved_document_type = force_document_type or analysis["document_type"]
    if resolved_document_type not in {"ft", "nft"}:
        raise WorkflowError("`force_document_type` должен быть `ft` или `nft`")

    target_sections = validate_sections(resolved_document_type, sections)

    init_pipeline_status(
        safe_task_id,
        run_identifier,
        stage_names=PIPELINE_STAGE_NAMES,
    )

    timings: dict[str, float] = {}
    result: dict[str, Any] = {
        "run_id": run_identifier,
        "task_id": safe_task_id,
        "document_type": resolved_document_type,
        "sections": target_sections,
        "artifacts": {},
        "timings": timings,
    }

    try:
        update_pipeline_stage(safe_task_id, run_identifier, "analyze", state="running")
        update_pipeline_stage(
            safe_task_id,
            run_identifier,
            "analyze",
            state="done",
            details={"document_type": resolved_document_type},
        )

        stage_started = datetime.now(timezone.utc)
        update_pipeline_stage(safe_task_id, run_identifier, "draft", state="running")
        profile_models = get_runtime_model_bundle()
        draft_result = create_draft(
            task_id=safe_task_id,
            force_document_type=resolved_document_type,
            sections=target_sections,
            model=draft_model or profile_models["draft_model"] or PIPELINE_DRAFT_MODEL or DRAFT_MODEL,
            analysis=analysis,
            generate_handoff=False,
        )
        timings["draft_seconds"] = (datetime.now(timezone.utc) - stage_started).total_seconds()
        update_pipeline_stage(
            safe_task_id,
            run_identifier,
            "draft",
            state="done",
            details={"draft_path": draft_result["draft_path"]},
        )

        result["artifacts"]["draft"] = draft_result["draft_path"]
        result["artifact_sections"] = target_sections

        if run_gaps:
            gap_started = datetime.now(timezone.utc)
            update_pipeline_stage(safe_task_id, run_identifier, "gaps", state="running")
            gaps = run_gap_analysis(
                task_id=safe_task_id,
                model=gap_model or profile_models["review_model"] or PIPELINE_GAP_MODEL or REVIEW_MODEL,
                draft_path=draft_result["draft_path"],
                generate_handoff=False,
            )
            timings["gaps_seconds"] = (datetime.now(timezone.utc) - gap_started).total_seconds()
            update_pipeline_stage(
                safe_task_id,
                run_identifier,
                "gaps",
                state="done",
                details={"gaps_path": gaps["gaps_path"]},
            )
            result["artifacts"]["gaps"] = gaps["gaps_path"]
        else:
            update_pipeline_stage(
                safe_task_id,
                run_identifier,
                "gaps",
                state="skipped",
                details={"reason": "disabled"},
            )

        if run_refine:
            refine_started = datetime.now(timezone.utc)
            update_pipeline_stage(safe_task_id, run_identifier, "refine", state="running")
            refined = refine_draft(
                task_id=safe_task_id,
                draft_path=draft_result["draft_path"],
                instructions=refine_instructions,
                model=refine_model or profile_models["refine_model"] or PIPELINE_REFINE_MODEL or REFINE_MODEL,
                target_sections=run_target_sections or None,
                analysis=analysis,
                generate_handoff=False,
            )
            timings["refine_seconds"] = (datetime.now(timezone.utc) - refine_started).total_seconds()
            update_pipeline_stage(
                safe_task_id,
                run_identifier,
                "refine",
                state="done",
                details={"refined_path": refined["refined_path"]},
            )
            result["artifacts"]["refine"] = refined["refined_path"]
            result["document_type"] = refined["document_type"]
            result["sections"] = refined["sections"]
            result["latest_draft"] = refined["refined_path"]
            result["source_draft"] = refined["source_draft_path"]
        else:
            update_pipeline_stage(
                safe_task_id,
                run_identifier,
                "refine",
                state="skipped",
                details={"reason": "disabled"},
            )

        result["status"] = "ok"
        result["timings"] = timings
        result["handoff"] = prepare_continue_handoff(
            task_id=safe_task_id,
            analysis=analysis,
            notes="Pipeline завершен. Рабочая копия и handoff готовы для Power mode в VS Code + Continue.",
        )
        result["artifacts"]["handoff"] = result["handoff"]["handoff_path"]
        update_pipeline_stage(safe_task_id, run_identifier, "finalize", state="done", details={"final_status": "ok"})
        complete_pipeline_status(safe_task_id, run_identifier, state="completed", result=result)
        return result

    except Exception as exc:  # noqa: BLE001
        update_pipeline_stage(
            safe_task_id,
            run_identifier,
            "finalize",
            state="failed",
            error=str(exc),
        )
        result["status"] = "failed"
        result["error"] = str(exc)
        complete_pipeline_status(safe_task_id, run_identifier, state="failed", result=result)
        raise


def start_pipeline_run(
    *,
    task_id: str,
    run_gaps: bool = True,
    run_refine: bool = False,
    force_document_type: str | None = None,
    sections: list[str] | None = None,
    refine_instructions: str | None = None,
    run_target_sections: list[str] | None = None,
    draft_model: str | None = None,
    gap_model: str | None = None,
    refine_model: str | None = None,
) -> dict[str, Any]:
    """
    Start async pipeline and return run metadata.
    """
    run_identifier = run_id()
    safe_task_id = sanitize_task_id(task_id)
    init_pipeline_status(
        safe_task_id,
        run_identifier,
        stage_names=PIPELINE_STAGE_NAMES,
    )

    def worker() -> None:
        run_pipeline(
            task_id=safe_task_id,
            run_gaps=run_gaps,
            run_refine=run_refine,
            force_document_type=force_document_type,
            sections=sections,
            refine_instructions=refine_instructions,
            run_target_sections=run_target_sections,
            draft_model=draft_model,
            gap_model=gap_model,
            refine_model=refine_model,
            run_id_value=run_identifier,
        )

    thread = threading.Thread(target=worker, name=f"pipeline-{run_identifier}", daemon=True)
    thread.start()

    return {
        "task_id": safe_task_id,
        "run_id": run_identifier,
        "state": "running",
        "status_path": str(pipeline_status_path(safe_task_id, run_identifier)),
    }
