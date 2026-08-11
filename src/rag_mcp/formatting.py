"""Format RAG search results into markdown strings.

Supports tiered rendering (L0/L1/L2) when results carry sidecar
summaries or when extractive approximation is needed.
"""

from __future__ import annotations

from typing import Literal

_SEPARATOR = "\n\n---\n\n"
_BUDGET_MARKER = "\n\n[Budget reached — additional results omitted]"

DetailLevel = Literal["L0", "L1", "L2"]

_L0_MAX_TOKENS = 100
_L1_MAX_CHARS = 2000


def _extract_first_sentence(text: str) -> str:
    """Return title + first sentence as an L0 extractive approximation."""
    for end in (".\n", ". ", ".\t"):
        idx = text.find(end)
        if idx != -1:
            return text[: idx + 1]
    return text[:150]


def _extract_l1(text: str) -> str:
    """Return first 2000 chars as an L1 extractive approximation."""
    if len(text) <= _L1_MAX_CHARS:
        return text
    cut = text[:_L1_MAX_CHARS]
    last_newline = cut.rfind("\n")
    if last_newline > _L1_MAX_CHARS // 2:
        return cut[:last_newline]
    return cut


def format_results(
    results: list[dict],
    max_chars: int,
    detail_level: DetailLevel = "L2",
) -> str:
    """Render *results* as a markdown string within *max_chars* budget.

    Each result dict is expected to have ``text``, ``source``, and
    ``metadata`` (with at least ``title``).

    When *detail_level* is L0 or L1, the formatter uses sidecar summaries
    (``metadata.l0_summary`` / ``metadata.l1_summary``) if present, else
    falls back to extractive approximation from the full text.
    """
    if not results:
        return "No results found."

    parts: list[str] = []
    used = 0

    for r in results:
        title = r.get("metadata", {}).get("title", "Untitled")
        source = r.get("source", "unknown")
        full_text = r.get("text", "")
        score = r.get("score")
        metadata = r.get("metadata", {})

        content = _select_content(full_text, metadata, detail_level)

        header = f"## {title}"
        if score is not None:
            header += f"  (relevance: {score:.2f})"

        if detail_level == "L0":
            entry = f"- **{title}**: {content}"
        else:
            entry = f"{header}\n\n{content}\n\n**Source**: {source}"

        entry_len = len(entry) + len(_SEPARATOR)

        if used + entry_len > max_chars and parts:
            parts.append(_BUDGET_MARKER.lstrip("\n"))
            break

        parts.append(entry)
        used += entry_len

    if detail_level == "L0":
        return "\n".join(parts)
    return _SEPARATOR.join(parts)


def _select_content(
    full_text: str, metadata: dict, detail_level: DetailLevel
) -> str:
    """Pick the right content tier from sidecars or extractive fallback."""
    if detail_level == "L0":
        if metadata.get("l0_summary"):
            return metadata["l0_summary"]
        return _extract_first_sentence(full_text)

    if detail_level == "L1":
        if metadata.get("l1_summary"):
            return metadata["l1_summary"]
        return _extract_l1(full_text)

    return full_text
