"""
Document ingestion logic.

Reads global docs from the mounted folders, extracts text,
splits it into chunks, gets embeddings from Ollama,
and uploads everything into Qdrant.
"""

import uuid
from pathlib import Path
from typing import Iterable

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.chunking import chunk_text
from app.documents import collect_supported_files, extract_text
from app.search import get_embedding
from app.settings import DOCS_ROOT, GLOBAL_CONTEXT_CATEGORIES, QDRANT_COLLECTION, QDRANT_URL


def get_qdrant_client() -> QdrantClient:
    """
    Create Qdrant client.
    """
    return QdrantClient(url=QDRANT_URL)


def collect_files() -> list[tuple[str, Path]]:
    """
    Collect files from global context folders.
    """
    collected: list[tuple[str, Path]] = []

    for category in GLOBAL_CONTEXT_CATEGORIES:
        directory = DOCS_ROOT / category
        for path in collect_supported_files(directory):
            collected.append((category, path))

    return collected


def iter_points() -> Iterable[PointStruct]:
    """
    Generate Qdrant points from all source documents.
    """
    for category, path in collect_files():
        text = extract_text(path)
        if not text.strip():
            continue

        chunks = chunk_text(text)
        title = path.stem
        relative_path = str(path.relative_to(DOCS_ROOT))

        for index, chunk in enumerate(chunks):
            point_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{relative_path}:{index}:{chunk}",
                )
            )

            embedding = get_embedding(chunk)

            payload = {
                "doc_id": relative_path,
                "chunk_id": f"{relative_path}:{index}",
                "source_path": relative_path,
                "category": category,
                "title": title,
                "text": chunk,
            }

            yield PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            )


def reindex_all_documents() -> dict:
    """
    Full destructive reindex of all global docs.
    """
    files = collect_files()
    if not files:
        return {
            "indexed_files": 0,
            "indexed_chunks": 0,
            "message": "Документы для индексации не найдены",
        }

    first_file_text = extract_text(files[0][1])
    first_chunks = chunk_text(first_file_text)

    if not first_chunks:
        return {
            "indexed_files": 0,
            "indexed_chunks": 0,
            "message": "Не удалось выделить текстовые чанки",
        }

    first_embedding = get_embedding(first_chunks[0])
    client = get_qdrant_client()

    existing = [collection.name for collection in client.get_collections().collections]
    if QDRANT_COLLECTION in existing:
        client.delete_collection(collection_name=QDRANT_COLLECTION)

    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(
            size=len(first_embedding),
            distance=Distance.COSINE,
        ),
    )

    points = list(iter_points())
    if points:
        client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points,
        )

    return {
        "indexed_files": len(files),
        "indexed_chunks": len(points),
        "collection": QDRANT_COLLECTION,
        "categories": list(GLOBAL_CONTEXT_CATEGORIES),
    }
