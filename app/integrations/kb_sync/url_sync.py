"""URLSyncProvider — fetches content from an arbitrary HTTP URL."""
from __future__ import annotations

import contextlib
import os
import tempfile

import httpx

from app.integrations.kb_sync.base import SyncProviderBase, SyncResult, _sha256


class URLSyncProvider(SyncProviderBase):
    """Fetch content from any public HTTP/HTTPS URL.

    Handles plain text and markdown directly.
    For HTML or other content types, attempts markitdown conversion.
    Falls back to raw text if markitdown is unavailable.

    Required sync_config keys:
      url — the full URL to fetch

    Optional sync_config keys:
      auth — {"type": "bearer", "token": "..."} for authenticated endpoints
    """

    provider_type = "url"

    async def fetch(
        self,
        sync_config: dict,
        secret_resolver: object | None = None,
    ) -> SyncResult:
        url = sync_config.get("url", "")
        if not url:
            return SyncResult(
                outcome="config_invalid",
                error_message="Missing required sync_config field: url",
            )

        headers: dict[str, str] = {"User-Agent": "Calseta/1.0"}

        # Support bearer auth for private endpoints
        auth = sync_config.get("auth")
        if auth and auth.get("type") == "bearer":
            headers["Authorization"] = f"Bearer {auth.get('token', '')}"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)

            if resp.status_code != 200:
                return SyncResult(
                    outcome="fetch_failed",
                    error_message=f"HTTP {resp.status_code} fetching {url}",
                )

            content_type = resp.headers.get("content-type", "")

            # Plain text or markdown — use directly
            if "text/plain" in content_type or url.endswith(".md"):
                content = resp.text
            else:
                content = _convert_to_markdown(resp.content, resp.text, content_type, url)

            content_hash = _sha256(content)
            return SyncResult(outcome="updated", content=content, content_hash=content_hash)

        except Exception as exc:
            return SyncResult(outcome="fetch_failed", error_message=str(exc))

    def validate_config(self, sync_config: dict) -> list[str]:
        if not sync_config.get("url"):
            return ["Missing required field: url"]
        return []


def _convert_to_markdown(
    raw_bytes: bytes,
    fallback_text: str,
    content_type: str,
    url: str,
) -> str:
    """Convert raw response bytes to markdown via markitdown, falling back to raw text."""
    if "text/html" in content_type:
        suffix = ".html"
    elif "application/pdf" in content_type:
        suffix = ".pdf"
    else:
        suffix = ".txt"

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as f:
            f.write(raw_bytes)
            tmp_path = f.name

        from markitdown import MarkItDown  # type: ignore[import-not-found]

        md = MarkItDown()
        result = md.convert(tmp_path)
        return result.text_content
    except Exception:
        return fallback_text
    finally:
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
