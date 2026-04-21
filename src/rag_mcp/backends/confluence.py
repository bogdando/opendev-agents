"""Confluence backend: search Confluence spaces via REST API.

Each configured space becomes a ``vector_store_id``.  Multiple spaces
can be served by comma-separating them in ``CONFLUENCESPACE``.

Supports Confluence Cloud with either **HTTP Basic** (email + API token) or
**OAuth 2.0** (Bearer access token from Atlassian 3LO). OAuth calls **must**
use ``https://api.atlassian.com/ex/confluence/{cloudId}/rest/api/...`` per
Atlassian; the backend resolves ``cloudId`` from ``CONFLUENCECLOUDID`` or
from ``GET /oauth/token/accessible-resources`` matching ``CONFLUENCEURL``.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any, Literal
from urllib.parse import urlparse

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


def _site_origin(url: str) -> str:
    """``https://tenant.atlassian.net`` from ``CONFLUENCEURL`` (strip ``/wiki``)."""
    u = url.strip()
    if "://" not in u:
        u = f"https://{u}"
    p = urlparse(u)
    netloc = p.netloc or p.path.split("/")[0]
    scheme = p.scheme or "https"
    return f"{scheme}://{netloc}"


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
        auth_mode: Literal["basic", "oauth"] = "oauth",
        cloud_id: str = "",
    ) -> None:
        # Public wiki URL for human-facing page links (always tenant host).
        self._public_wiki_base = _wiki_base_url(base_url)
        self._site_origin = _site_origin(base_url)
        self._spaces = spaces
        self._max_chars = max_response_chars
        self._auth_mode = auth_mode
        self._explicit_cloud_id = cloud_id.strip()
        self._oauth_api_base: str | None = None
        self._oauth_lock = asyncio.Lock()
        if auth_mode == "oauth":
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
            logger.debug(
                "Confluence OAuth (Bearer); public wiki base for links: %s",
                self._public_wiki_base,
            )
        else:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                auth=(email, token),
                headers={"Accept": "application/json"},
            )
            logger.debug("Confluence Basic auth, API base: %s", self._public_wiki_base)

    async def _ensure_oauth_api_base(self) -> str:
        """REST API prefix: site ``.../wiki`` (basic) or Atlassian gateway (oauth)."""
        if self._auth_mode != "oauth":
            return self._public_wiki_base
        if self._oauth_api_base is not None:
            return self._oauth_api_base
        async with self._oauth_lock:
            if self._oauth_api_base is not None:
                return self._oauth_api_base
            if self._explicit_cloud_id:
                self._oauth_api_base = (
                    "https://api.atlassian.com/ex/confluence/"
                    f"{self._explicit_cloud_id}"
                )
                cid = self._explicit_cloud_id
                tail = cid[-12:] if len(cid) > 12 else cid
                logger.info(
                    "Confluence OAuth API base from CONFLUENCECLOUDID (…%s)",
                    tail,
                )
            else:
                self._oauth_api_base = await self._discover_oauth_api_base()
            logger.debug("Confluence OAuth REST prefix: %s", self._oauth_api_base)
            return self._oauth_api_base

    async def _discover_oauth_api_base(self) -> str:
        """Resolve cloud ID via accessible-resources (OAuth must use api.atlassian.com)."""
        url = "https://api.atlassian.com/oauth/token/accessible-resources"
        resp = await self._client.get(url)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = (e.response.text or "")[:_HTTP_ERR_BODY_MAX]
            logger.warning(
                "Confluence OAuth accessible-resources HTTP %s: %s",
                e.response.status_code,
                body,
            )
            raise ValueError(
                "OAuth token rejected by accessible-resources "
                f"(HTTP {e.response.status_code}). "
                "Use a valid 3LO access token or set CONFLUENCECLOUDID."
            ) from e
        resources: list[dict[str, Any]] = resp.json()
        want = self._site_origin.rstrip("/")
        for item in resources:
            item_url = (item.get("url") or "").rstrip("/")
            if item_url == want:
                cid = item["id"]
                logger.info(
                    "Confluence OAuth matched site %s to cloud ID ...%s",
                    want,
                    str(cid)[-8:],
                )
                return f"https://api.atlassian.com/ex/confluence/{cid}"
        for item in resources:
            scopes = item.get("scopes") or []
            if any("confluence" in str(s).lower() for s in scopes):
                cid = item["id"]
                logger.warning(
                    "Confluence OAuth using first Confluence-scoped site: %s",
                    item.get("url"),
                )
                return f"https://api.atlassian.com/ex/confluence/{cid}"
        raise ValueError(
            "No Confluence site in accessible-resources for this token "
            f"(expected URL {want}). Set CONFLUENCECLOUDID explicitly."
        )

    async def _cql_search(
        self, cql: str, limit: int
    ) -> list[dict[str, Any]]:
        """Execute a CQL query and return the result array."""
        api_base = await self._ensure_oauth_api_base()
        url = f"{api_base}/rest/api/content/search"
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
        api_base = await self._ensure_oauth_api_base()
        url = f"{api_base}/rest/api/space/{space_key}"
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

            webui = page.get("_links", {}).get(
                "webui", f"/spaces/{space_key}"
            )
            if webui.startswith("http"):
                page_url = webui
            else:
                page_url = self._public_wiki_base.rstrip("/") + (
                    webui if webui.startswith("/") else f"/{webui}"
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
