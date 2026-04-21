"""Confluence backend: search Confluence spaces via REST API.

Each configured space becomes a ``vector_store_id``.  Multiple spaces
can be served by comma-separating them in ``CONFLUENCESPACE``.

Requires Confluence Cloud (Atlassian) with an API token.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import httpx

from rag_mcp.constants import SEARCH_STOP_WORDS

_HTTP_ERR_BODY_MAX = 800

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


def _wiki_base_url(url: str) -> str:
    """Confluence Cloud REST API lives under ``/wiki``.

    Accept either ``https://site.atlassian.net`` or ``.../wiki`` so callers
    can set ``CONFLUENCEURL`` to the site root (same as Jira) without
    duplicating ``/wiki`` in docs and env.
    """
    u = url.rstrip("/")
    if u.endswith("/wiki"):
        return u
    return f"{u}/wiki"


def _html_to_text(raw: str) -> str:
    """Rough HTML-to-plaintext conversion for Confluence storage format."""
    text = raw.replace("<br/>", "\n").replace("<br>", "\n")
    text = text.replace("</p>", "\n\n").replace("</li>", "\n")
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


def _cql_escape_literal(token: str) -> str:
    """Escape a CQL string literal (inside double quotes)."""
    return token.replace("\\", "\\\\").replace('"', '\\"')


def _wiki_query_tokens(query: str) -> list[str]:
    """Split query into tokens for full-text CQL (stop words removed).

    If nothing remains after filtering, uses the whole trimmed query as one
    phrase so short or stop-word-only queries still run.
    """
    raw_parts = [p for p in query.split() if p.strip()]
    tokens: list[str] = []
    for part in raw_parts:
        w = part.strip().strip(".,;:()[]\"'")
        if not w:
            continue
        if w.lower() in SEARCH_STOP_WORDS:
            continue
        tokens.append(w)
    if tokens:
        return tokens
    q = query.strip()
    return [q] if q else []


def _wiki_search_cql(space_key: str, tokens: list[str]) -> str:
    """Build CQL for space-scoped page/blog full-text search.

    Each token must match in body *or* title (Confluence stemmed full-text).
    Multiple tokens are ANDed. Results are newest first.
    """
    sk = _cql_escape_literal(space_key)
    parts: list[str] = [
        f'space = "{sk}"',
        'type in ("page", "blogpost")',
    ]
    for tok in tokens:
        lit = _cql_escape_literal(tok)
        parts.append(f'(text ~ "{lit}" OR title ~ "{lit}")')
    return " AND ".join(parts) + " order by lastModified desc"


def _wiki_phrase_fallback_cql(space_key: str, phrase: str) -> str:
    """Single phrase search when token AND returns nothing."""
    sk = _cql_escape_literal(space_key)
    lit = _cql_escape_literal(phrase.strip())
    return (
        f'space = "{sk}" AND type in ("page", "blogpost") '
        f'AND (text ~ "{lit}" OR title ~ "{lit}") '
        "order by lastModified desc"
    )


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
        self._base_url = _wiki_base_url(base_url)
        self._spaces = spaces
        self._max_chars = max_response_chars
        self._client = httpx.AsyncClient(
            timeout=30.0,
            auth=(email, token),
        )
        logger.debug("Confluence backend wiki base URL: %s", self._base_url)

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
        logger.debug(
            "Confluence CQL search GET %s limit=%s",
            url,
            params.get("limit"),
        )
        logger.debug("Confluence CQL: %s", cql)
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = (e.response.text or "")[:_HTTP_ERR_BODY_MAX]
            logger.warning(
                "Confluence CQL search HTTP %s: %s",
                e.response.status_code,
                body,
            )
            raise
        results = resp.json().get("results", [])
        logger.debug("Confluence CQL returned %d page(s)", len(results))
        return results

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

        tokens = _wiki_query_tokens(query)
        if not tokens:
            return []

        cql = _wiki_search_cql(space_key, tokens)
        logger.debug(
            "Confluence search store_id=%s space_key=%s top_k=%s",
            store_id,
            space_key,
            top_k,
        )
        pages = await self._cql_search(cql, top_k)

        if not pages and len(tokens) > 1:
            fb = _wiki_phrase_fallback_cql(space_key, query)
            logger.debug("Confluence phrase fallback after empty AND-token search")
            pages = await self._cql_search(fb, top_k)

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
