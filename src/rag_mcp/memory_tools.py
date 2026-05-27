"""MCP tools for cross-session memory management (recall/remember)."""

from __future__ import annotations

from fastmcp import Context

from rag_mcp.memory import VALID_CATEGORIES
from rag_mcp.server import get_app_context, mcp


@mcp.tool
async def recall(
    ctx: Context,
    query: str,
    category: str = "",
    top_k: int = 5,
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
    """
    app = get_app_context(ctx)

    if app.memory is None:
        return "Memory is disabled (RAG_MCP_MEMORY_BACKEND=none)."

    if category and category not in VALID_CATEGORIES:
        cats = ", ".join(sorted(VALID_CATEGORIES))
        return f'Unknown category "{category}". Valid: {cats}'

    memories = await app.memory.recall(query, category=category, top_k=top_k)

    if not memories:
        hint = f' in category "{category}"' if category else ""
        return f"No memories found for \"{query}\"{hint}."

    lines: list[str] = ["# Recalled Memories\n"]
    for i, mem in enumerate(memories, 1):
        saved = mem.get("saved_at", "unknown time")
        cat = mem.get("category", "context")
        content = mem.get("content", "")
        lines.append(f"## Memory {i} [{cat}]")
        lines.append(f"*Saved: {saved}*\n")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


@mcp.tool
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
