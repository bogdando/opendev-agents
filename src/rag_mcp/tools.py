"""MCP tools and resources for the RAG knowledge server."""

from __future__ import annotations

from pathlib import Path

from rag_mcp._app import Context, get_app_context, init_config, mcp
from rag_mcp.constants import SEARCH_STOP_WORDS
from rag_mcp.formatting import DetailLevel, format_results
from rag_mcp.sidecars import (
    CacheSidecarManager,
    SidecarManager,
    needs_l0,
    needs_l1,
)

_search_name = f"{init_config.effective_server_name.replace('-', '_')}_search"


@mcp.tool(name=_search_name)
async def search(
    ctx: Context,
    query: str,
    vector_store_id: str,
    top_k: int = 5,
    detail_level: str = "L1",
):
    """Search a knowledge base for relevant documentation.

    Returns formatted markdown with source attribution that can be
    injected directly into the conversation context.  When PNG wrap
    mode is enabled (RAG_MCP_PNG_WRAP=true) and detail_level is "L2",
    results are returned as 1568x1568 PNG image frames for dense
    context transfer.

    When PNG wrap is active, results from each store are capped at
    RAG_MCP_PNG_MAX_CHARS_PER_STORE characters (default 4500) to
    control vision-token cost per call.  Search multiple stores in
    separate calls to gather broader context across sources.

    When no results are found, returns recovery hints with suggested
    broader terms and alternative stores.

    Args:
        query: Natural language search query.
        vector_store_id: ID of the knowledge store to search
            (required).  Read the ``knowledge://stores`` resource
            first to discover available store IDs.
        top_k: Maximum number of results to return.
        detail_level: Content detail tier — "L0" (one-line abstract),
            "L1" (overview paragraph, default), or "L2" (full content).
            L0/L1 use cached summaries or extractive fallback. PNG wrap
            only applies at L2.
    """
    app = get_app_context(ctx)

    effective_level: DetailLevel = _resolve_detail_level(
        detail_level, app.config.tiered_retrieval, app.config.default_detail_level
    )

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

    results = await app.backend.search(
        query, vector_store_id, top_k, embeddings=app.embeddings,
    )

    if results:
        if app.config.tiered_retrieval and effective_level != "L2":
            _enrich_with_sidecars(results, vector_store_id, app)

        if app.config.png_wrap and effective_level == "L2":
            from rag_mcp.png_wrap import wrap_as_images
            budget = app.config.png_max_chars_per_store
        else:
            budget = app.config.max_response_chars

        formatted = format_results(results, budget, detail_level=effective_level)
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
        if app.config.png_wrap and effective_level == "L2":
            return wrap_as_images(formatted, max_pages=app.config.png_max_pages)
        return formatted

    return _build_recovery_hints(query, vector_store_id, stores)


def _resolve_detail_level(
    requested: str,
    tiered_enabled: bool,
    default: str,
) -> DetailLevel:
    """Normalize the detail_level parameter."""
    if not tiered_enabled:
        return "L2"
    level = requested.upper()
    if level in ("L0", "L1", "L2"):
        return level  # type: ignore[return-value]
    return default.upper()  # type: ignore[return-value]


def _enrich_with_sidecars(
    results: list[dict],
    store_id: str,
    app,
) -> None:
    """Attach sidecar summaries to results and schedule generation if missing."""
    from rag_mcp._app import AppContext
    app: AppContext  # type: ignore[no-redef]

    if app.config.backend == "mock":
        store_dir = Path(app.config.knowledge_dir) / store_id
        if not store_dir.is_dir():
            return
        summaries_path = (
            Path(app.config.summaries_dir)
            if app.config.summaries_dir != ".summaries-cache"
            else None
        )
        mgr = SidecarManager(store_dir, summaries_path)
        for r in results:
            source = r.get("source", "")
            if not source:
                continue
            file_path = Path(source)
            if not file_path.is_file():
                file_path = store_dir / source
            if not file_path.is_file():
                continue
            l0 = mgr.get_l0(file_path)
            l1 = mgr.get_l1(file_path)
            r.setdefault("metadata", {})
            if l0:
                r["metadata"]["l0_summary"] = l0
            if l1:
                r["metadata"]["l1_summary"] = l1
            if (not l0 or not l1) and app.bg_summarizer:
                text = r.get("text", "")
                file_key = str(file_path)
                if (not l0 and needs_l0(text)) or (not l1 and needs_l1(text)):
                    _schedule_sidecar_generation(
                        app, mgr, file_path, text, file_key
                    )
    else:
        cache_dir = Path(app.config.summaries_dir)
        cache_mgr = CacheSidecarManager(cache_dir)
        for r in results:
            doc_id = r.get("metadata", {}).get("doc_id", r.get("source", ""))
            if not doc_id:
                continue
            l0 = cache_mgr.get_l0(doc_id)
            l1 = cache_mgr.get_l1(doc_id)
            r.setdefault("metadata", {})
            if l0:
                r["metadata"]["l0_summary"] = l0
            if l1:
                r["metadata"]["l1_summary"] = l1
            if (not l0 or not l1) and app.bg_summarizer:
                text = r.get("text", "")
                if (not l0 and needs_l0(text)) or (not l1 and needs_l1(text)):
                    _schedule_cache_generation(app, cache_mgr, doc_id, text)


def _schedule_sidecar_generation(app, mgr: SidecarManager, file_path: Path, text: str, file_key: str) -> None:
    """Wire background summarizer to persist sidecars for mock backend."""
    from rag_mcp.summarizer import BackgroundSummarizer, Summarizer

    summarizer_url = app.config.effective_summarizer_url
    if not summarizer_url:
        return

    async def on_complete(key: str, l0: str | None, l1: str | None) -> None:
        mgr.write_sidecars(Path(key), text, l0, l1)

    bg = BackgroundSummarizer(
        Summarizer(summarizer_url, app.config.summarizer_model),
        on_complete,
    )
    bg.schedule(file_key, text)


def _schedule_cache_generation(app, cache_mgr: CacheSidecarManager, doc_id: str, text: str) -> None:
    """Wire background summarizer to persist cache for solr/confluence."""
    from rag_mcp.summarizer import BackgroundSummarizer, Summarizer

    summarizer_url = app.config.effective_summarizer_url
    if not summarizer_url:
        return

    async def on_complete(key: str, l0: str | None, l1: str | None) -> None:
        cache_mgr.write(key, l0, l1)

    bg = BackgroundSummarizer(
        Summarizer(summarizer_url, app.config.summarizer_model),
        on_complete,
    )
    bg.schedule(doc_id, text)


def _find_unmatched_terms(
    query: str, results: list[dict]
) -> list[str]:
    """Return query terms absent from every result text.

    Filters out common stop words so the hint only flags
    topical terms that genuinely have no coverage.
    """
    terms = [
        t for t in query.lower().split()
        if t not in SEARCH_STOP_WORDS and len(t) > 2
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
    store to inspect or search.  Also includes the search tool
    name so consumers know exactly what to call.
    """
    app = get_app_context(ctx)
    stores = await app.backend.list_stores()

    if not stores:
        return "No knowledge stores configured."

    lines: list[str] = [
        "# Available Knowledge Stores\n",
        f"**Search tool**: `{_search_name}`\n",
    ]
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
