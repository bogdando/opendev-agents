"""Format RAG search results into markdown strings.

Supports tiered rendering (L0/L1/L2) when results carry sidecar
summaries or when extractive approximation is needed.

Implements compression gain check: if a summary (L0/L1) provides no
compression gain compared to the original (size >= original), falls back
to returning the original instead.
"""

from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

_SEPARATOR = "\n\n---\n\n"
_BUDGET_MARKER = "\n\n[Budget reached — additional results omitted]"

DetailLevel = Literal["L0", "L1", "L2"]

_L0_MAX_TOKENS = 100
_L1_MAX_CHARS = 2000


def _has_compression_gain(summary: str, original: str) -> bool:
    """Check if summary provides compression gain over original.
    
    Returns True if summary is shorter than original (has compression gain).
    Returns False if summary is equal to or longer than original (no gain).
    
    Uses character count for simplicity; can be enhanced with tokenizer later.
    """
    if not summary or not original:
        return False
    return len(summary) < len(original)


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
        content_id = r.get("id", r.get("source", "unknown"))

        content = _select_content(full_text, metadata, detail_level, content_id)

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
    full_text: str, metadata: dict, detail_level: DetailLevel,
    content_id: str = ""
) -> str:
    """Pick the right content tier from sidecars or extractive fallback.
    
    Implements compression gain check: if a summary (L0/L1) provides no
    compression gain (size >= original), falls back to returning the
    original full text instead.
    
    Args:
        full_text: Original full content (L2)
        metadata: Result metadata dict with optional l0_summary, l1_summary
        detail_level: Requested detail level (L0, L1, L2)
        content_id: Optional content identifier for logging
    
    Returns:
        Selected content at appropriate detail level or original if no gain.
    """
    if detail_level == "L0":
        l0_summary = metadata.get("l0_summary")
        if l0_summary:
            if _has_compression_gain(l0_summary, full_text):
                return l0_summary
            else:
                # No compression gain — prefer original
                logger.debug(
                    "compression_no_gain",
                    extra={
                        "content_id": content_id,
                        "level": "L0",
                        "l0_chars": len(l0_summary),
                        "original_chars": len(full_text),
                        "ratio": len(l0_summary) / len(full_text) if full_text else 0,
                    }
                )
                return full_text
        return _extract_first_sentence(full_text)

    if detail_level == "L1":
        l1_summary = metadata.get("l1_summary")
        if l1_summary:
            if _has_compression_gain(l1_summary, full_text):
                return l1_summary
            else:
                # No compression gain — prefer original
                logger.debug(
                    "compression_no_gain",
                    extra={
                        "content_id": content_id,
                        "level": "L1",
                        "l1_chars": len(l1_summary),
                        "original_chars": len(full_text),
                        "ratio": len(l1_summary) / len(full_text) if full_text else 0,
                    }
                )
                return full_text
        return _extract_l1(full_text)

    # L2: always return original
    return full_text
