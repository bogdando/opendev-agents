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

    raise ValueError(f"Unknown backend: {config.backend!r}")
