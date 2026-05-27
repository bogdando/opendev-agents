"""RAG MCP Server configuration via environment variables and CLI."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Configuration for the RAG MCP server.

    All fields can be set via environment variables with the RAG_MCP_ prefix
    (e.g. RAG_MCP_TRANSPORT=stdio) or via CLI flags (e.g. --transport stdio).

    Confluence settings also accept unprefixed names (no underscores):
    CONFLUENCEURL, CONFLUENCEEMAIL, CONFLUENCETOKEN, CONFLUENCESPACE.
    When both are set, the short name wins.
    """

    model_config = SettingsConfigDict(env_prefix="RAG_MCP_")

    transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    server_name: str = ""
    backend: Literal["mock", "solr", "confluence"] = "mock"
    knowledge_dir: str = "./knowledge"
    solr_url: str = "http://localhost:8983"
    confluence_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CONFLUENCEURL",
            "RAG_MCP_CONFLUENCE_URL",
        ),
    )
    confluence_email: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CONFLUENCEEMAIL",
            "RAG_MCP_CONFLUENCE_EMAIL",
        ),
    )
    confluence_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CONFLUENCETOKEN",
            "RAG_MCP_CONFLUENCE_TOKEN",
        ),
    )
    confluence_space: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CONFLUENCESPACE",
            "RAG_MCP_CONFLUENCE_SPACE",
        ),
    )
    max_response_chars: int = Field(default=30000, ge=1)

    memory_backend: Literal["local", "openviking", "none"] = "none"
    memory_dir: str = "./.memories"
    openviking_url: str = "http://127.0.0.1:1933"
    openviking_account: str = "default"
    openviking_user: str = "default"
    openviking_agent_id: str = "rag-mcp-server"

    @property
    def effective_server_name(self) -> str:
        """MCP server name advertised to clients.

        Defaults to a backend-specific name matching the conventional
        mcp.json keys so that clients (e.g. Cursor) see distinct server
        identities and don't confuse routing between instances.
        """
        if self.server_name:
            return self.server_name
        _names = {
            "mock": "rag-knowledge",
            "solr": "rag-knowledge-okp",
            "confluence": "rag-knowledge-wiki",
        }
        return _names.get(self.backend, "rag-knowledge")

    @property
    def proxy_url(self) -> str | None:
        """Return the HTTP(S) proxy URL from the environment, if any.

        Cursor's MCP ``env`` block may strip inherited proxy variables.
        Reading them eagerly at config time and threading them into httpx
        ensures backends work inside network-sandboxed containers (nono).
        """
        import os

        for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY",
                     "http_proxy", "ALL_PROXY", "all_proxy"):
            val = os.environ.get(var)
            if val:
                return val
        return None
