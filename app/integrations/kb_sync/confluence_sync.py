"""ConfluenceSyncProvider — fetches a page from Confluence REST API and converts it to markdown."""
from __future__ import annotations

import re

import httpx

from app.integrations.kb_sync.base import SyncProviderBase, SyncResult, _resolve_token, _sha256


class ConfluenceSyncProvider(SyncProviderBase):
    """Fetch a Confluence page and convert its storage format to markdown.

    Required sync_config keys:
      base_url  — Confluence base URL, e.g. "https://myorg.atlassian.net"
      page_id   — Confluence page ID, e.g. "12345678"

    Optional sync_config keys:
      space_key — informational only; not used in the API call
      auth      — {"type": "secret_ref", "secret_name": "confluence_token"}
                  or {"type": "bearer", "token": "..."}
    """

    provider_type = "confluence"

    async def fetch(
        self,
        sync_config: dict,
        secret_resolver: object | None = None,
    ) -> SyncResult:
        base_url = sync_config.get("base_url", "").rstrip("/")
        page_id = sync_config.get("page_id", "")

        if not base_url or not page_id:
            return SyncResult(
                outcome="config_invalid",
                error_message="Missing required sync_config fields: base_url, page_id",
            )

        url = f"{base_url}/wiki/rest/api/content/{page_id}"
        params: dict[str, str] = {"expand": "body.storage,version"}
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "Calseta/1.0",
        }

        token = await _resolve_token(sync_config, secret_resolver)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params, headers=headers)

            if resp.status_code == 404:
                return SyncResult(
                    outcome="fetch_failed",
                    error_message=f"Confluence page {page_id} not found",
                )
            if resp.status_code == 401:
                return SyncResult(
                    outcome="fetch_failed",
                    error_message="Confluence authentication failed — check your API token",
                )
            if resp.status_code != 200:
                return SyncResult(
                    outcome="fetch_failed",
                    error_message=f"Confluence API returned HTTP {resp.status_code}",
                )

            data = resp.json()
            storage_body: str = (
                data.get("body", {}).get("storage", {}).get("value", "")
            )
            version_number = str(data.get("version", {}).get("number", ""))

            content = _confluence_storage_to_markdown(storage_body)
            content_hash = _sha256(content)
            return SyncResult(
                outcome="updated",
                content=content,
                content_hash=content_hash,
                sync_source_ref=version_number,
            )

        except Exception as exc:
            return SyncResult(outcome="fetch_failed", error_message=str(exc))

    def validate_config(self, sync_config: dict) -> list[str]:
        errors: list[str] = []
        if not sync_config.get("base_url"):
            errors.append("Missing required field: base_url")
        if not sync_config.get("page_id"):
            errors.append("Missing required field: page_id")
        return errors


def _confluence_storage_to_markdown(storage_xml: str) -> str:
    """Best-effort conversion of Confluence storage XML to markdown.

    Handles common constructs: headings, bold, italic, inline code, code blocks,
    list items, paragraphs, and line breaks. Strips remaining XML tags.
    """
    text = storage_xml

    # Headings
    text = re.sub(
        r"<h([1-6])[^>]*>(.*?)</h\1>",
        lambda m: "#" * int(m.group(1)) + " " + m.group(2),
        text,
        flags=re.DOTALL,
    )

    # Bold
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL)

    # Italic
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.DOTALL)

    # Inline code
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)

    # Confluence structured macro code blocks
    text = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
        r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?"
        r"</ac:structured-macro>",
        r"```\n\1\n```",
        text,
        flags=re.DOTALL,
    )

    # List items
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1", text, flags=re.DOTALL)

    # Paragraphs → double newline
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", text, flags=re.DOTALL)

    # Line breaks
    text = re.sub(r"<br\s*/?>", "\n", text)

    # Strip all remaining XML/HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
