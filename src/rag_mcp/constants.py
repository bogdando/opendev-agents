"""Shared constants for RAG MCP."""

# Short words unlikely to be meaningful query terms (Confluence CQL, mock
# keyword search, and recovery hints in tools).
SEARCH_STOP_WORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "to", "of",
    "is", "it", "do", "or", "by", "as", "if", "be",
    "so", "no", "up", "my", "we", "he",
    "how", "who", "what", "when", "where", "why",
    "and", "but", "for", "not", "are", "was", "has",
    "can", "did", "its", "our", "had", "may", "all",
})
