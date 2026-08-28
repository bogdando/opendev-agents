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

# Minimum keyword overlap for a fallback result to be accepted.
MIN_KEYWORD_COVERAGE = 0.5

# Near-exact keyword coverage used by the mock search BM25 swap.
EXACT_MATCH_COVERAGE = 0.8

# Fraction of top_k reserved for the dedicated BM25 holder when
# merging into the semantic pool (70/30). Semantic keeps the rest.
BM25_MERGE_RATIO = 0.3

# Characters at the start of a document used to decide whether the
# query is the subject (gold) vs a citation later in the body.
LEAD_MATCH_CHARS = 160

# Cap on memories scanned by keyword fallback after date filtering.
# Date windows apply *before* this slice so an older gold in a tight
# window is not displaced by newer files. Unfiltered recall only sees
# this many newest files — narrow with saved_after/saved_before.
KEYWORD_FALLBACK_LIST_LIMIT = 200
