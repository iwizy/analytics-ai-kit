"""
Confluence import helpers backed by per-analyst Playwright profiles.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from app.settings import ANALYST_PROFILES_ROOT, PLAYWRIGHT_STATE_ROOT

PROFILE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")
SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9]+")
MULTISPACE_PATTERN = re.compile(r"[ \t]+")
BLANK_BLOCK_PATTERN = re.compile(r"\n{3,}")

LOGIN_FIELD_SELECTORS = (
    "input[name='username']",
    "input[type='email']",
    "#username",
    "#os_username",
)

PASSWORD_FIELD_SELECTORS = (
    "input[name='password']",
    "input[type='password']",
    "#password",
    "#os_password",
)

SUBMIT_SELECTORS = (
    "#login-submit",
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Continue')",
    "button:has-text('Log in')",
    "button:has-text('Login')",
    "button:has-text('Войти')",
)

TITLE_SELECTORS = (
    "[data-testid='page-title']",
    "#title-text",
    "h1",
)

CONTENT_SELECTORS = (
    "[data-testid='page-content']",
    "#main-content",
    ".wiki-content",
    "main",
    "article",
    "body",
)

NAVIGATION_TIMEOUT_MS = 60000
POST_LOGIN_WAIT_MS = 1500
MIN_CONTENT_LENGTH = 120


class ConfluenceImportError(RuntimeError):
    """
    Raised when analyst profile or Confluence page import fails.
    """


@dataclass(frozen=True)
class AnalystProfile:
    """
    Stored credentials and browser state for one analyst.
    """

    analyst_id: str
    login: str
    password: str
    profile_path: Path
    storage_state_path: Path


def utc_iso() -> str:
    """
    Build ISO UTC timestamp for metadata.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_storage_dirs() -> None:
    """
    Ensure storage folders for analyst credentials and sessions exist.
    """
    ANALYST_PROFILES_ROOT.mkdir(parents=True, exist_ok=True)
    PLAYWRIGHT_STATE_ROOT.mkdir(parents=True, exist_ok=True)


def sanitize_analyst_id(analyst_id: str) -> str:
    """
    Validate analyst profile id.
    """
    normalized = analyst_id.strip()
    if not normalized:
        raise ConfluenceImportError("`analyst_id` не должен быть пустым")

    if not PROFILE_ID_PATTERN.match(normalized):
        raise ConfluenceImportError(
            "`analyst_id` содержит недопустимые символы; используйте буквы, цифры, точку, underscore и дефис"
        )

    return normalized


def analyst_profile_path(analyst_id: str) -> Path:
    """
    Build file path for analyst credentials.
    """
    return ANALYST_PROFILES_ROOT / f"{sanitize_analyst_id(analyst_id)}.json"


def analyst_storage_state_path(analyst_id: str) -> Path:
    """
    Build file path for persisted Playwright session.
    """
    return PLAYWRIGHT_STATE_ROOT / f"{sanitize_analyst_id(analyst_id)}.json"


def protect_file(path: Path) -> None:
    """
    Restrict file permissions when platform supports chmod.
    """
    try:
        path.chmod(0o600)
    except OSError:
        return


def save_analyst_profile(*, analyst_id: str, login: str, password: str) -> dict[str, str]:
    """
    Persist analyst credentials to a dedicated local file.
    """
    safe_analyst_id = sanitize_analyst_id(analyst_id)
    login_value = login.strip()
    password_value = password.strip()

    if not login_value:
        raise ConfluenceImportError("`login` не должен быть пустым")
    if not password_value:
        raise ConfluenceImportError("`password` не должен быть пустым")

    ensure_storage_dirs()

    profile_path = analyst_profile_path(safe_analyst_id)
    payload = {
        "analyst_id": safe_analyst_id,
        "login": login_value,
        "password": password_value,
        "updated_at": utc_iso(),
    }
    profile_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    protect_file(profile_path)

    return {
        "analyst_id": safe_analyst_id,
        "profile_path": str(profile_path),
        "storage_state_path": str(analyst_storage_state_path(safe_analyst_id)),
    }


