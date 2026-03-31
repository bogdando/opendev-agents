"""MCP tools and resources for the RAG knowledge server."""

from __future__ import annotations

from fastmcp import Context

from rag_mcp.formatting import format_results
from rag_mcp.server import get_app_context, mcp


@mcp.tool
async def search(
    ctx: Context,
    query: str,
    vector_store_id: str = "",
    top_k: int = 5,
) -> str:
    """Search a knowledge base for relevant documentation.

    Returns formatted markdown with source attribution that can be
    injected directly into the conversation context.

    Args:
        query: Natural language search query.
        vector_store_id: ID of the knowledge store to search.
                         Leave empty to search the first available store.
        top_k: Maximum number of results to return.
    """
    app = get_app_context(ctx)

    if not vector_store_id:
        stores = await app.backend.list_stores()
        if not stores:
            return "No knowledge stores available."
        vector_store_id = stores[0]["id"]

    results = await app.backend.search(query, vector_store_id, top_k)
    return format_results(results, app.config.max_response_chars)


@mcp.resource("knowledge://stores")
async def list_knowledge_stores(ctx: Context) -> str:
    """List all available knowledge stores and their metadata."""
    app = get_app_context(ctx)
    stores = await app.backend.list_stores()

    if not stores:
        return "No knowledge stores configured."

    lines: list[str] = ["# Available Knowledge Stores\n"]
    for s in stores:
        lines.append(f"## {s['name']}")
        lines.append(f"- **Store ID**: `{s['id']}`")
        lines.append(f"- **Documents**: {s['doc_count']}")
        lines.append(f"- **Last updated**: {s['last_updated']}")
        lines.append(f"- {s['description']}")
        lines.append("")
    return "\n".join(lines)


@mcp.resource("knowledge://{store_id}")
async def get_knowledge_store(store_id: str, ctx: Context) -> str:
    """Get metadata for a specific knowledge store."""
    app = get_app_context(ctx)
    store = await app.backend.get_store(store_id)

    if store is None:
        return f"Knowledge store '{store_id}' not found."

    return (
        f"# {store['name']}\n\n"
        f"- **Store ID**: `{store['id']}`\n"
        f"- **Documents**: {store['doc_count']}\n"
        f"- **Last updated**: {store['last_updated']}\n"
        f"- {store['description']}\n"
    )
