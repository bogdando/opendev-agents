"""Tests for summarizer output sanitization (knowledge-RAG path).

Covers the reasoning-model chain-of-thought leak: models that ignore
the sentinel prompt emit planning prose ("I'll structure the summary
clearly: ...") with no think tags at all, which the original strip
(rsplit on the closing tag only) passed through verbatim into L0/L1
sidecar summaries.
"""

from __future__ import annotations

import asyncio
import unittest

from rag_mcp.summarizer import (
    _DIRECT_ANSWER_LABEL,
    _THINK_CLOSE,
    _THINK_OPEN,
    BackgroundSummarizer,
    Summarizer,
    strip_meta_preamble,
    strip_thinking,
)

# The exact untagged leak observed from granite-style models:
# planning prose followed by the actual summary.
_REPORTED_LEAK = (
    "I'll structure the summary clearly: brief intro, configuration "
    "steps, deployment, verification. Keep it factual without "
    "markdown, under 500 words.\n\n"
    "This document provides a solution for configuring Nova Placement "
    "in Red Hat OpenStack Platform (RHOSP) to enable cluster "
    "administrators to dynamically adjust CPU ..."
)
_REPORTED_CLEAN = (
    "This document provides a solution for configuring Nova Placement "
    "in Red Hat OpenStack Platform (RHOSP) to enable cluster "
    "administrators to dynamically adjust CPU ..."
)


class TestStripMetaPreamble(unittest.TestCase):
    """Leading meta-planning sentences are dropped; content kept."""

    def test_reported_leak_is_stripped(self):
        """The exact untagged leak: planning sentences removed."""
        self.assertEqual(
            strip_meta_preamble(_REPORTED_LEAK), _REPORTED_CLEAN
        )

    def test_l0_style_planning_preamble(self):
        """L0-style leak ("We need to produce a single sentence...")
        seen from small models is dropped."""
        content = (
            "We need to produce a single sentence summary (max 100 "
            "tokens). Let's craft one now.\n\n"
            "Nova uses the placement service to track inventories."
        )
        self.assertEqual(
            strip_meta_preamble(content),
            "Nova uses the placement service to track inventories.",
        )

    def test_stops_at_first_content_sentence(self):
        """Only leading sentences are considered: meta-styled phrases
        mid-text are legitimate content and preserved verbatim."""
        content = (
            "The document covers EDPM node deployment. "
            "I will not summarize the appendix."
        )
        self.assertEqual(strip_meta_preamble(content), content)

    def test_clean_summary_unchanged(self):
        """A clean summary passes through untouched."""
        content = "Nova scheduling filters determine host placement."
        self.assertEqual(strip_meta_preamble(content), content)

    def test_all_meta_returns_empty(self):
        """Pure planning output sanitizes to an empty string."""
        content = "I'll think about it. Let me plan the structure."
        self.assertEqual(strip_meta_preamble(content), "")

    def test_empty_input_round_trips(self):
        """Empty and whitespace-only input round-trips."""
        self.assertEqual(strip_meta_preamble(""), "")
        self.assertEqual(strip_meta_preamble("  \n "), "")


class TestStripThinkingUntaggedLeak(unittest.TestCase):
    """strip_thinking handles output without any think tags."""

    def test_reported_leak_no_tags(self):
        """The reported failure: no closing tag present, so the old
        rsplit never fired and the preamble got persisted."""
        self.assertEqual(strip_thinking(_REPORTED_LEAK), _REPORTED_CLEAN)

    def test_tagged_output_still_stripped(self):
        """Regression: closed think blocks keep text after last close."""
        content = (
            f"{_THINK_OPEN}>Let me analyze the document. {_THINK_CLOSE}\n"
            "The document describes Nova scheduling filters."
        )
        self.assertEqual(
            strip_thinking(content),
            "The document describes Nova scheduling filters.",
        )

    def test_closed_tag_with_leaked_preamble_after(self):
        """Preamble leaked after the close tag is also removed."""
        content = (
            f"{_THINK_OPEN}>reasoning{_THINK_CLOSE}\n\n"
            "I'll keep it short. Nova placement tracks inventories."
        )
        self.assertEqual(
            strip_thinking(content),
            "Nova placement tracks inventories.",
        )

    def test_unclosed_think_block(self):
        """An unclosed block: keep the trailing segment, drop the tag
        and any leading planning prose."""
        content = (
            f"{_THINK_OPEN}>Let me plan the answer. "
            "The placement service tracks inventories."
        )
        self.assertEqual(
            strip_thinking(content),
            "The placement service tracks inventories.",
        )

    def test_truncated_sentinel_prefix(self):
        """Model emitted the opening half of the sentinel (label
        without the closing tag) followed by the answer."""
        content = (
            f"{_THINK_OPEN}>{_DIRECT_ANSWER_LABEL}\n\n"
            "This document provides a solution for configuring Nova "
            "Placement."
        )
        self.assertEqual(
            strip_thinking(content),
            "This document provides a solution for configuring Nova "
            "Placement.",
        )

    def test_plain_text_unchanged(self):
        """Non-reasoning output passes through unchanged."""
        content = "Nova scheduling filters determine host placement."
        self.assertEqual(strip_thinking(content), content)


