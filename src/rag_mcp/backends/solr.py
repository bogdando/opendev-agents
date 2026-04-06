"""Solr/OKP backend using okp-mcp's Solr client and formatting.

Imports okp_mcp submodules directly (bypassing __init__.py) to reuse
the Solr query engine and result formatting without triggering MCP tool
registration or replicating upstream code.

Requires a running Solr instance with the OKP ``portal`` core.
"""

from __future__ import annotations

import logging

import httpx

from okp_mcp.content import doc_uri  # pyright: ignore[reportMissingImports]
from okp_mcp.formatting import _format_result  # pyright: ignore[reportMissingImports]
from okp_mcp.solr import _clean_query, _solr_query  # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


class SolrBackend:
    """Backend that queries Solr/OKP via okp-mcp's client layer."""

    def __init__(self, solr_url: str, max_response_chars: int) -> None:
        self._solr_endpoint = f"{solr_url}/solr/portal/select"
        self._max_response_chars = max_response_chars
        self._client = httpx.AsyncClient(timeout=30.0)

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

        results: list[dict] = []
        for doc in docs:
            formatted_text, _sort_key = await _format_result(
                doc, data, include_content=True, query=query
            )
            title = (
                doc.get("allTitle")
                or doc.get("heading_h1")
                or doc.get("title", "").split("|")[0].strip()
                or "Untitled"
            )
            if isinstance(title, list):
                title = title[0]
            url_path = doc_uri(doc)
            results.append(
                {
                    "text": formatted_text,
                    "source": f"https://access.redhat.com{url_path}",
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
            }
        ]

    async def get_store(self, store_id: str) -> dict | None:
        if store_id == "okp":
            stores = await self.list_stores()
            return stores[0]
        return None
