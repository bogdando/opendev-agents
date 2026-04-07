"""MCP tools and resources for the RAG knowledge server."""

from __future__ import annotations

from fastmcp import Context

from rag_mcp.formatting import format_results
from rag_mcp.server import get_app_context, mcp


@mcp.tool
async def search(
    ctx: Context,
    query: str,
    vector_store_id: str,
    top_k: int = 5,
) -> str:
    """Search a knowledge base for relevant documentation.

    Returns formatted markdown with source attribution that can be
    injected directly into the conversation context.  When no results
    are found, returns recovery hints with suggested broader terms
    and alternative stores.

    Args:
        query: Natural language search query.
        vector_store_id: ID of the knowledge store to search
            (required).  Read the ``knowledge://stores`` resource
            first to discover available store IDs.
        top_k: Maximum number of results to return.
    """
    app = get_app_context(ctx)

    stores = await app.backend.list_stores()
    if not stores:
        return "No knowledge stores available."

    store_ids = [s["id"] for s in stores]
    if vector_store_id not in store_ids:
        return (
            f"Unknown store \"{vector_store_id}\". "
            f"Available stores: {', '.join(store_ids)}. "
            "Read resource knowledge://stores for details."
        )

    results = await app.backend.search(query, vector_store_id, top_k)

    if results:
        formatted = format_results(
            results, app.config.max_response_chars
        )
        unmatched = _find_unmatched_terms(query, results)
        if unmatched:
            terms = ", ".join(f'"{t}"' for t in unmatched)
            formatted += (
                "\n\n---\n\n"
                "**Note**: No documents in store "
                f'"{vector_store_id}" mention {terms}.'
                " Results above matched only the"
                " other query terms."
            )
        return formatted

    return _build_recovery_hints(query, vector_store_id, stores)


# Short words unlikely to be meaningful query terms.
_STOP_WORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "to", "of",
    "is", "it", "do", "or", "by", "as", "if", "be",
    "so", "no", "up", "my", "we", "he",
    "how", "who", "what", "when", "where", "why",
    "and", "but", "for", "not", "are", "was", "has",
    "can", "did", "its", "our", "had", "may", "all",
})


def _find_unmatched_terms(
    query: str, results: list[dict]
) -> list[str]:
    """Return query terms absent from every result text.

    Filters out common stop words so the hint only flags
    topical terms that genuinely have no coverage.
    """
    terms = [
        t for t in query.lower().split()
        if t not in _STOP_WORDS and len(t) > 2
    ]
    if len(terms) <= 1:
        return []
    combined = " ".join(
        r.get("text", "").lower() for r in results
    )
    return [t for t in terms if t not in combined]


def _build_recovery_hints(
    query: str, searched_store: str, all_stores: list[dict]
) -> str:
    """Build a recovery-hint response when search returns no results."""
    keywords = query.split()
    lines = [
        f'No results found for "{query}" in store "{searched_store}".',
        "",
        "**Suggestions**:",
    ]

    if len(keywords) > 1:
        broader = ", ".join(f'"{kw}"' for kw in keywords)
        lines.append(f"- Try broader terms: {broader}")

    other_stores = [s for s in all_stores if s["id"] != searched_store]
    for s in other_stores:
        lines.append(f"- Try a different store: \"{s['id']}\" - {s['description']}")

    store_ids = [s["id"] for s in all_stores]
    lines.append(f"- Available stores: {', '.join(store_ids)}")

    return "\n".join(lines)


@mcp.resource("knowledge://stores")
async def list_knowledge_stores(ctx: Context) -> str:
    """List all available knowledge stores (compact catalog).

    Level 1 of progressive discovery: returns store IDs, names,
    access level, and freshness so the agent can decide which
    store to inspect or search.
    """
    app = get_app_context(ctx)
    stores = await app.backend.list_stores()

    if not stores:
        return "No knowledge stores configured."

    lines: list[str] = ["# Available Knowledge Stores\n"]
    for s in stores:
        lines.append(f"## {s['name']}")
        lines.append(f"- **Store ID**: `{s['id']}`")
        lines.append(f"- **Access**: {s.get('access', 'unknown')}")
        lines.append(f"- **Freshness**: {s.get('freshness', s.get('last_updated', 'unknown'))}")
        lines.append(f"- **Documents**: {s['doc_count']}")
        lines.append(f"- {s['description']}")
        lines.append("")
    return "\n".join(lines)


@mcp.resource("knowledge://{store_id}")
async def get_knowledge_store(store_id: str, ctx: Context) -> str:
    """Get full metadata for a specific knowledge store.

    Level 2 of progressive discovery: returns domain coverage,
    corpus freshness, access level, and document count so the
    agent can decide whether this store is relevant for the task.
    """
    app = get_app_context(ctx)
    store = await app.backend.get_store(store_id)

    if store is None:
        return f"Knowledge store '{store_id}' not found."

    coverage = store.get("coverage", [])
    coverage_str = ", ".join(coverage) if coverage else "not specified"

    return (
        f"# {store['name']}\n\n"
        f"- **Store ID**: `{store['id']}`\n"
        f"- **Access**: {store.get('access', 'unknown')}\n"
        f"- **Freshness**: {store.get('freshness', store.get('last_updated', 'unknown'))}\n"
        f"- **Documents**: {store['doc_count']}\n"
        f"- **Coverage**: {coverage_str}\n"
        f"- {store['description']}\n"
    )
