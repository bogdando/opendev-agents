"""Tests for rag_mcp.backends.mock module."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from rag_mcp.constants import SEARCH_STOP_WORDS
from rag_mcp.backends.mock import MockBackend, _extract_title


class TestExtractTitle(unittest.TestCase):

    def test_heading_extracted(self):
        self.assertEqual("My Title", _extract_title("# My Title\n\nbody", Path("f.md")))

    def test_fallback_to_filename(self):
        self.assertEqual("Nova Scheduler", _extract_title("no heading here", Path("nova-scheduler.md")))

    def test_subheading_falls_back_to_filename(self):
        text = "## Sub Heading\n\nbody"
        self.assertEqual("Sub Heading", _extract_title(text, Path("sub-heading.md")))

    def test_rst_equals_underline(self):
        text = "My RST Title\n============\n\nBody text."
        self.assertEqual("My RST Title", _extract_title(text, Path("doc.rst")))

    def test_rst_dash_underline(self):
        text = "Section Name\n------------\n\nContent."
        self.assertEqual("Section Name", _extract_title(text, Path("s.rst")))

    def test_rst_directive_not_treated_as_heading(self):
        text = ".. toctree::\n===========\n\nReal Title\n==========\n"
        self.assertEqual("Real Title", _extract_title(text, Path("x.rst")))


class TestMockBackendListStores(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        store = self.root / "my-store"
        store.mkdir()
        (store / "doc-a.md").write_text("# Doc A\n\nContent about alpha.")
        (store / "doc-b.md").write_text("# Doc B\n\nContent about beta.")
        self.backend = MockBackend(str(self.root))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_store_discovered(self):
        stores = asyncio.run(self.backend.list_stores())
        self.assertEqual(1, len(stores))
        self.assertEqual("my-store", stores[0]["id"])

    def test_store_annotations(self):
        stores = asyncio.run(self.backend.list_stores())
        s = stores[0]
        self.assertEqual("public", s["access"])
        self.assertIsInstance(s["freshness"], str)
        self.assertNotEqual("unknown", s["freshness"])
        self.assertIsInstance(s["coverage"], list)
        self.assertEqual(2, len(s["coverage"]))
        self.assertIn("doc a", s["coverage"])
        self.assertIn("doc b", s["coverage"])

    def test_doc_count(self):
        stores = asyncio.run(self.backend.list_stores())
        self.assertEqual(2, stores[0]["doc_count"])

    def test_rst_files_counted(self):
        store = self.root / "rst-store"
        store.mkdir()
        (store / "guide.rst").write_text("Guide\n=====\n\nRST content.")
        (store / "notes.txt").write_text("Plain text notes.")
        stores = asyncio.run(self.backend.list_stores())
        rst_store = [s for s in stores if s["id"] == "rst-store"][0]
        self.assertEqual(2, rst_store["doc_count"])

    def test_nested_files_counted(self):
        store = self.root / "nested-store"
        store.mkdir()
        sub = store / "admin"
        sub.mkdir()
        (sub / "config.rst").write_text("Config\n======\n")
        (store / "index.md").write_text("# Index\n")
        stores = asyncio.run(self.backend.list_stores())
        ns = [s for s in stores if s["id"] == "nested-store"][0]
        self.assertEqual(2, ns["doc_count"])

    def test_hidden_dirs_ignored(self):
        (self.root / ".hidden").mkdir()
        (self.root / ".hidden" / "secret.md").write_text("secret")
        stores = asyncio.run(self.backend.list_stores())
        ids = [s["id"] for s in stores]
        self.assertNotIn(".hidden", ids)

    def test_empty_root(self):
        backend = MockBackend("/nonexistent/path")
        stores = asyncio.run(backend.list_stores())
        self.assertEqual([], stores)


class TestMockBackendGetStore(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        (self.root / "alpha").mkdir()
        (self.root / "alpha" / "f.md").write_text("# F\n\ncontent")
        self.backend = MockBackend(str(self.root))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_existing_store(self):
        store = asyncio.run(self.backend.get_store("alpha"))
        self.assertIsNotNone(store)
        self.assertEqual("alpha", store["id"])

    def test_missing_store(self):
        store = asyncio.run(self.backend.get_store("nonexistent"))
        self.assertIsNone(store)


class TestMockBackendSearch(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        store = self.root / "docs"
        store.mkdir()
        (store / "l3-agent.md").write_text("# L3 Agent\n\nManages floating IPs and router namespaces.")
        (store / "nova-scheduler.md").write_text("# Nova Scheduler\n\nFilter and weigher architecture.")
        (store / "unrelated.md").write_text("# Unrelated\n\nNothing relevant here.")
        self.backend = MockBackend(str(self.root))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_keyword_match(self):
        results = asyncio.run(self.backend.search("floating IPs", "docs", 5))
        self.assertGreaterEqual(len(results), 1)
        titles = [r["metadata"]["title"] for r in results]
        self.assertIn("L3 Agent", titles)

    def test_no_match(self):
        results = asyncio.run(self.backend.search("xyznonexistent", "docs", 5))
        self.assertEqual([], results)

    def test_top_k_limit(self):
        results = asyncio.run(self.backend.search("agent scheduler", "docs", 1))
        self.assertEqual(1, len(results))

    def test_missing_store_dir(self):
        results = asyncio.run(self.backend.search("anything", "no-such-store", 5))
        self.assertEqual([], results)

    def test_result_shape(self):
        results = asyncio.run(self.backend.search("scheduler", "docs", 1))
        self.assertEqual(1, len(results))
        r = results[0]
        self.assertIn("text", r)
        self.assertIn("source", r)
        self.assertIn("score", r)
        self.assertIn("metadata", r)
        self.assertIn("title", r["metadata"])
        self.assertIn("store_id", r["metadata"])
        self.assertEqual("docs", r["metadata"]["store_id"])
        self.assertIsInstance(r["score"], float)
        self.assertGreater(r["score"], 0.0)
        self.assertLessEqual(r["score"], 1.0)

    def test_results_ranked_by_relevance(self):
        results = asyncio.run(self.backend.search("floating IPs router namespaces", "docs", 5))
        if len(results) > 1:
            self.assertEqual("L3 Agent", results[0]["metadata"]["title"])

    def test_stop_words_removed_from_keywords(self):
        """Mock uses SEARCH_STOP_WORDS; filler words must not block matches."""
        self.assertIn("how", SEARCH_STOP_WORDS)
        self.assertIn("to", SEARCH_STOP_WORDS)
        results = asyncio.run(self.backend.search("how to scheduler", "docs", 5))
        titles = [r["metadata"]["title"] for r in results]
        self.assertIn("Nova Scheduler", titles)

    def test_all_tokens_stop_words_falls_back_to_raw_split(self):
        """If every token is a stop word, scoring uses the original split."""
        results = asyncio.run(self.backend.search("the and or", "docs", 5))
        # Fallback path: keywords become ["the", "and", "or"]; at least one
        # doc in the fixture contains common English (e.g. "and" in body).
        self.assertGreater(len(results), 0)


class TestMockBackendSearchRST(unittest.TestCase):
    """Search over .rst files and nested directories."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        store = self.root / "nova-docs"
        store.mkdir()
        (store / "index.rst").write_text(
            "Nova Documentation\n"
            "==================\n\n"
            "Welcome to the Nova compute service.\n"
        )
        sub = store / "admin"
        sub.mkdir()
        (sub / "scheduling.rst").write_text(
            "Scheduling\n"
            "==========\n\n"
            "Filter and weigher architecture for placement.\n"
        )
        (sub / "live-migration.rst").write_text(
            "Live Migration\n"
            "==============\n\n"
            "Move running instances between hosts.\n"
        )
        (store / "notes.txt").write_text(
            "Release notes: fixed live migration bug.\n"
        )
        self.backend = MockBackend(str(self.root))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_rst_keyword_match(self):
        results = asyncio.run(
            self.backend.search("scheduling placement", "nova-docs", 5)
        )
        self.assertGreaterEqual(len(results), 1)
        titles = [r["metadata"]["title"] for r in results]
        self.assertIn("Scheduling", titles)

    def test_nested_rst_found(self):
        results = asyncio.run(
            self.backend.search("live migration hosts", "nova-docs", 5)
        )
        self.assertGreaterEqual(len(results), 1)
        sources = [r["source"] for r in results]
        nested = [s for s in sources if "admin" in s]
        self.assertGreater(len(nested), 0)

    def test_txt_files_searched(self):
        results = asyncio.run(
            self.backend.search("release notes migration", "nova-docs", 5)
        )
        sources = [r["source"] for r in results]
        txt_hits = [s for s in sources if s.endswith(".txt")]
        self.assertGreater(len(txt_hits), 0)

    def test_rst_title_extracted(self):
        results = asyncio.run(
            self.backend.search("compute service", "nova-docs", 5)
        )
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(
            "Nova Documentation", results[0]["metadata"]["title"]
        )


if __name__ == "__main__":
    unittest.main()
