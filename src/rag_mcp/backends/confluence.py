"""Confluence backend: search Confluence spaces via REST API.

Each configured space becomes a ``vector_store_id``.  Multiple spaces
can be served by comma-separating them in ``RAG_MCP_CONFLUENCE_SPACE``.

Requires Confluence Cloud (Atlassian) with an API token.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(raw: str) -> str:
    """Rough HTML-to-plaintext conversion for Confluence storage format."""
    text = raw.replace("<br/>", "\n").replace("<br>", "\n")
    text = text.replace("</p>", "\n\n").replace("</li>", "\n")
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


class ConfluenceBackend:
    """Backend that queries Confluence Cloud via REST API v2/v1."""

    def __init__(
        self,
        base_url: str,
        email: str,
        token: str,
        spaces: list[str],
        max_response_chars: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._spaces = spaces
        self._max_chars = max_response_chars
        self._client = httpx.AsyncClient(
            timeout=30.0,
            auth=(email, token),
        )

    async def _cql_search(
        self, cql: str, limit: int
    ) -> list[dict[str, Any]]:
        """Execute a CQL query and return the result array."""
        url = f"{self._base_url}/rest/api/content/search"
        params = {
            "cql": cql,
            "limit": str(limit),
            "expand": "body.view,version,space",
        }
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def _get_space_info(self, space_key: str) -> dict[str, Any]:
        url = f"{self._base_url}/rest/api/space/{space_key}"
        resp = await self._client.get(url)
        if resp.status_code == 200:
            return resp.json()
        return {"key": space_key, "name": space_key}

    async def list_stores(self) -> list[dict]:
        stores: list[dict] = []
        for space_key in self._spaces:
            info = await self._get_space_info(space_key)
            stores.append(
                {
                    "id": space_key.lower(),
                    "name": info.get("name", space_key),
                    "description": (
                        info.get("description", {})
                        .get("plain", {})
                        .get("value", f"Confluence space {space_key}")
                    ),
                    "doc_count": -1,
                    "last_updated": "live",
                    "access": "credentialed",
                    "freshness": "live",
                    "coverage": ["confluence", space_key.lower()],
                }
            )
        return stores

    async def get_store(self, store_id: str) -> dict | None:
        for s in await self.list_stores():
            if s["id"] == store_id:
                return s
        return None

    def _resolve_space_key(self, store_id: str) -> str | None:
        """Map a lowercase store_id back to the original space key."""
        for key in self._spaces:
            if key.lower() == store_id:
                return key
        return None

    async def search(
        self, query: str, store_id: str, top_k: int
    ) -> list[dict]:
        space_key = self._resolve_space_key(store_id)
        if space_key is None:
            return []

        escaped = query.replace('"', '\\"')
        cql = f'space = "{space_key}" AND text ~ "{escaped}"'
        pages = await self._cql_search(cql, top_k)

        results: list[dict] = []
        budget = self._max_chars
        for page in pages:
            title = page.get("title", "Untitled")
            body_html = (
                page.get("body", {}).get("view", {}).get("value", "")
            )
            text = _html_to_text(body_html)
            if len(text) > budget:
                text = text[:budget] + "\n\n[truncated]"
                budget = 0
            else:
                budget -= len(text)

            page_url = self._base_url + page.get("_links", {}).get(
                "webui", f"/wiki/spaces/{space_key}"
            )
            space_info = page.get("space", {})
            results.append(
                {
                    "text": text,
                    "source": page_url,
                    "metadata": {
                        "title": title,
                        "store_id": store_id,
                        "space": space_info.get("key", space_key),
                        "version": page.get("version", {}).get(
                            "number", 0
                        ),
                    },
                }
            )
            if budget <= 0:
                break
        return results
