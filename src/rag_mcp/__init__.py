"""RAG MCP Server — thin wrapper exposing knowledge as MCP tools and resources."""

from __future__ import annotations

import logging

from rag_mcp.config import ServerConfig
from rag_mcp.server import mcp

__version__ = "0.1.0"

logger = logging.getLogger(__name__)


def main() -> None:
    """Entry point: parse config, configure logging, start the MCP server."""
    from rag_mcp import server as _server

    config = ServerConfig()
    _server._server_config = config

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info(
        "Starting RAG MCP server  transport=%s  backend=%s",
        config.transport,
        config.backend,
    )

    if config.transport in ("sse", "streamable-http"):
        mcp.run(transport=config.transport, host=config.host, port=config.port)
    else:
        mcp.run(transport="stdio")
