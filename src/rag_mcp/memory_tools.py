"""MCP tools for cross-session memory management (recall/remember)."""

from __future__ import annotations

from rag_mcp._app import Context, get_app_context, init_config, mcp
from rag_mcp.formatting import DetailLevel, format_results
from rag_mcp.memory import VALID_CATEGORIES

_prefix = init_config.effective_server_name.replace("-", "_")


@mcp.tool(name=f"{_prefix}_recall", output_schema=None)
async def recall(
    ctx: Context,
    query: str,
    category: str = "",
    top_k: int = 5,
    detail_level: str = "L1",
) -> str:
    """Recall relevant memories from past sessions.

    Use at session start to check for relevant context, or when
    the user asks "do you remember...". Returns memories ranked
    by relevance to the query.

    Args:
        query: What to recall — task context, topic, or question.
        category: Filter by category: preference, decision,
            learning, correction, context, workflow (optional).
        top_k: Maximum number of memories to return.
        detail_level: Content detail tier — "L0" (one-line abstract),
            "L1" (overview, default), or "L2" (full content). When OV
            has auto_generate_l0/l1 enabled, uses VLM summaries;
            otherwise extractive fallback. PNG wrap only at L2.
    """
    app = get_app_context(ctx)

    if app.memory is None:
        return "Memory is disabled (RAG_MCP_MEMORY_BACKEND=none)."

    if category and category not in VALID_CATEGORIES:
        cats = ", ".join(sorted(VALID_CATEGORIES))
        return f'Unknown category "{category}". Valid: {cats}'

    effective_level: DetailLevel = _resolve_detail_level(
        detail_level, app.config.tiered_retrieval, app.config.default_detail_level
    )

    session_id = getattr(ctx, "client_id", "") or ""

    memories = await app.memory.recall(
        query,
        category=category,
        top_k=top_k,
        embeddings=app.embeddings,
        detail_level=effective_level,
        session_id=session_id,
    )

    if not memories:
        hint = f' in category "{category}"' if category else ""
        return f"No memories found for \"{query}\"{hint}."

    results = _memories_to_results(memories)
    budget = app.config.max_response_chars

    if app.config.png_wrap and effective_level == "L2":
        from rag_mcp.png_wrap import wrap_as_images
        budget = app.config.png_max_chars_per_store
        formatted = format_results(results, budget, detail_level=effective_level)
        return wrap_as_images(formatted, max_pages=app.config.png_max_pages)

    return format_results(results, budget, detail_level=effective_level)


def _memories_to_results(memories: list[dict]) -> list[dict]:
    """Convert memory dicts to the result format expected by format_results."""
    results = []
    for mem in memories:
        cat = mem.get("category", "context")
        saved = mem.get("saved_at", "unknown")
        text = (
            mem.get("content")
            or mem.get("l1_summary")
            or mem.get("l0_summary")
            or ""
        )
        results.append({
            "text": text,
            "source": f"memory/{cat}/{saved}",
            "metadata": {
                "title": f"Memory [{cat}] — {saved}",
                "l0_summary": mem.get("l0_summary"),
                "l1_summary": mem.get("l1_summary"),
            },
            "score": mem.get("score"),
        })
    return results


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


@mcp.tool(name=f"{_prefix}_remember", output_schema=None)
async def remember(
    ctx: Context,
    content: str,
    category: str = "context",
) -> str:
    """Save a memory for future sessions.

    Call when the user states a preference, makes a significant
    decision, or when you learn something useful for future sessions.
    For workflows, include the sequence of steps, tools used, inputs,
    and success criteria.

    Args:
        content: What to remember — be specific and concise.
        category: One of: preference, decision, learning,
            correction, context, workflow. Defaults to context.
    """
    app = get_app_context(ctx)

    if app.memory is None:
        return "Memory is disabled (RAG_MCP_MEMORY_BACKEND=none)."

    if category not in VALID_CATEGORIES:
        cats = ", ".join(sorted(VALID_CATEGORIES))
        return f'Unknown category "{category}". Valid: {cats}'

    if not content.strip():
        return "Cannot save empty memory."

    result = await app.memory.remember(content.strip(), category=category)

    if result.get("deduplicated"):
        return (
            f"Memory already exists at `{result['uri']}` "
            f"(category: {result['category']}). Skipped duplicate."
        )

    if result.get("error"):
        return f"Failed to save memory: {result['error']}"

    return (
        f"Memory saved.\n"
        f"- **URI**: `{result['uri']}`\n"
        f"- **Category**: {result['category']}\n"
        f"- **Saved at**: {result['saved_at']}"
    )
