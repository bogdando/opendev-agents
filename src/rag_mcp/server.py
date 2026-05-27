"""FastMCP application instance and lifespan management."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastmcp import Context, FastMCP

from rag_mcp.backends import BackendProtocol, get_backend
from rag_mcp.config import ServerConfig
from rag_mcp.memory import MemoryProtocol, get_memory_backend

logger = logging.getLogger(__name__)

_server_config: ServerConfig | None = None


@dataclass
class AppContext:
    backend: BackendProtocol
    config: ServerConfig
    memory: MemoryProtocol | None = None


@asynccontextmanager
async def _app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    config = _server_config or ServerConfig()
    server._mcp_server.name = config.effective_server_name
    backend = get_backend(config)
    memory = get_memory_backend(config)
    logger.info(
        "RAG MCP server ready  name=%s  backend=%s  memory=%s",
        config.effective_server_name,
        config.backend,
        config.memory_backend,
    )
    yield {"app": AppContext(backend=backend, config=config, memory=memory)}


def get_app_context(ctx: Context) -> AppContext:
    """Retrieve the AppContext from a tool invocation context."""
    return ctx.request_context.lifespan_context["app"]


mcp = FastMCP(
    "rag-knowledge",
    instructions=(
        "Search external knowledge bases (OpenStack docs, project specs, "
        "deployment guides) to augment your answers. Use the search tool "
        "to retrieve relevant documentation before responding."
    ),
    lifespan=_app_lifespan,
)

import rag_mcp.tools as _tools  # noqa: F401, E402
import rag_mcp.memory_tools as _memory_tools  # noqa: F401, E402
