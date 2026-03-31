"""FastMCP application instance and lifespan management."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastmcp import Context, FastMCP

from rag_mcp.backends import BackendProtocol, get_backend
from rag_mcp.config import ServerConfig

logger = logging.getLogger(__name__)

_server_config: ServerConfig | None = None


@dataclass
class AppContext:
    backend: BackendProtocol
    config: ServerConfig


@asynccontextmanager
async def _app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    config = _server_config or ServerConfig()
    backend = get_backend(config)
    logger.info(
        "RAG MCP server ready  backend=%s  knowledge_dir=%s",
        config.backend,
        config.knowledge_dir,
    )
    yield {"app": AppContext(backend=backend, config=config)}


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