def load_analyst_profile(analyst_id: str) -> AnalystProfile:
    """
    Load analyst credentials from local storage.
    """
    safe_analyst_id = sanitize_analyst_id(analyst_id)
    ensure_storage_dirs()

    profile_path = analyst_profile_path(safe_analyst_id)
    if not profile_path.exists():
        raise ConfluenceImportError(
            f"Профиль аналитика '{safe_analyst_id}' не найден. Сначала сохраните логин и пароль."
        )

    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfluenceImportError(
            f"Файл профиля аналитика '{safe_analyst_id}' поврежден"
        ) from exc

    login = str(payload.get("login") or "").strip()
    password = str(payload.get("password") or "").strip()
    if not login or not password:
        raise ConfluenceImportError(
            f"Профиль аналитика '{safe_analyst_id}' не содержит логин и пароль"
        )

    return AnalystProfile(
        analyst_id=safe_analyst_id,
        login=login,
        password=password,
        profile_path=profile_path,
        storage_state_path=analyst_storage_state_path(safe_analyst_id),
    )


def normalize_text(text: str) -> str:
    """
    Compact whitespace while keeping readable paragraph breaks.
    """
    normalized_lines = [MULTISPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    compacted = "\n".join(line for line in normalized_lines)
    compacted = BLANK_BLOCK_PATTERN.sub("\n\n", compacted)
    return compacted.strip()


def slugify(value: str) -> str:
    """
    Convert a title or path fragment to safe ASCII slug.
    """
    slug = SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug[:80] or "page"


def pick_first_visible_selector(page: Page, selectors: tuple[str, ...]) -> str | None:
    """
    Return first selector that is currently visible on page.
    """
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=1000):
                return selector
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return None


def click_submit(page: Page) -> None:
    """
    Click first available submit control for login flow.
    """
    for selector in SUBMIT_SELECTORS:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=1000):
                locator.click()
                return
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue

    page.keyboard.press("Enter")


def login_required(page: Page) -> bool:
    """
    Detect whether current page still asks for credentials.
    """
    current_url = page.url.lower()
    if any(marker in current_url for marker in ("login", "signin", "auth")):
        return True

    return bool(
        pick_first_visible_selector(page, LOGIN_FIELD_SELECTORS)
        or pick_first_visible_selector(page, PASSWORD_FIELD_SELECTORS)
    )


