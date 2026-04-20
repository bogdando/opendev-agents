"""Backend protocol and factory for RAG MCP server."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from rag_mcp.config import ServerConfig


class BackendProtocol(Protocol):
    """Interface that every RAG backend must satisfy."""

    async def search(
        self, query: str, store_id: str, top_k: int
    ) -> list[dict]: ...

    async def list_stores(self) -> list[dict]: ...

    async def get_store(self, store_id: str) -> dict | None: ...


def get_backend(config: ServerConfig) -> BackendProtocol:
    """Instantiate the backend selected by *config.backend*."""
    if config.backend == "mock":
        from rag_mcp.backends.mock import MockBackend

        return MockBackend(config.knowledge_dir)

    if config.backend == "solr":
        from rag_mcp.backends.solr import SolrBackend

        return SolrBackend(config.solr_url, config.max_response_chars)

    if config.backend == "confluence":
        from rag_mcp.backends.confluence import ConfluenceBackend

        spaces = [
            s.strip()
            for s in config.confluence_space.split(",")
            if s.strip()
        ]
        if not spaces:
            raise ValueError(
                "RAG_MCP_CONFLUENCE_SPACE must list at least one "
                "Confluence space key (comma-separated)"
            )
        if not config.confluence_url:
            raise ValueError(
                "RAG_MCP_CONFLUENCE_URL is required for the "
                "confluence backend"
            )
        if not config.confluence_email or not config.confluence_token:
            raise ValueError(
                "RAG_MCP_CONFLUENCE_EMAIL and RAG_MCP_CONFLUENCE_TOKEN "
                "are required for the confluence backend"
            )
        return ConfluenceBackend(
            base_url=config.confluence_url,
            email=config.confluence_email,
            token=config.confluence_token,
            spaces=spaces,
            max_response_chars=config.max_response_chars,
        )

    raise ValueError(f"Unknown backend: {config.backend!r}")
