"""RAG MCP Server — thin wrapper exposing knowledge as MCP tools and resources."""

from __future__ import annotations

import logging

from rag_mcp.config import ServerConfig
from rag_mcp.server import mcp

__version__ = "0.1.0"

logger = logging.getLogger(__name__)


def _resolve_ssl_cert_file() -> None:
    """Pick the first existing CA bundle from SSL_CERT_FILE, SSL_CERT_FILE_ALT,
    or well-known system paths."""
    import os
    from pathlib import Path

    primary = os.environ.get("SSL_CERT_FILE", "")
    if primary and Path(primary).is_file():
        return

    candidates = [os.environ.get("SSL_CERT_FILE_ALT", "")]
    candidates += [
        "/etc/pki/tls/certs/ca-bundle.crt",
        "/etc/ssl/certs/ca-certificates.crt",
    ]
    for path in candidates:
        if path and Path(path).is_file():
            os.environ["SSL_CERT_FILE"] = path
            return


def main() -> None:
    """Entry point: parse config, configure logging, start the MCP server."""
    from rag_mcp import _app

    _resolve_ssl_cert_file()
    config = ServerConfig()
    _app._server_config = config

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info(
        "Starting RAG MCP server  transport=%s  backend=%s  proxy=%s",
        config.transport,
        config.backend,
        "yes" if config.proxy_url else "no",
    )

    if config.transport in ("sse", "streamable-http"):
        mcp.run(transport=config.transport, host=config.host, port=config.port)
    else:
        mcp.run(transport="stdio")
