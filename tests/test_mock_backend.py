"""Tests for MockBackend embedding reranking."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rag_mcp.backends.mock import MockBackend


class TestMockBackendReranking(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        store_dir = Path(self._tmpdir) / "store1"
        store_dir.mkdir()
        (store_dir / "doc1.md").write_text(
            "# Alpha\nThis document discusses openstack deployment patterns."
        )
        (store_dir / "doc2.md").write_text(
            "# Beta\nThis covers openstack networking and ovn."
        )
        (store_dir / "doc3.md").write_text(
            "# Gamma\nInfrastructure automation with openstack."
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_search_without_embeddings_uses_keyword_order(self):
        backend = MockBackend(self._tmpdir)
        results = await backend.search("openstack", "store1", 10)
        self.assertEqual(3, len(results))
        for r in results:
            self.assertEqual(r["score"], 1.0)

    async def test_search_with_embeddings_reranks(self):
        backend = MockBackend(self._tmpdir)

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=[1.0, 0.0, 0.0])
        mock_embeddings.embed = mock.AsyncMock(return_value=[
            [0.1, 0.9, 0.1],  # doc1 - low similarity to query
            [0.9, 0.1, 0.0],  # doc2 - high similarity to query
            [0.5, 0.5, 0.0],  # doc3 - medium similarity
        ])

        results = await backend.search(
            "openstack", "store1", 10, embeddings=mock_embeddings,
        )

        self.assertEqual(3, len(results))
        scores = [r["score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertGreater(results[0]["score"], results[2]["score"])

    async def test_search_embedding_failure_preserves_keyword_results(self):
        backend = MockBackend(self._tmpdir)

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=None)

        results = await backend.search(
            "openstack", "store1", 10, embeddings=mock_embeddings,
        )

        self.assertEqual(3, len(results))
        for r in results:
            self.assertEqual(r["score"], 1.0)

    async def test_search_embed_docs_failure_preserves_keyword_results(self):
        backend = MockBackend(self._tmpdir)

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=[1.0, 0.0])
        mock_embeddings.embed = mock.AsyncMock(return_value=None)

        results = await backend.search(
            "openstack", "store1", 10, embeddings=mock_embeddings,
        )

        self.assertEqual(3, len(results))
        for r in results:
            self.assertEqual(r["score"], 1.0)


class TestGuaranteedBM25Slot(unittest.IsolatedAsyncioTestCase):
    """After semantic ranking, at least 1 keyword-matching result must appear."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        store_dir = Path(self._tmpdir) / "store1"
        store_dir.mkdir()
        (store_dir / "semantic_match.md").write_text(
            "# Semantically Similar\nThis doc has no query keywords at all."
        )
        (store_dir / "keyword_match.md").write_text(
            "# Keyword Match\nREFERENCE RESULTS for RAG MCP summarizer tests."
        )
        (store_dir / "another_semantic.md").write_text(
            "# Another Semantic\nAlso unrelated to the query keywords."
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_keyword_match_included_when_semantics_dominate(self):
        """Even when embeddings rank keyword_match.md last, it must appear."""
        backend = MockBackend(self._tmpdir)

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=[1.0, 0.0, 0.0])
        # Embeddings push keyword_match.md to last place
        mock_embeddings.embed = mock.AsyncMock(return_value=[
            [0.95, 0.05, 0.0],  # semantic_match.md - highest cosine
            [0.1, 0.1, 0.9],   # keyword_match.md - lowest cosine
            [0.8, 0.15, 0.05], # another_semantic.md - second highest
        ])

        results = await backend.search(
            "REFERENCE RESULTS RAG MCP summarizer", "store1", 2,
            embeddings=mock_embeddings,
        )

        sources = [r["source"] for r in results]
        self.assertIn("store1/keyword_match.md", sources)

    async def test_no_swap_when_keyword_match_already_in_top(self):
        """If top results already have keyword coverage, no swap needed."""
        backend = MockBackend(self._tmpdir)

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=[0.1, 0.1, 0.9])
        # keyword_match.md is already top by cosine
        mock_embeddings.embed = mock.AsyncMock(return_value=[
            [0.2, 0.1, 0.0],  # semantic_match.md
            [0.1, 0.1, 0.95], # keyword_match.md - highest
            [0.3, 0.1, 0.0],  # another_semantic.md
        ])

        results = await backend.search(
            "REFERENCE RESULTS RAG MCP summarizer", "store1", 2,
            embeddings=mock_embeddings,
        )

        self.assertEqual(2, len(results))
        self.assertIn("store1/keyword_match.md", results[0]["source"])


if __name__ == "__main__":
    unittest.main()
