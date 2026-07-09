"""Tests for LocalMemoryBackend with embedding-enhanced recall."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rag_mcp.memory.local import LocalMemoryBackend


def _create_memory(root: Path, category: str, filename: str, content: str):
    """Helper to write a memory file with frontmatter."""
    cat_dir = root / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / filename).write_text(
        f"---\ncategory: {category}\nsaved_at: '2026-01-01T00:00:00Z'\n---\n\n{content}\n"
    )


class TestKeywordRecall(unittest.IsolatedAsyncioTestCase):
    """Baseline keyword recall (no embeddings)."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        _create_memory(self._root, "context", "m1.md", "deploy openstack with ansible")
        _create_memory(self._root, "context", "m2.md", "kubernetes networking with ovn")
        _create_memory(self._root, "decision", "m3.md", "decided to use openstack ironic for baremetal")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_basic_keyword_recall(self):
        backend = LocalMemoryBackend(self._tmpdir)
        results = await backend.recall("openstack")
        self.assertEqual(2, len(results))

    async def test_category_filter(self):
        backend = LocalMemoryBackend(self._tmpdir)
        results = await backend.recall("openstack", category="decision")
        self.assertEqual(1, len(results))
        self.assertIn("ironic", results[0]["content"])

    async def test_no_match_returns_empty(self):
        backend = LocalMemoryBackend(self._tmpdir)
        results = await backend.recall("zebra")
        self.assertEqual(0, len(results))


class TestEmbeddingReranking(unittest.IsolatedAsyncioTestCase):
    """Recall with embedding reranking."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        _create_memory(self._root, "context", "m1.md", "deploy openstack with ansible playbooks")
        _create_memory(self._root, "context", "m2.md", "openstack neutron networking setup")
        _create_memory(self._root, "context", "m3.md", "openstack ironic baremetal provisioning")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_reranking_reorders_results(self):
        backend = LocalMemoryBackend(self._tmpdir)

        def _embed_by_content(texts):
            vecs = []
            for t in texts:
                if "ironic" in t:
                    vecs.append([0.9, 0.1, 0.0])  # high similarity
                elif "neutron" in t:
                    vecs.append([0.5, 0.5, 0.0])  # medium
                else:
                    vecs.append([0.1, 0.9, 0.1])  # low
            return vecs

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=[1.0, 0.0, 0.0])
        mock_embeddings.embed = mock.AsyncMock(side_effect=_embed_by_content)

        results = await backend.recall("openstack", top_k=3, embeddings=mock_embeddings)

        self.assertEqual(3, len(results))
        self.assertIn("ironic", results[0]["content"])
        self.assertIn("ansible", results[2]["content"])

    async def test_embed_query_failure_falls_back_to_keyword(self):
        backend = LocalMemoryBackend(self._tmpdir)

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=None)

        results = await backend.recall("openstack", top_k=3, embeddings=mock_embeddings)

        self.assertEqual(3, len(results))
        mock_embeddings.embed.assert_not_called()

    async def test_embed_docs_failure_falls_back_to_keyword(self):
        backend = LocalMemoryBackend(self._tmpdir)

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=[1.0, 0.0])
        mock_embeddings.embed = mock.AsyncMock(return_value=None)

        results = await backend.recall("openstack", top_k=3, embeddings=mock_embeddings)

        self.assertEqual(3, len(results))


class TestMultiQueryExpansion(unittest.IsolatedAsyncioTestCase):
    """Multi-query gathers more candidates than single keyword search."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        _create_memory(self._root, "context", "m1.md", "ansible deployment automation")
        _create_memory(self._root, "context", "m2.md", "openstack cloud platform")
        _create_memory(self._root, "decision", "m3.md", "baremetal provisioning decision")
        _create_memory(self._root, "learning", "m4.md", "learned about ironic drivers")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_multi_query_finds_more_candidates(self):
        """With 3+ keywords, individual keyword searches find extra matches."""
        backend = LocalMemoryBackend(self._tmpdir)

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=[0.5, 0.5])
        mock_embeddings.embed = mock.AsyncMock(
            side_effect=lambda texts: [[0.5, 0.5]] * len(texts)
        )

        results = await backend.recall(
            "openstack ansible baremetal",
            top_k=10,
            embeddings=mock_embeddings,
        )

        self.assertGreaterEqual(len(results), 3)

    async def test_no_category_searches_all(self):
        """Without category filter, multi-query searches across all categories."""
        backend = LocalMemoryBackend(self._tmpdir)

        mock_embeddings = mock.AsyncMock()
        mock_embeddings.embed_query = mock.AsyncMock(return_value=[0.5, 0.5])
        mock_embeddings.embed = mock.AsyncMock(
            side_effect=lambda texts: [[0.5, 0.5]] * len(texts)
        )

        results = await backend.recall(
            "deployment automation",
            top_k=10,
            embeddings=mock_embeddings,
        )

        self.assertGreaterEqual(len(results), 1)

    async def test_without_embeddings_uses_keyword_only(self):
        """Without embeddings, plain keyword recall is used."""
        backend = LocalMemoryBackend(self._tmpdir)

        results_kw_only = await backend.recall("ansible", top_k=10)
        self.assertEqual(1, len(results_kw_only))
        self.assertIn("ansible", results_kw_only[0]["content"])


if __name__ == "__main__":
    unittest.main()
