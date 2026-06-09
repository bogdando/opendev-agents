"""Solr/OKP backend using okp-mcp's Solr client and formatting.

Imports okp_mcp submodules directly (bypassing __init__.py) to reuse
the Solr query engine and result annotation without triggering MCP tool
registration or replicating upstream code.

Requires a running Solr instance with the OKP ``portal`` core.
"""

from __future__ import annotations

import logging

import httpx

from okp_mcp.content import doc_uri  # pyright: ignore[reportMissingImports]
from okp_mcp.formatting import _annotate_result  # pyright: ignore[reportMissingImports]
from okp_mcp.solr import _clean_query, _solr_query  # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


class SolrBackend:
    """Backend that queries Solr/OKP via okp-mcp's client layer."""

    def __init__(
        self,
        solr_url: str,
        max_response_chars: int,
        proxy_url: str | None = None,
    ) -> None:
        self._solr_endpoint = f"{solr_url}/solr/portal/select"
        self._max_response_chars = max_response_chars
        self._client = httpx.AsyncClient(
            timeout=30.0, proxy=proxy_url
        )

    async def search(
        self, query: str, store_id: str, top_k: int
    ) -> list[dict]:
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

        docs = data.get("response", {}).get("docs", [])
        if not docs:
            return []

        max_score = data.get("response", {}).get(
            "maxScore", 1.0
        ) or 1.0

        highlights = data.get("highlighting", {})

        results: list[dict] = []
        for doc in docs:
            title = (
                doc.get("allTitle")
                or doc.get("heading_h1")
                or doc.get("title", "").split("|")[0].strip()
                or "Untitled"
            )
            if isinstance(title, list):
                title = title[0]

            doc_id = doc.get("id", "")
            hl_snippets = highlights.get(doc_id, {}).get(
                "main_content", []
            )
            hl_text = "\n".join(hl_snippets) if hl_snippets else ""
            content = doc.get("main_content", "")
            if isinstance(content, list):
                content = "\n".join(content)

            annotations, applicability, _sort_key = _annotate_result(
                title, hl_text, content,
                product=doc.get("product", ""),
            )

            parts: list[str] = [f"**{title}**"]
            parts.append(
                f"Type: {doc.get('documentKind', 'Unknown')}"
            )
            if applicability:
                parts.append(f"Applicability: {applicability}")
            url_path = doc_uri(doc)
            parts.append(
                f"URL: https://access.redhat.com{url_path}"
            )
            if doc.get("lastModifiedDate"):
                parts.append(
                    f"Last updated: {doc['lastModifiedDate']}"
                )
            if annotations:
                parts.extend(annotations)
            if hl_text:
                parts.append(f"Content: {hl_text[:3000]}")
            elif doc.get("portal_synopsis"):
                parts.append(
                    f"Content: {doc['portal_synopsis']}"
                )
            elif content:
                parts.append(f"Content: {content[:3000]}")

            formatted_text = "\n".join(parts)
            raw_score = doc.get("score", 0.0)
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
                        "doc_kind": doc.get("documentKind", ""),
                        "product": doc.get("product", ""),
                    },
                }
            )
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
