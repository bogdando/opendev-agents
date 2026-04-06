"""Tests for rag_mcp.backends.mock module."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from rag_mcp.backends.mock import MockBackend, _extract_title


class TestExtractTitle(unittest.TestCase):

    def test_heading_extracted(self):
        self.assertEqual("My Title", _extract_title("# My Title\n\nbody", Path("f.md")))

    def test_fallback_to_filename(self):
        self.assertEqual("Nova Scheduler", _extract_title("no heading here", Path("nova-scheduler.md")))

    def test_subheading_falls_back_to_filename(self):
        text = "## Sub Heading\n\nbody"
        self.assertEqual("Sub Heading", _extract_title(text, Path("sub-heading.md")))


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
        self.assertIn("metadata", r)
        self.assertIn("title", r["metadata"])
        self.assertIn("store_id", r["metadata"])
        self.assertEqual("docs", r["metadata"]["store_id"])

    def test_results_ranked_by_relevance(self):
        results = asyncio.run(self.backend.search("floating IPs router namespaces", "docs", 5))
        if len(results) > 1:
            self.assertEqual("L3 Agent", results[0]["metadata"]["title"])


if __name__ == "__main__":
    unittest.main()
