"""Tests for tiered retrieval: TieredFormatter, sidecars, and detail_level."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rag_mcp.formatting import (
    _extract_first_sentence,
    _extract_l1,
    _select_content,
    format_results,
)
from rag_mcp.sidecars import (
    CacheSidecarManager,
    SidecarManager,
    content_hash,
    needs_l0,
    needs_l1,
)


def _make_result(
    title: str = "Test Title",
    text: str = "This is a full document body with lots of content.",
    source: str = "src.md",
    score: float | None = None,
    l0_summary: str | None = None,
    l1_summary: str | None = None,
) -> dict:
    r: dict = {
        "text": text,
        "source": source,
        "metadata": {"title": title},
    }
    if score is not None:
        r["score"] = score
    if l0_summary is not None:
        r["metadata"]["l0_summary"] = l0_summary
    if l1_summary is not None:
        r["metadata"]["l1_summary"] = l1_summary
    return r


class TestExtractiveApproximation(unittest.TestCase):
    def test_extract_first_sentence_basic(self):
        text = "This is the first sentence. And this is the second."
        result = _extract_first_sentence(text)
        self.assertEqual("This is the first sentence.", result)

    def test_extract_first_sentence_with_newline(self):
        text = "Title line.\nRest of document."
        result = _extract_first_sentence(text)
        self.assertEqual("Title line.", result)

    def test_extract_first_sentence_no_period(self):
        text = "A very short text without periods or breaks"
        result = _extract_first_sentence(text)
        self.assertEqual(text[:150], result)

    def test_extract_l1_short_content(self):
        text = "Short content under limit."
        result = _extract_l1(text)
        self.assertEqual(text, result)

    def test_extract_l1_long_content_cuts_at_newline(self):
        lines = ["Line number " + str(i) for i in range(200)]
        text = "\n".join(lines)
        result = _extract_l1(text)
        self.assertLessEqual(len(result), 2000)
        self.assertTrue(result.endswith("Line number " + str(result.count("\n"))))

    def test_extract_l1_no_good_newline(self):
        text = "x" * 3000
        result = _extract_l1(text)
        self.assertEqual(len(result), 2000)


class TestSelectContent(unittest.TestCase):
    def test_l0_uses_sidecar(self):
        metadata = {"l0_summary": "Concise L0 abstract."}
        result = _select_content("Full text here", metadata, "L0")
        self.assertEqual("Concise L0 abstract.", result)

    def test_l0_falls_back_to_extractive(self):
        result = _select_content("First sentence. More text.", {}, "L0")
        self.assertEqual("First sentence.", result)

    def test_l1_uses_sidecar(self):
        metadata = {"l1_summary": "L1 overview paragraph."}
        result = _select_content("Full text here", metadata, "L1")
        self.assertEqual("L1 overview paragraph.", result)

    def test_l1_falls_back_to_extractive(self):
        text = "x" * 5000
        result = _select_content(text, {}, "L1")
        self.assertLessEqual(len(result), 2000)

    def test_l2_returns_full_text(self):
        full = "Complete document."
        result = _select_content(full, {"l0_summary": "ignored"}, "L2")
        self.assertEqual(full, result)


class TestFormatResultsWithDetailLevel(unittest.TestCase):
    def test_default_is_l2(self):
        out = format_results([_make_result()], 30000)
        self.assertIn("## Test Title", out)
        self.assertIn("**Source**: src.md", out)

    def test_l0_compact_format(self):
        results = [
            _make_result(title="Doc A", l0_summary="Summary A"),
            _make_result(title="Doc B", l0_summary="Summary B"),
        ]
        out = format_results(results, 30000, detail_level="L0")
        self.assertIn("- **Doc A**: Summary A", out)
        self.assertIn("- **Doc B**: Summary B", out)
        self.assertNotIn("---", out)

    def test_l1_has_source_attribution(self):
        results = [_make_result(l1_summary="Overview paragraph.")]
        out = format_results(results, 30000, detail_level="L1")
        self.assertIn("Overview paragraph.", out)
        self.assertIn("**Source**: src.md", out)

    def test_l2_full_content(self):
        text = "Full document with all details."
        results = [_make_result(text=text, l0_summary="Ignored")]
        out = format_results(results, 30000, detail_level="L2")
        self.assertIn(text, out)

    def test_budget_still_applies(self):
        results = [
            _make_result(text="x" * 500, title=f"T{i}") for i in range(20)
        ]
        out = format_results(results, 1200, detail_level="L2")
        self.assertIn("Budget reached", out)


class TestSidecarThresholds(unittest.TestCase):
    def test_needs_l0_short_content(self):
        short = " ".join(["word"] * 50)
        self.assertFalse(needs_l0(short))

    def test_needs_l0_long_content(self):
        long_text = " ".join(["word"] * 200)
        self.assertTrue(needs_l0(long_text))

    def test_needs_l1_short_content(self):
        self.assertFalse(needs_l1("x" * 1000))

    def test_needs_l1_long_content(self):
        self.assertTrue(needs_l1("x" * 3000))


class TestContentHash(unittest.TestCase):
    def test_deterministic(self):
        h1 = content_hash("hello")
        h2 = content_hash("hello")
        self.assertEqual(h1, h2)

    def test_differs_for_different_content(self):
        h1 = content_hash("hello")
        h2 = content_hash("world")
        self.assertNotEqual(h1, h2)

    def test_returns_16_chars(self):
        h = content_hash("test")
        self.assertEqual(len(h), 16)


class TestSidecarManager(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store_dir = Path(self._tmpdir.name) / "store"
        self.store_dir.mkdir()
        self.doc = self.store_dir / "test.md"
        self.doc.write_text("Full document content here.")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_no_sidecars_returns_none(self):
        mgr = SidecarManager(self.store_dir)
        self.assertIsNone(mgr.get_l0(self.doc))
        self.assertIsNone(mgr.get_l1(self.doc))

    def test_write_and_read_sidecars(self):
        mgr = SidecarManager(self.store_dir)
        text = self.doc.read_text()
        mgr.write_sidecars(self.doc, text, "L0 text", "L1 text")

        self.assertEqual(mgr.get_l0(self.doc), "L0 text")
        self.assertEqual(mgr.get_l1(self.doc), "L1 text")

    def test_stale_sidecar_returns_none(self):
        mgr = SidecarManager(self.store_dir)
        text = self.doc.read_text()
        mgr.write_sidecars(self.doc, text, "L0", "L1")

        self.doc.write_text("Modified content!")
        self.assertIsNone(mgr.get_l0(self.doc))
        self.assertIsNone(mgr.get_l1(self.doc))

    def test_stale_sidecar_rebuilt_after_rewrite(self):
        """Non-fresh sidecars are replaced when write_sidecars is called
        with the new content, simulating the background summarizer completing
        after a content change triggers regeneration."""
        mgr = SidecarManager(self.store_dir)
        original = self.doc.read_text()
        mgr.write_sidecars(self.doc, original, "old L0", "old L1")

        new_content = "Completely rewritten document."
        self.doc.write_text(new_content)

        self.assertIsNone(mgr.get_l0(self.doc))
        self.assertIsNone(mgr.get_l1(self.doc))
        self.assertFalse(mgr.is_fresh(self.doc, new_content))

        mgr.write_sidecars(self.doc, new_content, "new L0", "new L1")

        self.assertEqual(mgr.get_l0(self.doc), "new L0")
        self.assertEqual(mgr.get_l1(self.doc), "new L1")
        self.assertTrue(mgr.is_fresh(self.doc, new_content))

    def test_is_fresh(self):
        mgr = SidecarManager(self.store_dir)
        text = self.doc.read_text()
        mgr.write_sidecars(self.doc, text, "L0", "L1")

        self.assertTrue(mgr.is_fresh(self.doc, text))
        self.assertFalse(mgr.is_fresh(self.doc, "different"))

    def test_custom_summaries_dir(self):
        summaries = Path(self._tmpdir.name) / "cache"
        summaries.mkdir()
        mgr = SidecarManager(self.store_dir, summaries)
        text = self.doc.read_text()
        mgr.write_sidecars(self.doc, text, "cached L0", "cached L1")

        self.assertEqual(mgr.get_l0(self.doc), "cached L0")
        self.assertTrue((summaries / "test.md.l0").exists())


class TestCacheSidecarManager(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_no_cache_returns_none(self):
        mgr = CacheSidecarManager(self.cache_dir)
        self.assertIsNone(mgr.get_l0("doc123"))
        self.assertIsNone(mgr.get_l1("doc123"))

    def test_write_and_read(self):
        mgr = CacheSidecarManager(self.cache_dir)
        mgr.write("doc123", "abstract", "overview")

        self.assertEqual(mgr.get_l0("doc123"), "abstract")
        self.assertEqual(mgr.get_l1("doc123"), "overview")

    def test_has_cache(self):
        mgr = CacheSidecarManager(self.cache_dir)
        self.assertFalse(mgr.has_cache("doc456"))
        mgr.write("doc456", "l0", None)
        self.assertTrue(mgr.has_cache("doc456"))

    def test_partial_write(self):
        mgr = CacheSidecarManager(self.cache_dir)
        mgr.write("doc789", None, "just l1")
        self.assertIsNone(mgr.get_l0("doc789"))
        self.assertEqual(mgr.get_l1("doc789"), "just l1")


class TestSummarizer(unittest.TestCase):
    def test_summarizer_instantiation(self):
        from rag_mcp.summarizer import Summarizer
        s = Summarizer("http://localhost:11434", "qwen2.5:7b")
        self.assertEqual(
            s._url, "http://localhost:11434/v1/chat/completions"
        )
        self.assertEqual(s._model, "qwen2.5:7b")

    def test_background_summarizer_deduplicates(self):
        from rag_mcp.summarizer import BackgroundSummarizer, Summarizer

        s = Summarizer("http://localhost:11434", "test")

        async def noop(key, l0, l1):
            pass

        bg = BackgroundSummarizer(s, noop)
        self.assertEqual(bg.pending_count, 0)

    def test_extractive_served_before_sidecars_ready(self):
        """On cold start (no sidecars), format_results returns extractive
        approximations immediately. The summarizer is scheduled in the
        background but the caller already has usable content."""
        long_content = (
            "Nova scheduling filters determine host placement. "
            + "Details follow with more elaboration on the topic. " * 80
        )
        results = [
            {
                "text": long_content,
                "source": "scheduling.md",
                "metadata": {"title": "Scheduling"},
            }
        ]

        out_l0 = format_results(results, 30000, detail_level="L0")
        self.assertIn("Nova scheduling filters", out_l0)
        self.assertNotIn("Details follow", out_l0)

        out_l1 = format_results(results, 30000, detail_level="L1")
        self.assertIn("Nova scheduling filters", out_l1)
        out_l2 = format_results(results, 30000, detail_level="L2")
        self.assertLess(len(out_l1), len(out_l2))

    def test_summarizer_not_called_when_sidecars_exist(self):
        """Once sidecars are lazily created, the enrichment logic reads
        them directly and never schedules the summarizer again.

        Full lifecycle:
        1. First search hit: no sidecars → extractive served, schedule fires
        2. Background completes: sidecars written
        3. Second search hit: sidecars fresh → no scheduling, LLM summaries served
        """
        store_dir = Path(tempfile.mkdtemp()) / "store"
        store_dir.mkdir()
        doc = store_dir / "guide.md"
        long_content = (
            "Nova scheduling filters determine host placement. "
            + "Details follow. " * 100
        )
        doc.write_text(long_content)

        mgr = SidecarManager(store_dir)

        schedule_calls: list[str] = []

        def fake_schedule(file_key, text):
            schedule_calls.append(file_key)
            mgr.write_sidecars(Path(file_key), text, "LLM-generated L0", "LLM-generated L1")

        l0 = mgr.get_l0(doc)
        l1 = mgr.get_l1(doc)
        self.assertIsNone(l0)
        self.assertIsNone(l1)

        results_before = [
            {
                "text": long_content,
                "source": str(doc),
                "metadata": {"title": "Scheduling"},
            }
        ]
        out_before = format_results(results_before, 30000, detail_level="L1")
        self.assertNotIn("LLM-generated", out_before)
        self.assertIn("Nova scheduling", out_before)

        if (not l0 and needs_l0(long_content)) or (not l1 and needs_l1(long_content)):
            fake_schedule(str(doc), long_content)

        self.assertEqual(len(schedule_calls), 1)
        self.assertEqual(mgr.get_l0(doc), "LLM-generated L0")
        self.assertEqual(mgr.get_l1(doc), "LLM-generated L1")

        results_after = [
            {
                "text": long_content,
                "source": str(doc),
                "metadata": {
                    "title": "Scheduling",
                    "l0_summary": mgr.get_l0(doc),
                    "l1_summary": mgr.get_l1(doc),
                },
            }
        ]
        out_after = format_results(results_after, 30000, detail_level="L1")
        self.assertIn("LLM-generated L1", out_after)

        schedule_calls.clear()
        l0 = mgr.get_l0(doc)
        l1 = mgr.get_l1(doc)
        if (not l0 and needs_l0(long_content)) or (not l1 and needs_l1(long_content)):
            fake_schedule(str(doc), long_content)

        self.assertEqual(len(schedule_calls), 0, "Summarizer must not be called when fresh sidecars exist")


class TestRecallL2PngWrap(unittest.TestCase):
    """Verify that recall() at L2 with png_wrap=True invokes wrap_as_images."""

    def _run_recall(self, detail_level="L2", png_wrap=True, tiered=True):
        import asyncio
        from unittest import mock

        from rag_mcp.memory_tools import recall

        memories = [
            {
                "content": "Full workflow procedure for GPU passthrough.",
                "category": "workflow",
                "saved_at": "2026-08-10T12:00:00Z",
                "uri": "viking://user/default/memories/workflow/test.md",
            },
        ]

        mock_memory = mock.AsyncMock()
        mock_memory.recall.return_value = memories

        mock_config = mock.MagicMock()
        mock_config.png_wrap = png_wrap
        mock_config.tiered_retrieval = tiered
        mock_config.default_detail_level = "L1"
        mock_config.max_response_chars = 30000
        mock_config.png_max_chars_per_store = 4500
        mock_config.png_max_pages = 3

        mock_app = mock.MagicMock()
        mock_app.memory = mock_memory
        mock_app.config = mock_config
        mock_app.embeddings = None

        mock_ctx = mock.MagicMock()

        with mock.patch(
            "rag_mcp.memory_tools.get_app_context",
            autospec=True,
            return_value=mock_app,
        ), mock.patch(
            "rag_mcp.png_wrap.wrap_as_images",
            return_value="<PNG_PAYLOAD>",
        ) as mock_wrap:
            result = asyncio.run(
                recall(mock_ctx, "GPU passthrough", detail_level=detail_level)
            )
        return result, mock_wrap

    def test_l2_recall_gets_png_payload(self):
        """L2 recall with png_wrap=True returns PNG-wrapped output."""
        result, mock_wrap = self._run_recall(detail_level="L2", png_wrap=True)
        mock_wrap.assert_called_once()
        self.assertEqual(result, "<PNG_PAYLOAD>")

    def test_l1_recall_skips_png(self):
        """L1 recall never triggers PNG wrap even when png_wrap=True."""
        result, mock_wrap = self._run_recall(detail_level="L1", png_wrap=True)
        mock_wrap.assert_not_called()
        self.assertIn("workflow", result)

    def test_l0_recall_skips_png(self):
        """L0 recall never triggers PNG wrap."""
        _result, mock_wrap = self._run_recall(detail_level="L0", png_wrap=True)
        mock_wrap.assert_not_called()

    def test_l2_recall_no_png_when_disabled(self):
        """L2 recall without png_wrap returns plain text."""
        result, mock_wrap = self._run_recall(detail_level="L2", png_wrap=False)
        mock_wrap.assert_not_called()
        self.assertIn("GPU passthrough", result)


if __name__ == "__main__":
    unittest.main()
