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


if __name__ == "__main__":
    unittest.main()