class _FakeChatResponse:
    """Minimal httpx.Response stand-in for the chat endpoint."""

    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeChatClient:
    """Async httpx client stub returning a canned completion."""

    def __init__(self, content):
        self._content = content
        self.calls = 0

    async def post(self, url, json):
        self.calls += 1
        return _FakeChatResponse(self._content)


class TestChatSanitizesLeakedPreamble(unittest.TestCase):
    """Knowledge-RAG path: Summarizer._chat sanitizes untagged leaks."""

    def test_untagged_preamble_removed(self):
        """A completion with no tags and leaked planning prose returns
        only the clean summary text."""
        s = Summarizer("http://localhost:8000", "granite")
        s._client = _FakeChatClient(_REPORTED_LEAK)

        answer = asyncio.run(s.generate_l1("long document text"))
        self.assertEqual(answer, _REPORTED_CLEAN)

    def test_pure_preamble_returns_none(self):
        """A completion that is entirely planning prose yields None so
        sidecars are not written with empty summaries."""
        s = Summarizer("http://localhost:8000", "granite")
        s._client = _FakeChatClient(
            "I'll think about the structure. Let me plan it."
        )

        self.assertIsNone(asyncio.run(s.generate_l1("document text")))


class TestBackgroundSummarizerCleanOutput(unittest.TestCase):
    """Knowledge-RAG path end-to-end: leaked preambles never reach the
    sidecar persistence callback."""

    def test_on_complete_receives_sanitized_summaries(self):
        """Both L0 and L1 completions are sanitized before the
        persistence callback fires."""
        captured = {}

        s = Summarizer("http://localhost:8000", "granite")
        s._client = _FakeChatClient(_REPORTED_LEAK)

        async def on_complete(key, l0, l1):
            captured.update(key=key, l0=l0, l1=l1)

        bg = BackgroundSummarizer(s, on_complete)

        async def run():
            bg.schedule("docs/x.md", "word " * 300)
            while bg.pending_count:
                await asyncio.sleep(0.01)

        asyncio.run(run())

        self.assertEqual(captured["key"], "docs/x.md")
        self.assertEqual(captured["l0"], _REPORTED_CLEAN)
        self.assertEqual(captured["l1"], _REPORTED_CLEAN)


class TestCachedSidecarSanitization(unittest.TestCase):
    """Knowledge-RAG read path: dirty cached sidecars are cleaned."""

    def test_dirty_cached_summary_sanitized(self):
        """Sidecars written before the fix are cleaned on read."""
        from rag_mcp.tools import _sanitize_cached

        dirty = "I'll summarize this now. The real cached summary."
        self.assertEqual(
            _sanitize_cached(dirty), "The real cached summary."
        )

    def test_pure_preamble_treated_as_missing(self):
        """A cache entry that is entirely preamble reads as missing so
        the background summarizer regenerates it."""
        from rag_mcp.tools import _sanitize_cached

        self.assertIsNone(_sanitize_cached("Let me plan. I'll do it."))
        self.assertIsNone(_sanitize_cached(None))
        self.assertIsNone(_sanitize_cached(""))


if __name__ == "__main__":
    unittest.main()
