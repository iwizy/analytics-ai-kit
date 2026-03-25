"""
Utilities for splitting long text into overlapping chunks.
"""

import os


def chunk_text(text: str) -> list[str]:
    """
    Split text into chunks with overlap using environment configuration.
    """
    chunk_size = int(os.getenv("CHUNK_SIZE") or "1200")
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP") or "200")

    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0

    while start < len(cleaned):
        end = start + chunk_size
        chunk = cleaned[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(cleaned):
            break

        start = max(end - chunk_overlap, start + 1)

    return chunks