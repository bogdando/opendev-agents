"""Tests for SolrBackend hybrid/semantic search and fallback."""

from __future__ import annotations

import unittest
from unittest import mock

import httpx


class TestSolrHybridSearch(unittest.IsolatedAsyncioTestCase):

    def _make_backend(self, search_mode: str = "hybrid"):
        from rag_mcp.backends.solr import SolrBackend

        return SolrBackend(
            solr_url="http://solr:8983",
            max_response_chars=30000,
            search_mode=search_mode,
        )

    def _mock_embeddings(self, vec=None, fail=False):
        """Create a mock EmbeddingClient."""
        m = mock.AsyncMock()
        if fail:
            m.embed_query = mock.AsyncMock(return_value=None)
        else:
            m.embed_query = mock.AsyncMock(return_value=vec or [0.1, 0.2, 0.3])
        return m

    @mock.patch("rag_mcp.backends.solr._solr_query")
    async def test_keyword_mode_skips_vector_search(self, mock_solr_query):
        backend = self._make_backend(search_mode="keyword")
        embeddings = self._mock_embeddings()

        mock_response = mock.MagicMock()
        mock_response.docs = []
        mock_data = mock.MagicMock()
        mock_data.response = mock_response
        mock_data.highlighting = {}
        mock_solr_query.return_value = mock_data

        results = await backend.search("query", "okp", 5, embeddings=embeddings)

        embeddings.embed_query.assert_not_called()
        self.assertEqual(results, [])

    async def test_hybrid_mode_calls_vector_endpoint(self):
        backend = self._make_backend(search_mode="hybrid")
        embeddings = self._mock_embeddings(vec=[0.1, 0.2])

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = mock.Mock()
        mock_resp.json.return_value = {
            "response": {
                "docs": [
                    {
                        "allTitle": "Test Doc",
                        "main_content": "content here",
                        "url_slug": "/docs/test",
                        "score": 0.95,
                        "documentKind": "article",
                        "product": "RHEL",
                    }
                ]
            }
        }

        async def fake_post(*args, **kwargs):
            return mock_resp

        with mock.patch.object(backend._client, "post", side_effect=fake_post) as m:
            results = await backend.search("query", "okp", 5, embeddings=embeddings)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["metadata"]["title"], "Test Doc")
        self.assertAlmostEqual(results[0]["score"], 1.0)

        call_args = m.call_args
        self.assertIn("hybrid-search", call_args[0][0])

    async def test_semantic_mode_calls_semantic_endpoint(self):
        backend = self._make_backend(search_mode="semantic")
        embeddings = self._mock_embeddings(vec=[0.1, 0.2])

        mock_resp = mock.MagicMock()
        mock_resp.raise_for_status = mock.Mock()
        mock_resp.json.return_value = {"response": {"docs": []}}

        async def fake_post(*args, **kwargs):
            return mock_resp

        with mock.patch.object(backend._client, "post", side_effect=fake_post) as m:
            results = await backend.search("query", "okp", 5, embeddings=embeddings)

        self.assertEqual(results, [])
        call_args = m.call_args
        self.assertIn("semantic-search", call_args[0][0])

    @mock.patch("rag_mcp.backends.solr._solr_query")
    async def test_hybrid_falls_back_on_embed_failure(self, mock_solr_query):
        backend = self._make_backend(search_mode="hybrid")
        embeddings = self._mock_embeddings(fail=True)

        mock_response = mock.MagicMock()
        mock_response.docs = []
        mock_data = mock.MagicMock()
        mock_data.response = mock_response
        mock_data.highlighting = {}
        mock_solr_query.return_value = mock_data

        results = await backend.search("query", "okp", 5, embeddings=embeddings)

        mock_solr_query.assert_called_once()
        self.assertEqual(results, [])

    @mock.patch("rag_mcp.backends.solr._solr_query")
    async def test_hybrid_falls_back_on_http_error(self, mock_solr_query):
        backend = self._make_backend(search_mode="hybrid")
        embeddings = self._mock_embeddings(vec=[0.1, 0.2])

        with mock.patch.object(
            backend._client, "post", side_effect=httpx.ConnectError("refused")
        ):
            mock_response = mock.MagicMock()
            mock_response.docs = []
            mock_data = mock.MagicMock()
            mock_data.response = mock_response
            mock_data.highlighting = {}
            mock_solr_query.return_value = mock_data

            results = await backend.search("query", "okp", 5, embeddings=embeddings)

        mock_solr_query.assert_called_once()
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
