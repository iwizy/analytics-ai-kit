from __future__ import annotations

import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urldefrag, urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from app.confluence import (
    CONTENT_SELECTORS,
    ConfluenceImportError,
    fetch_page_content,
    load_analyst_profile,
    protect_file,
    slugify,
    utc_iso,
)
from app.settings import DOCS_ROOT

DEFAULT_ANALYST_ID = "default"
COLLECTIONS_ROOT = DOCS_ROOT / "shared-context" / "confluence_collections"
MAX_CONTEXT_PAGES = 50
MAX_CONTEXT_DEPTH = 3
SKIP_PATH_MARKERS = (
    "/download/",
    "/attachments/",
    "/login",
    "/logout",
    "/pages/editpage.action",
    "/pages/createpage.action",
    "/pages/viewinfo.action",
    "/plugins/servlet",
    "/rest/",
)


class ContextCollectionError(RuntimeError):
    pass


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _canonical_url(url: str) -> str:
    stripped, _fragment = urldefrag(url.strip())
    return stripped


def _collection_id(raw_value: str, root_url: str) -> str:
    explicit = slugify(raw_value) if raw_value.strip() else ""
    if explicit:
        return explicit
    parsed = urlparse(root_url)
    query_page_id = parse_qs(parsed.query).get("pageId", [""])[0]
    path_name = Path(parsed.path or "/").name
    return f"{_now_id()}_{slugify(query_page_id or path_name or parsed.netloc or 'context')}"


def _same_confluence_area(root_url: str, candidate_url: str) -> bool:
    root = urlparse(root_url)
    candidate = urlparse(candidate_url)
    if candidate.scheme not in {"http", "https"}:
        return False
    if candidate.netloc != root.netloc:
        return False

    path = candidate.path.lower()
    if any(marker in path for marker in SKIP_PATH_MARKERS):
        return False
    if not re.search(r"(confluence|/display/|/pages/|/spaces/|/wiki/)", path):
        return False

    return True


def _extract_links(page, root_url: str) -> list[str]:
    try:
        links = page.evaluate(
            """
            ({ contentSelectors }) => {
              const roots = [];
              for (const selector of contentSelectors) {
                const node = document.querySelector(selector);
                if (node) {
                  roots.push(node);
                }
              }
              if (document.body) {
                roots.push(document.body);
              }
              const seen = new Set();
              const links = [];
              for (const root of roots) {
                for (const link of Array.from(root.querySelectorAll('a[href]'))) {
                  if (link.href && !seen.has(link.href)) {
                    seen.add(link.href);
                    links.push(link.href);
                  }
                }
              }
              return links;
            }
            """,
            {"contentSelectors": list(CONTENT_SELECTORS)},
        )
    except Exception:
        return []

    clean: list[str] = []
    for href in links if isinstance(links, list) else []:
        absolute = _canonical_url(urljoin(page.url, str(href)))
        if absolute and absolute not in clean and _same_confluence_area(root_url, absolute):
            clean.append(absolute)
    return clean


def _render_page_markdown(*, title: str, text: str, source_url: str, depth: int) -> str:
    return (
        f"# {title}\n\n"
        f"Source URL: {source_url}\n\n"
        f"Collected at: {utc_iso()}\n\n"
        f"Collection depth: {depth}\n\n"
        f"---\n\n"
        f"{text}\n"
    )


