"""Memory protocol and factory for cross-session memory management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from rag_mcp.config import ServerConfig


class MemoryProtocol(Protocol):
    """Interface that every memory backend must satisfy.

    Memory backends handle cross-session recall and persistence,
    separate from the knowledge retrieval BackendProtocol.
    """

    async def recall(
        self, query: str, category: str = "", top_k: int = 5
    ) -> list[dict]:
        """Find memories relevant to the query.

        Returns list of dicts with keys: content, category, saved_at, uri.
        """
        ...

    async def remember(
        self, content: str, category: str = "context"
    ) -> dict:
        """Persist a new memory.

        Returns dict with keys: uri, category, saved_at.
        """
        ...

    async def list_memories(
        self, category: str = "", limit: int = 20
    ) -> list[dict]:
        """List recent memories, optionally filtered by category."""
        ...


VALID_CATEGORIES = frozenset(
    {"preference", "decision", "learning", "correction", "context", "workflow"}
)


def get_memory_backend(config: ServerConfig) -> MemoryProtocol | None:
    """Instantiate the memory backend selected by config, or None if disabled."""
    if config.memory_backend == "none":
        return None

    if config.memory_backend == "local":
        from rag_mcp.memory.local import LocalMemoryBackend

        return LocalMemoryBackend(config.memory_dir)

    if config.memory_backend == "openviking":
        from rag_mcp.memory.openviking import OpenVikingMemoryBackend

        return OpenVikingMemoryBackend(
            url=config.openviking_url,
            account=config.openviking_account,
            user=config.openviking_user,
            agent_id=config.openviking_agent_id,
            api_key=config.openviking_api_key,
        )

    raise ValueError(f"Unknown memory backend: {config.memory_backend!r}")
