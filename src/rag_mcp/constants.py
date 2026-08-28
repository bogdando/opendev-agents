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

# Threshold for suppressing the keyword fallback: only results with
# near-exact keyword coverage *and* a lead-window match prevent the
# BM25 scan. A citing document that quotes the query later in the body
# must not suppress the true gold.
EXACT_MATCH_COVERAGE = 0.8

# Characters at the start of a document used to decide whether the
# query is the subject (gold) vs a citation later in the body.
LEAD_MATCH_CHARS = 160

# Cap on memories scanned by keyword fallback after date filtering.
# Date windows apply *before* this slice so an older gold in a tight
# window is not displaced by newer files. Unfiltered recall only sees
# this many newest files — narrow with saved_after/saved_before.
KEYWORD_FALLBACK_LIST_LIMIT = 200