def _write_index(collection_dir: Path, manifest: dict[str, Any]) -> None:
    lines = [
        f"# {manifest['title']}",
        "",
        f"Root URL: {manifest['root_url']}",
        "",
        f"Collected at: {manifest['created_at']}",
        "",
        f"Pages collected: {manifest['imported_count']}",
        "",
        "## Страницы",
        "",
    ]
    for item in manifest["pages"]:
        lines.append(f"- [{item['title']}](pages/{item['file_name']})")
        lines.append(f"  Source: {item['resolved_url']}")
        lines.append("")
    if manifest["failed"]:
        lines.extend(["## Не удалось собрать", ""])
        for item in manifest["failed"]:
            lines.append(f"- {item['url']}: {item['error']}")
    (collection_dir / "context_index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def list_context_collections() -> list[dict[str, Any]]:
    COLLECTIONS_ROOT.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for collection_dir in sorted([path for path in COLLECTIONS_ROOT.iterdir() if path.is_dir()], key=lambda path: path.name, reverse=True):
        manifest = _read_json(collection_dir / "manifest.json")
        if not manifest:
            continue
        items.append(
            {
                "collection_id": collection_dir.name,
                "title": str(manifest.get("title") or collection_dir.name),
                "root_url": str(manifest.get("root_url") or ""),
                "created_at": str(manifest.get("created_at") or ""),
                "imported_count": int(manifest.get("imported_count") or 0),
                "failed_count": len(manifest.get("failed") or []),
                "path": str(collection_dir),
            }
        )
    return items


def collect_confluence_context(
    *,
    root_url: str,
    collection_id: str = "",
    max_depth: int = 1,
    max_pages: int = 20,
    analyst_id: str = DEFAULT_ANALYST_ID,
) -> dict[str, Any]:
    clean_root_url = _canonical_url(root_url)
    if not clean_root_url:
        raise ContextCollectionError("Передайте ссылку на корневую страницу Confluence")

    depth_limit = min(max(int(max_depth or 1), 0), MAX_CONTEXT_DEPTH)
    pages_limit = min(max(int(max_pages or 20), 1), MAX_CONTEXT_PAGES)

    try:
        profile = load_analyst_profile(analyst_id)
    except ConfluenceImportError as exc:
        raise ContextCollectionError(str(exc)) from exc

    safe_collection_id = _collection_id(collection_id, clean_root_url)
    collection_dir = COLLECTIONS_ROOT / safe_collection_id
    pages_dir = collection_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(clean_root_url, 0)])
    imported: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        context_kwargs: dict[str, object] = {"ignore_https_errors": True}
        if profile.storage_state_path.exists() and profile.storage_state_path.stat().st_size > 0:
            context_kwargs["storage_state"] = str(profile.storage_state_path)

        context = browser.new_context(**context_kwargs)
        try:
            page = context.new_page()
            while queue and len(imported) < pages_limit:
                url, depth = queue.popleft()
                canonical = _canonical_url(url)
                if canonical in visited:
                    continue
                visited.add(canonical)

                try:
                    payload = fetch_page_content(page, canonical, profile)
                    file_name = f"{len(imported) + 1:03d}_{slugify(payload['title'])}.md"
                    page_path = pages_dir / file_name
                    page_path.write_text(
                        _render_page_markdown(
                            title=payload["title"],
                            text=payload["text"],
                            source_url=payload["resolved_url"],
                            depth=depth,
                        ),
                        encoding="utf-8",
                    )
                    links = _extract_links(page, clean_root_url)
                    imported.append(
                        {
                            "title": payload["title"],
                            "source_url": canonical,
                            "resolved_url": payload["resolved_url"],
                            "file_name": file_name,
                            "depth": depth,
                            "links_found": len(links),
                        }
                    )
                    if depth < depth_limit:
                        for link in links:
                            if link not in visited and len(queue) + len(imported) < pages_limit:
                                queue.append((link, depth + 1))
                except PlaywrightTimeoutError as exc:
                    failed.append({"url": canonical, "error": f"Timeout при загрузке страницы: {exc}"})
                except Exception as exc:
                    failed.append({"url": canonical, "error": str(exc)})

            context.storage_state(path=str(profile.storage_state_path))
            protect_file(profile.storage_state_path)
        finally:
            context.close()
            browser.close()

    title = imported[0]["title"] if imported else safe_collection_id
    manifest = {
        "collection_id": safe_collection_id,
        "title": title,
        "root_url": clean_root_url,
        "created_at": utc_iso(),
        "analyst_id": analyst_id,
        "max_depth": depth_limit,
        "max_pages": pages_limit,
        "imported_count": len(imported),
        "failed": failed,
        "pages": imported,
    }
    (collection_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_index(collection_dir, manifest)

    return {
        "collection_id": safe_collection_id,
        "collection_path": str(collection_dir),
        "index_path": str(collection_dir / "context_index.md"),
        "manifest": manifest,
        "collections": list_context_collections(),
    }
