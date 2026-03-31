"""RAG MCP Server configuration via environment variables and CLI."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    """Configuration for the RAG MCP server.

    All fields can be set via environment variables with the RAG_MCP_ prefix
    (e.g. RAG_MCP_TRANSPORT=stdio) or via CLI flags (e.g. --transport stdio).
    """

    model_config = {"env_prefix": "RAG_MCP_"}

    transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    backend: Literal["mock"] = "mock"
    knowledge_dir: str = "./knowledge"
    max_response_chars: int = Field(default=30000, ge=1)
