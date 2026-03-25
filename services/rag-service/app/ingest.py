"""
Document ingestion logic.

Reads files from the mounted docs folders, extracts text,
splits it into chunks, gets embeddings from Ollama,
and uploads everything into Qdrant.
"""

import os
import uuid
from pathlib import Path
from typing import Iterable

import fitz
import httpx
from docx import Document
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.chunking import chunk_text

DOCS_ROOT = Path(os.getenv("DOCS_ROOT") or "/data/docs")
QDRANT_URL = os.getenv("QDRANT_URL") or "http://localhost:6333"
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION") or "analytics_context"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or "nomic-embed-text"


def get_qdrant_client() -> QdrantClient:
    """
    Create Qdrant client.
    """
    return QdrantClient(url=QDRANT_URL)


def collect_files() -> list[tuple[str, Path]]:
    """
    Collect files from standard documentation folders.
    """
    categories = ["input", "templates", "glossary", "examples"]
    collected: list[tuple[str, Path]] = []

    for category in categories:
        directory = DOCS_ROOT / category
        if not directory.exists():
            continue

        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".md", ".txt", ".docx", ".pdf"}:
                collected.append((category, path))

    return collected


def extract_text(path: Path) -> str:
    """
    Extract text depending on file extension.
    """
    suffix = path.suffix.lower()

    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".docx":
        doc = Document(str(path))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)

    if suffix == ".pdf":
        text_parts: list[str] = []
        with fitz.open(path) as pdf:
            for page in pdf:
                text_parts.append(page.get_text())
        return "\n".join(text_parts)

    return ""


def get_embedding(text: str) -> list[float]:
    """
    Get embedding vector from Ollama.
    """
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={
                "model": EMBEDDING_MODEL,
                "prompt": text,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]


def ensure_collection(vector_size: int) -> None:
    """
    Create Qdrant collection if it does not exist.
    """
    client = get_qdrant_client()
    existing = [collection.name for collection in client.get_collections().collections]

    if QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )


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
                    f"{relative_path}:{index}:{chunk}"
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
    Full destructive reindex of all documents.
    """
    files = collect_files()
    if not files:
        return {
            "indexed_files": 0,
            "indexed_chunks": 0,
            "message": "No documents found",
        }

    first_file_text = extract_text(files[0][1])
    first_chunks = chunk_text(first_file_text)

    if not first_chunks:
        return {
            "indexed_files": 0,
            "indexed_chunks": 0,
            "message": "No text chunks found",
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
    }