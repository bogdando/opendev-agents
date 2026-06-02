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

try:
    from fastmcp import Context, FastMCP
except ImportError:
    from mcp.server.fastmcp import Context, FastMCP

from rag_mcp.backends import BackendProtocol, get_backend
from rag_mcp.config import ServerConfig
from rag_mcp.memory import MemoryProtocol, get_memory_backend

__all__ = ["AppContext", "Context", "get_app_context", "init_config", "mcp"]

logger = logging.getLogger(__name__)

_server_config: ServerConfig | None = None

init_config = ServerConfig()


@dataclass
class AppContext:
    backend: BackendProtocol
    config: ServerConfig
    memory: MemoryProtocol | None = None


def get_app_context(ctx: Context) -> AppContext:
    """Retrieve the AppContext from a tool invocation context."""
    return ctx.request_context.lifespan_context["app"]


@asynccontextmanager
async def _app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    config = _server_config or ServerConfig()
    backend = get_backend(config)
    memory = get_memory_backend(config)
    logger.info(
        "RAG MCP server ready  name=%s  backend=%s  memory=%s",
        config.effective_server_name,
        config.backend,
        config.memory_backend,
    )
    yield {"app": AppContext(backend=backend, config=config, memory=memory)}


mcp = FastMCP(
    init_config.effective_server_name,
    instructions=(
        "Search external knowledge bases (OpenStack docs, project specs, "
        "deployment guides) to augment your answers. Use the search tool "
        "to retrieve relevant documentation before responding."
    ),
    lifespan=_app_lifespan,
)
