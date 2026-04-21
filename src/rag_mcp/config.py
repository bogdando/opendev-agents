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
    CONFLUENCEURL, CONFLUENCEEMAIL, CONFLUENCETOKEN, CONFLUENCEAUTH,
    CONFLUENCECLOUDID, CONFLUENCESPACE.
    When both are set, the short name wins.
    """

    model_config = SettingsConfigDict(env_prefix="RAG_MCP_")

    transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

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
    confluence_auth: Literal["basic", "oauth"] = Field(
        default="oauth",
        validation_alias=AliasChoices(
            "CONFLUENCEAUTH",
            "RAG_MCP_CONFLUENCE_AUTH",
        ),
    )
    confluence_cloud_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CONFLUENCECLOUDID",
            "RAG_MCP_CONFLUENCE_CLOUD_ID",
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
