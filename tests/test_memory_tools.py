"""Tests for the recall/remember MCP tool layer (memory_tools).

Mirrors the PNG wrap gating tests from test_tools.py (TestSearchPngWrap):
recall() must follow the same contract as search() — PNG frames only
when RAG_MCP_PNG_WRAP is enabled, the effective level is L2, and the
aggregated memory text is large enough to benefit from optical
compression.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from rag_mcp.memory_tools import recall


def _make_memory(content: str, category: str = "context") -> dict:
    """A memory dict as returned by the OV/local backends."""
    return {
        "content": content,
        "category": category,
        "saved_at": "2026-11-12T00:00:00+00:00",
        "uri": f"viking://user/u/memories/{category}/20261112T000000Z.md",
        "score": 0.9,
        "l0_summary": None,
        "l1_summary": None,
    }


class TestRecallPngWrap(unittest.TestCase):
    """PNG wrap gating for recall() mirrors the search() contract."""

    def _run_recall(
        self,
        memories,
        png_wrap=True,
        detail_level="L2",
        tiered_retrieval=True,
    ):
        """Run recall() with a mocked app context and png_wrap module."""
        mock_config = mock.MagicMock()
        mock_config.png_wrap = png_wrap
        mock_config.png_max_pages = 3
        mock_config.png_max_chars_per_store = 4500
        mock_config.max_response_chars = 50000
        mock_config.tiered_retrieval = tiered_retrieval

        fake_memory = mock.AsyncMock()
        fake_memory.recall.return_value = memories

        mock_app = mock.MagicMock()
        mock_app.config = mock_config
        mock_app.memory = fake_memory
        mock_app.session_id = "s1"

        mock_ctx = mock.MagicMock()

        fake_image = mock.MagicMock()
        fake_wrap = mock.MagicMock(return_value=[fake_image])
        fake_png_mod = mock.MagicMock(wrap_as_images=fake_wrap)

        with mock.patch(
            "rag_mcp.memory_tools.get_app_context",
            autospec=True,
            return_value=mock_app,
        ), mock.patch.dict(
            "sys.modules",
            {"rag_mcp.png_wrap": fake_png_mod},
        ):
            out = asyncio.run(
                recall(mock_ctx, "query", detail_level=detail_level)
            )
        return out, fake_wrap

    def test_png_wrap_disabled_returns_text(self):
        """RAG_MCP_PNG_WRAP=false must never wrap, even at L2."""
        memories = [_make_memory("x" * 20000)]
        out, mock_wrap = self._run_recall(memories, png_wrap=False)
        self.assertIsInstance(out, str)
        mock_wrap.assert_not_called()
        self.assertNotIn("skipped visual compression", out)

    def test_png_wrap_disabled_forced_l2_still_text(self):
        """Tiered retrieval off forces L2; a disabled flag still wins."""
        memories = [_make_memory("x" * 20000)]
        out, mock_wrap = self._run_recall(
            memories, png_wrap=False, tiered_retrieval=False,
            detail_level="L0",
        )
        self.assertIsInstance(out, str)
        mock_wrap.assert_not_called()

    def test_large_content_returns_images(self):
        """Aggregated memory text over the threshold wraps as PNG."""
        memories = [_make_memory("x" * 6000)]
        out, mock_wrap = self._run_recall(memories, png_wrap=True)
        self.assertIsInstance(out, list)
        self.assertGreater(len(out), 0)
        mock_wrap.assert_called_once()

    def test_small_content_falls_back_to_raw_text_with_hint(self):
        """Aggregated memory text below the threshold returns text."""
        memories = [_make_memory("some memory content")]
        out, mock_wrap = self._run_recall(memories, png_wrap=True)
        self.assertIsInstance(out, str)
        mock_wrap.assert_not_called()
        self.assertIn(
            "skipped visual compression because of small content", out
        )
        self.assertIn("some memory content", out)

    def test_just_below_threshold_returns_text(self):
        """One char below the threshold still returns raw text."""
        memories = [_make_memory("x" * 5999)]
        out, mock_wrap = self._run_recall(memories, png_wrap=True)
        self.assertIsInstance(out, str)
        mock_wrap.assert_not_called()
        self.assertIn(
            "skipped visual compression because of small content", out
        )

    def test_l0_never_wraps(self):
        """L0 stays plain text regardless of the png_wrap flag."""
        memories = [_make_memory("x" * 20000)]
        out, mock_wrap = self._run_recall(
            memories, png_wrap=True, detail_level="L0"
        )
        self.assertIsInstance(out, str)
        mock_wrap.assert_not_called()

    def test_l1_never_wraps(self):
        """L1 stays plain text regardless of the png_wrap flag."""
        memories = [_make_memory("x" * 20000)]
        out, mock_wrap = self._run_recall(
            memories, png_wrap=True, detail_level="L1"
        )
        self.assertIsInstance(out, str)
        mock_wrap.assert_not_called()

    def test_no_memories_returns_text(self):
        """Empty recall results are plain text even with png_wrap on."""
        out, mock_wrap = self._run_recall([], png_wrap=True)
        self.assertIsInstance(out, str)
        self.assertIn("No memories found", out)
        mock_wrap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