def perform_login(page: Page, profile: AnalystProfile) -> None:
    """
    Execute best-effort login flow for Atlassian Cloud or Server/Data Center.
    """
    username_selector = pick_first_visible_selector(page, LOGIN_FIELD_SELECTORS)
    if username_selector:
        page.locator(username_selector).first.fill(profile.login)

    password_selector = pick_first_visible_selector(page, PASSWORD_FIELD_SELECTORS)
    if password_selector is None:
        click_submit(page)
        page.wait_for_timeout(800)
        password_selector = pick_first_visible_selector(page, PASSWORD_FIELD_SELECTORS)

    if password_selector is None:
        raise ConfluenceImportError("Не удалось найти поле пароля на странице авторизации Confluence")

    page.locator(password_selector).first.fill(profile.password)
    click_submit(page)
    page.wait_for_load_state("domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
    page.wait_for_timeout(POST_LOGIN_WAIT_MS)


def ensure_authenticated(page: Page, profile: AnalystProfile) -> None:
    """
    Log in when target page redirects to authentication.
    """
    if not login_required(page):
        return

    perform_login(page, profile)
    if login_required(page):
        raise ConfluenceImportError(
            f"Не удалось авторизоваться в Confluence для профиля '{profile.analyst_id}'"
        )


def extract_page_payload(page: Page) -> dict[str, str]:
    """
    Extract visible title and content from current Confluence page.
    """
    for selector in CONTENT_SELECTORS:
        try:
            page.locator(selector).first.wait_for(state="visible", timeout=5000)
            break
        except PlaywrightTimeoutError:
            continue

    payload = page.evaluate(
        """
        ({ titleSelectors, contentSelectors }) => {
          const findText = (selectors) => {
            for (const selector of selectors) {
              const node = document.querySelector(selector);
              if (node && node.innerText && node.innerText.trim()) {
                return node.innerText.trim();
              }
            }
            return "";
          };

          const title = findText(titleSelectors) || document.title || "Confluence Page";
          let content = "";

          for (const selector of contentSelectors) {
            const node = document.querySelector(selector);
            if (node && node.innerText && node.innerText.trim().length > 40) {
              content = node.innerText;
              break;
            }
          }

          if (!content) {
            content = document.body ? document.body.innerText : "";
          }

          return {
            title,
            text: content || "",
            resolved_url: window.location.href,
          };
        }
        """,
        {
            "titleSelectors": list(TITLE_SELECTORS),
            "contentSelectors": list(CONTENT_SELECTORS),
        },
    )

    title = normalize_text(str(payload.get("title") or "Confluence Page"))
    text = normalize_text(str(payload.get("text") or ""))
    resolved_url = str(payload.get("resolved_url") or page.url)

    if len(text) < MIN_CONTENT_LENGTH:
        raise ConfluenceImportError(f"Страница {resolved_url} не содержит достаточно текста для импорта")

    return {
        "title": title,
        "text": text,
        "resolved_url": resolved_url,
    }


def fetch_page_content(page: Page, url: str, profile: AnalystProfile) -> dict[str, str]:
    """
    Open Confluence page, authenticate if needed and extract readable text.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
    ensure_authenticated(page, profile)
    page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
    page.wait_for_timeout(800)
    ensure_authenticated(page, profile)
    return extract_page_payload(page)


def build_attachment_path(attachments_dir: Path, title: str, source_url: str) -> Path:
    """
    Build unique attachment filename for imported Confluence page.
    """
    parsed = urlparse(source_url)
    page_id = parse_qs(parsed.query).get("pageId", [""])[0]
    path_token = Path(parsed.path or "/").name
    base_name = slugify(page_id or path_token or title or parsed.netloc)
    candidate = attachments_dir / f"confluence_{base_name}.md"

    if not candidate.exists():
        return candidate

    title_slug = slugify(title)
    suffix = 2
    while True:
        candidate = attachments_dir / f"confluence_{title_slug}_{suffix}.md"
        if not candidate.exists():
            return candidate
        suffix += 1


def render_attachment_content(*, title: str, text: str, source_url: str, analyst_id: str) -> str:
    """
    Render imported page as markdown attachment consumable by the existing pipeline.
    """
    return (
        f"# {title}\n\n"
        f"Source URL: {source_url}\n\n"
        f"Imported by analyst profile: {analyst_id}\n\n"
        f"Imported at: {utc_iso()}\n\n"
        f"---\n\n"
        f"{text}\n"
    )


def import_confluence_urls(
    *,
    analyst_id: str,
    urls: list[str],
    attachments_dir: Path,
) -> dict[str, object]:
    """
    Import one or more Confluence pages into task attachments.
    """
    clean_urls = []
    for raw_url in urls:
        url = raw_url.strip()
        if url and url not in clean_urls:
            clean_urls.append(url)

    if not clean_urls:
        raise ConfluenceImportError("Передайте хотя бы одну ссылку Confluence")

    profile = load_analyst_profile(analyst_id)
    attachments_dir.mkdir(parents=True, exist_ok=True)

    imported: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )

        context_kwargs: dict[str, object] = {
            "ignore_https_errors": True,
        }
        if profile.storage_state_path.exists() and profile.storage_state_path.stat().st_size > 0:
            context_kwargs["storage_state"] = str(profile.storage_state_path)

        context = browser.new_context(**context_kwargs)

        try:
            for url in clean_urls:
                page = context.new_page()
                try:
                    payload = fetch_page_content(page, url, profile)
                    attachment_path = build_attachment_path(
                        attachments_dir,
                        payload["title"],
                        payload["resolved_url"],
                    )
                    attachment_path.write_text(
                        render_attachment_content(
                            title=payload["title"],
                            text=payload["text"],
                            source_url=payload["resolved_url"],
                            analyst_id=profile.analyst_id,
                        ),
                        encoding="utf-8",
                    )
                    imported.append(
                        {
                            "url": url,
                            "resolved_url": payload["resolved_url"],
                            "title": payload["title"],
                            "attachment_path": str(attachment_path),
                            "attachment_name": attachment_path.name,
                        }
                    )
                except ConfluenceImportError as exc:
                    failed.append({"url": url, "error": str(exc)})
                except Exception as exc:
                    failed.append({"url": url, "error": f"Неожиданная ошибка импорта: {exc}"})
                finally:
                    page.close()

            context.storage_state(path=str(profile.storage_state_path))
            protect_file(profile.storage_state_path)
        finally:
            context.close()
            browser.close()

    return {
        "analyst_id": profile.analyst_id,
        "imported": imported,
        "failed": failed,
    }
