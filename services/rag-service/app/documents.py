"""
Document loading and text extraction helpers.
"""

from pathlib import Path

import fitz
from docx import Document

from app.settings import SUPPORTED_EXTENSIONS


def is_supported_file(path: Path) -> bool:
    """
    Return True when file extension is supported for ingestion.
    """
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def collect_supported_files(directory: Path) -> list[Path]:
    """
    Recursively collect supported files from a directory.
    """
    if not directory.exists():
        return []

    files: list[Path] = []
    for path in directory.rglob("*"):
        if is_supported_file(path):
            files.append(path)

    return sorted(files)


def extract_text(path: Path) -> str:
    """
    Extract plain text from markdown/text/docx/pdf files.
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
