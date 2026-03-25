"""
Helpers for prompt rendering and Ollama text generation.
"""

from pathlib import Path

import httpx

from app.settings import OLLAMA_BASE_URL


def load_text_file(path: Path) -> str:
    """
    Load UTF-8 text content from disk.
    """
    return path.read_text(encoding="utf-8")


def render_template(template: str, values: dict[str, str]) -> str:
    """
    Render a string template using {{placeholder}} substitutions.
    """
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def generate_text(
    *,
    model: str,
    prompt: str,
    system_prompt: str,
    temperature: float = 0.2,
) -> str:
    """
    Generate text from Ollama chat endpoint.
    """
    with httpx.Client(timeout=300.0) as client:
        response = client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "options": {
                    "temperature": temperature,
                },
            },
        )
        response.raise_for_status()
        payload = response.json()

    content = payload.get("message", {}).get("content", "").strip()
    if not content:
        raise RuntimeError("Empty response from Ollama")

    return content
