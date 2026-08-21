"""Solr/OKP backend using okp-mcp's Solr client and formatting.

Imports okp_mcp submodules directly (bypassing __init__.py) to reuse
the Solr query engine and result annotation without triggering MCP tool
registration or replicating upstream code.

Requires a running Solr instance with the OKP ``portal`` core.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx
from okp_mcp.content import doc_uri  # pyright: ignore[reportMissingImports]
from okp_mcp.formatting import annotate_result  # pyright: ignore[reportMissingImports]
from okp_mcp.solr import (  # pyright: ignore[reportMissingImports]
    _clean_query,
    _solr_query,
)

if TYPE_CHECKING:
    from rag_mcp.embeddings import EmbeddingClient

logger = logging.getLogger(__name__)


class SolrBackend:
    """Backend that queries Solr/OKP via okp-mcp's client layer."""

    def __init__(
        self,
        solr_url: str,
        max_response_chars: int,
        proxy_url: str | None = None,
        search_mode: str = "keyword",
    ) -> None:
        self._solr_url = solr_url.rstrip("/")
        self._solr_endpoint = f"{self._solr_url}/solr/portal/select"
        self._max_response_chars = max_response_chars
        self._search_mode = search_mode
        self._client = httpx.AsyncClient(
            timeout=30.0, proxy=proxy_url
        )

    async def search(
        self, query: str, store_id: str, top_k: int, **kwargs: Any
    ) -> list[dict]:
        embeddings: EmbeddingClient | None = kwargs.get("embeddings")

        if self._search_mode in ("semantic", "hybrid") and embeddings:
            result = await self._vector_search(query, store_id, top_k, embeddings)
            if result is not None:
                return result
            logger.warning(
                "Vector search failed, falling back to BM25 keyword search"
            )

        cleaned = _clean_query(query)
        data = await _solr_query(
            {
                "q": cleaned,
                "fl": (
                    "id,allTitle,heading_h1,title,view_uri,url_slug,"
                    "documentKind,product,documentation_version,"
                    "lastModifiedDate,main_content,portal_synopsis,score"
                ),
                "rows": top_k,
            },
            client=self._client,
            solr_endpoint=self._solr_endpoint,
        )

        docs = data.response.docs
        if not docs:
            return []

        raw_scores = [doc.score for doc in docs if doc.score is not None]
        max_score = max(raw_scores, default=1.0) or 1.0

        highlights = data.highlighting

        results: list[dict] = []
        for doc in docs:
            title = (
                doc.allTitle
                or (doc.heading_h1[0] if doc.heading_h1 else "")
                or doc.title.split("|")[0].strip()
                or "Untitled"
            )

            hl_snippets = highlights.get(doc.id, {}).get(
                "main_content", []
            )
            hl_text = "\n".join(hl_snippets) if hl_snippets else ""
            content = doc.main_content

            annotations, applicability, _sort_key = annotate_result(
                title, hl_text, content,
                product=doc.product,
            )

            parts: list[str] = [f"**{title}**"]
            parts.append(
                f"Type: {doc.documentKind or 'Unknown'}"
            )
            if applicability:
                parts.append(f"Applicability: {applicability}")
            url_path = doc_uri(doc)
            parts.append(
                f"URL: https://access.redhat.com{url_path}"
            )
            if doc.lastModifiedDate:
                parts.append(
                    f"Last updated: {doc.lastModifiedDate}"
                )
            if annotations:
                parts.extend(annotations)
            if hl_text:
                parts.append(f"Content: {hl_text[:3000]}")
            elif doc.portal_synopsis:
                parts.append(
                    f"Content: {doc.portal_synopsis}"
                )
            elif content:
                parts.append(f"Content: {content[:3000]}")

            formatted_text = "\n".join(parts)
            raw_score = doc.score or 0.0
            results.append(
                {
                    "text": formatted_text,
                    "source": f"https://access.redhat.com{url_path}",
                    "score": round(
                        raw_score / max_score, 4
                    ),
                    "metadata": {
                        "title": title,
                        "store_id": store_id,
                        "doc_kind": doc.documentKind,
                        "product": doc.product,
                    },
                }
            )
        return results

    async def _vector_search(
        self,
        query: str,
        store_id: str,
        top_k: int,
        embeddings: EmbeddingClient,
    ) -> list[dict] | None:
        """Attempt semantic or hybrid search via Solr vector endpoints.

        Returns None if embedding or Solr request fails (caller falls back).
        """
        vec = await embeddings.embed_query(query)
        if vec is None:
            return None

        vector_str = "[" + ",".join(str(v) for v in vec) + "]"
        endpoint = (
            f"{self._solr_url}/solr/portal/hybrid-search"
            if self._search_mode == "hybrid"
            else f"{self._solr_url}/solr/portal/semantic-search"
        )

        params: dict[str, Any] = {"topK": top_k, "vector": vector_str}
        if self._search_mode == "hybrid":
            params["q"] = _clean_query(query)

        try:
            resp = await self._client.post(
                endpoint,
                data=params,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Solr vector endpoint failed: %s", exc)
            return None

        docs = body.get("response", {}).get("docs", [])
        if not docs:
            return []

        raw_scores = [d.get("score", 0.0) for d in docs]
        max_score = max(raw_scores, default=1.0) or 1.0

        results: list[dict] = []
        for doc in docs:
            title = doc.get("allTitle") or doc.get("title", "Untitled")
            content = doc.get("main_content", "")
            url_slug = doc.get("url_slug", "")
            source = f"https://access.redhat.com{url_slug}" if url_slug else ""
            raw_score = doc.get("score", 0.0)

            results.append({
                "text": f"**{title}**\n\nContent: {content[:3000]}",
                "source": source,
                "score": round(raw_score / max_score, 4),
                "metadata": {
                    "title": title,
                    "store_id": store_id,
                    "doc_kind": doc.get("documentKind"),
                    "product": doc.get("product"),
                },
            })
        return results

    async def list_stores(self) -> list[dict]:
        return [
            {
                "id": "okp",
                "name": "OKP Knowledge Base",
                "description": "Red Hat documentation, solutions, articles, CVEs, and errata via Solr/OKP",
                "doc_count": -1,
                "last_updated": "live",
                "access": "credentialed",
                "freshness": "live",
                "coverage": ["documentation", "solutions", "articles", "cves", "errata"],
            }
        ]

    async def get_store(self, store_id: str) -> dict | None:
        if store_id == "okp":
            stores = await self.list_stores()
            return stores[0]
        return None
