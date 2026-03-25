"""
Main application entrypoint for the local RAG service.

This service:
- reads project documentation from mounted folders
- chunks and embeds documents
- stores vectors in Qdrant
- performs semantic search for agent context retrieval
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.ingest import reindex_all_documents
from app.search import search_documents

app = FastAPI(
    title="Analytics RAG Service",
    version="0.1.0"
)


class SearchRequest(BaseModel):
    query: str
    limit: int | None = None


@app.get("/health")
def health() -> dict:
    """
    Health check endpoint.
    """
    return {"status": "ok"}


@app.post("/reindex")
def reindex() -> dict:
    """
    Full reindex of all project documents.
    """
    result = reindex_all_documents()
    return {
        "status": "ok",
        "details": result
    }


@app.post("/search")
def search(request: SearchRequest) -> dict:
    """
    Semantic search across indexed documents.
    """
    if not request.query.strip():
        raise HTTPException(
            status_code=400,
            detail="Query must not be empty"
        )

    results = search_documents(
        query=request.query,
        limit=request.limit
    )

    return {
        "status": "ok",
        "results": results
    }