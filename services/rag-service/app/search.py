"""
Semantic search logic for indexed project documentation.
"""

import os

import httpx
from qdrant_client import QdrantClient

QDRANT_URL = os.getenv("QDRANT_URL") or "http://localhost:6333"
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION") or "analytics_context"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or "nomic-embed-text"
SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT") or "8")


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