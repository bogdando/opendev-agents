"""Format RAG search results into markdown strings."""

from __future__ import annotations

_SEPARATOR = "\n\n---\n\n"
_BUDGET_MARKER = "\n\n[Budget reached — additional results omitted]"


def format_results(results: list[dict], max_chars: int) -> str:
    """Render *results* as a markdown string within *max_chars* budget.

    Each result dict is expected to have ``text``, ``source``, and
    ``metadata`` (with at least ``title``).
    """
    if not results:
        return "No results found."

    parts: list[str] = []
    used = 0

    for r in results:
        title = r.get("metadata", {}).get("title", "Untitled")
        source = r.get("source", "unknown")
        text = r.get("text", "")

        entry = f"## {title}\n\n{text}\n\n**Source**: {source}"
        entry_len = len(entry) + len(_SEPARATOR)

        if used + entry_len > max_chars and parts:
            parts.append(_BUDGET_MARKER.lstrip("\n"))
            break

        parts.append(entry)
        used += entry_len

    return _SEPARATOR.join(parts)
