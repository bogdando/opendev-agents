"""Singleton FastMCP application instance and shared context helpers.

This module owns the `mcp` object and is imported by tool modules
(tools.py, memory_tools.py).  It deliberately avoids importing those
modules to break the circular dependency that previously caused
sporadic tool-discovery failures in Cursor's MCP client.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

try:
    from fastmcp import Context, FastMCP
except ImportError:
    from mcp.server.fastmcp import Context, FastMCP

from rag_mcp.backends import BackendProtocol, get_backend
from rag_mcp.config import ServerConfig
from rag_mcp.memory import MemoryProtocol, get_memory_backend

if TYPE_CHECKING:
    from rag_mcp.embeddings import EmbeddingClient
    from rag_mcp.summarizer import BackgroundSummarizer

__all__ = ["AppContext", "Context", "get_app_context", "init_config", "mcp"]

logger = logging.getLogger(__name__)

_server_config: ServerConfig | None = None

init_config = ServerConfig()


@dataclass
class AppContext:
    backend: BackendProtocol
    config: ServerConfig
    memory: MemoryProtocol | None = None
    embeddings: "EmbeddingClient | None" = None
    bg_summarizer: "BackgroundSummarizer | None" = None


def get_app_context(ctx: Context) -> AppContext:
    """Retrieve the AppContext from a tool invocation context."""
    return ctx.request_context.lifespan_context["app"]


@asynccontextmanager
async def _app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    config = _server_config or ServerConfig()
    backend = get_backend(config)
    memory = get_memory_backend(config)

    embeddings = None
    embed_url = config.effective_embedding_url
    if embed_url:
        from rag_mcp.embeddings import EmbeddingClient
        embeddings = EmbeddingClient(embed_url, config.embedding_model)
        logger.info(
            "Embedding client enabled: %s model=%s",
            embed_url, config.embedding_model,
        )

    bg_summarizer = None
    if config.tiered_retrieval:
        summarizer_url = config.effective_summarizer_url
        if summarizer_url:
            from rag_mcp.summarizer import BackgroundSummarizer, Summarizer
            summarizer = Summarizer(summarizer_url, config.summarizer_model)

            async def _noop_callback(
                file_key: str, l0: str | None, l1: str | None
            ) -> None:
                pass

            bg_summarizer = BackgroundSummarizer(summarizer, _noop_callback)
            logger.info(
                "Tiered retrieval enabled: summarizer=%s model=%s",
                summarizer_url, config.summarizer_model,
            )
        else:
            logger.info(
                "Tiered retrieval enabled but no summarizer URL — "
                "extractive fallback only"
            )

    logger.info(
        "RAG MCP server ready  name=%s  backend=%s  memory=%s",
        config.effective_server_name,
        config.backend,
        config.memory_backend,
    )
    yield {"app": AppContext(
        backend=backend, config=config, memory=memory,
        embeddings=embeddings, bg_summarizer=bg_summarizer,
    )}


mcp = FastMCP(
    init_config.effective_server_name,
    instructions=(
        "Search external knowledge bases (OpenStack docs, project specs, "
        "deployment guides) to augment your answers. Use the search tool "
        "to retrieve relevant documentation before responding."
    ),
    lifespan=_app_lifespan,
)
