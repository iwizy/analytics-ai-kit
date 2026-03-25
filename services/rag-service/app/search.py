"""
Semantic search logic for indexed project documentation.
"""

import httpx
from qdrant_client import QdrantClient

from app.settings import (
    EMBEDDING_MODEL,
    OLLAMA_BASE_URL,
    QDRANT_COLLECTION,
    QDRANT_URL,
    SEARCH_LIMIT,
)


def get_qdrant_client() -> QdrantClient:
    """
    Create Qdrant client instance.
    """
    return QdrantClient(url=QDRANT_URL)


def get_embedding(text: str) -> list[float]:
    """
    Retrieve embedding vector from Ollama.
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
        return response.json()["embedding"]


def search_documents(query: str, limit: int | None = None) -> list[dict]:
    """
    Search indexed chunks by semantic similarity.
    """
    effective_limit = limit or SEARCH_LIMIT
    embedding = get_embedding(query)
    client = get_qdrant_client()

    hits = client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=embedding,
        limit=effective_limit,
    )

    return [
        {
            "score": hit.score,
            "doc_id": hit.payload.get("doc_id"),
            "chunk_id": hit.payload.get("chunk_id"),
            "source_path": hit.payload.get("source_path"),
            "category": hit.payload.get("category"),
            "title": hit.payload.get("title"),
            "text": hit.payload.get("text"),
        }
        for hit in hits
    ]
