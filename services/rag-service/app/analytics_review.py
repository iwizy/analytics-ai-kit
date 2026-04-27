from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.confluence import ConfluenceImportError, import_confluence_urls
from app.documents import collect_supported_files, extract_text
from app.environment_state import DEFAULT_ANALYST_ID, get_runtime_model_bundle
from app.llm import generate_text, load_text_file, render_template
from app.settings import ARTIFACTS_ROOT, DOCS_ROOT, FT_SECTIONS, NFT_SECTIONS, REVIEW_MODEL, SECTION_DISPLAY_NAMES
from app.workflow import WorkflowError, detect_document_type, sanitize_task_id, utc_iso, utc_timestamp

REVIEW_SOURCES_KIND = "review_sources"
ANALYTICS_REVIEWS_KIND = "analytics_reviews"
MAX_ARTICLE_CHARS = 40000


def ensure_review_dir(kind: str, review_id: str) -> Path:
    path = ARTIFACTS_ROOT / kind / sanitize_task_id(review_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_review_paths(review_id: str) -> tuple[Path, Path]:
    safe_review_id = sanitize_task_id(review_id)
    return ensure_review_dir(REVIEW_SOURCES_KIND, safe_review_id), ensure_review_dir(ANALYTICS_REVIEWS_KIND, safe_review_id)


def import_review_confluence(*, review_id: str, urls: list[str]) -> dict[str, Any]:
    safe_review_id = sanitize_task_id(review_id)
    sources_dir, _ = resolve_review_paths(safe_review_id)
    try:
        result = import_confluence_urls(
            analyst_id=DEFAULT_ANALYST_ID,
            urls=urls,
            attachments_dir=sources_dir,
        )
    except ConfluenceImportError as exc:
        raise WorkflowError(str(exc)) from exc
    return {
        "review_id": safe_review_id,
        **result,
    }


def list_review_sources(review_id: str) -> list[Path]:
    safe_review_id = sanitize_task_id(review_id)
    sources_dir, _ = resolve_review_paths(safe_review_id)
    return collect_supported_files(sources_dir)


def read_review_article(review_id: str) -> tuple[str, list[str]]:
    safe_review_id = sanitize_task_id(review_id)
    source_files = list_review_sources(safe_review_id)
    if not source_files:
        raise WorkflowError("Сначала загрузи статью файлом или импортируй ссылку Confluence для ревью")

    text_blocks: list[str] = []
    labels: list[str] = []
    current_size = 0
    for path in source_files:
        extracted = extract_text(path).strip()
        if not extracted:
            continue
        labels.append(path.name)
        block = f"# Source: {path.name}\n\n{extracted}"
        remaining = MAX_ARTICLE_CHARS - current_size
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining]
        text_blocks.append(block)
        current_size += len(block)

    if not text_blocks:
        raise WorkflowError("Не удалось извлечь текст из источников ревью")

    return "\n\n---\n\n".join(text_blocks), labels


def build_template_outline(document_type: str) -> str:
    sections = FT_SECTIONS if document_type == "ft" else NFT_SECTIONS
    lines: list[str] = []
    for section in sections:
        title = SECTION_DISPLAY_NAMES.get(section, section)
        template_path = DOCS_ROOT / "templates" / "sections" / document_type / f"{section}.md"
        template_text = load_text_file(template_path).strip()
        if len(template_text) > 1600:
            template_text = f"{template_text[:1600]}..."
        lines.append(f"## {title} ({section})\n{template_text}")
    return "\n\n".join(lines)


def render_analytics_review_prompt(
    *,
    article_text: str,
    source_labels: list[str],
    document_type: str,
    forced_type: bool,
) -> str:
    prompt_template = load_text_file(DOCS_ROOT / "templates" / "prompts" / "analytics_review.md")
    template_outline = build_template_outline(document_type)
    return render_template(
        prompt_template,
        {
            "source_labels": ", ".join(source_labels) if source_labels else "-",
            "document_type": document_type,
            "document_type_note": "тип документа был выбран аналитиком вручную" if forced_type else "тип документа был определён автоматически по содержимому статьи",
            "template_outline": template_outline,
            "article_text": article_text,
        },
    )


def run_analytics_review(
    *,
    review_id: str,
    document_type: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    safe_review_id = sanitize_task_id(review_id)
    _, reviews_dir = resolve_review_paths(safe_review_id)
    article_text, source_labels = read_review_article(safe_review_id)

    normalized_type = (document_type or "auto").strip().lower()
    if normalized_type not in {"auto", "ft", "nft"}:
        raise WorkflowError("`document_type` должен быть `auto`, `ft` или `nft`")

    detected_type = normalized_type
    detection_meta: dict[str, Any] = {}
    forced_type = normalized_type in {"ft", "nft"}
    if normalized_type == "auto":
        detected_type, detection_meta = detect_document_type(article_text)

    prompt = render_analytics_review_prompt(
        article_text=article_text,
        source_labels=source_labels,
        document_type=detected_type,
        forced_type=forced_type,
    )

    profile_models = get_runtime_model_bundle()
    review_model = model or profile_models["review_model"] or REVIEW_MODEL
    review_markdown = generate_text(
        model=review_model,
        prompt=prompt,
        system_prompt=(
            "Ты lead системный аналитик и reviewer аналитической документации. "
            "Проверяй материал строго по входному тексту и шаблону, не выдумывай отсутствующие факты, "
            "отвечай только на русском языке и давай конкретные рекомендации."
        ),
        temperature=0.0,
    ).strip()

    review_path = reviews_dir / f"{utc_timestamp()}_analytics_review.md"
    review_path.write_text(review_markdown + "\n", encoding="utf-8")

    meta_path = reviews_dir / f"{review_path.stem}.json"
    meta_payload = {
        "review_id": safe_review_id,
        "created_at": utc_iso(),
        "document_type": detected_type,
        "document_type_forced": forced_type,
        "detection_meta": detection_meta,
        "model": review_model,
        "sources": source_labels,
        "review_path": str(review_path),
    }
    meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "review_id": safe_review_id,
        "document_type": detected_type,
        "document_type_forced": forced_type,
        "detection_meta": detection_meta,
        "model": review_model,
        "sources": source_labels,
        "review_path": str(review_path),
        "metadata_path": str(meta_path),
    }
