"""Tests for rag_mcp.embeddings module."""

from __future__ import annotations

import unittest
from unittest import mock

from rag_mcp.embeddings import EmbeddingClient, cosine_similarity


class TestCosIneSimilarity(unittest.TestCase):

    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        self.assertAlmostEqual(cosine_similarity(v, v), 1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        self.assertAlmostEqual(cosine_similarity(a, b), 0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(a, b), -1.0)

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        self.assertEqual(cosine_similarity(a, b), 0.0)


class TestEmbeddingClient(unittest.IsolatedAsyncioTestCase):

    def _client(self, api_key: str = "") -> EmbeddingClient:
        return EmbeddingClient(
            base_url="http://localhost:11434",
            model="nomic-ai/nomic-embed-text-v1.5",
            api_key=api_key,
        )

    async def test_embed_success(self):
        client = self._client()
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = mock.Mock()
        mock_response.json.return_value = {
            "data": [
                {"index": 1, "embedding": [0.3, 0.4]},
                {"index": 0, "embedding": [0.1, 0.2]},
            ]
        }

        async def fake_post(*args, **kwargs):
            return mock_response

        with mock.patch.object(client._client, "post", side_effect=fake_post):
            result = await client.embed(["hello", "world"])

        self.assertEqual(result, [[0.1, 0.2], [0.3, 0.4]])

    async def test_embed_sorts_by_index(self):
        client = self._client()
        mock_response = mock.MagicMock()
        mock_response.raise_for_status = mock.Mock()
        mock_response.json.return_value = {
            "data": [
                {"index": 2, "embedding": [0.5]},
                {"index": 0, "embedding": [0.1]},
                {"index": 1, "embedding": [0.3]},
            ]
        }

        async def fake_post(*args, **kwargs):
            return mock_response

        with mock.patch.object(client._client, "post", side_effect=fake_post):
            result = await client.embed(["a", "b", "c"])

        self.assertEqual(result, [[0.1], [0.3], [0.5]])

    async def test_embed_http_error_returns_none(self):
        import httpx

        client = self._client()

        async def fake_post(*args, **kwargs):
            raise httpx.ConnectError("refused")

        with mock.patch.object(client._client, "post", side_effect=fake_post):
            result = await client.embed(["test"])

        self.assertIsNone(result)

    async def test_embed_malformed_json_returns_none(self):
        client = self._client()
        mock_response = mock.MagicMock()
        mock_response.raise_for_status = mock.Mock()
        mock_response.json.return_value = {"unexpected": "shape"}

        async def fake_post(*args, **kwargs):
            return mock_response

        with mock.patch.object(client._client, "post", side_effect=fake_post):
            result = await client.embed(["test"])

        self.assertIsNone(result)

    async def test_embed_query_returns_single_vector(self):
        client = self._client()
        mock_response = mock.MagicMock()
        mock_response.raise_for_status = mock.Mock()
        mock_response.json.return_value = {
            "data": [{"index": 0, "embedding": [0.5, 0.6, 0.7]}]
        }

        async def fake_post(*args, **kwargs):
            return mock_response

        with mock.patch.object(client._client, "post", side_effect=fake_post):
            result = await client.embed_query("test query")

        self.assertEqual(result, [0.5, 0.6, 0.7])

    async def test_embed_query_returns_none_on_failure(self):
        import httpx

        client = self._client()

        async def fake_post(*args, **kwargs):
            raise httpx.ReadTimeout("timeout")

        with mock.patch.object(client._client, "post", side_effect=fake_post):
            result = await client.embed_query("test")

        self.assertIsNone(result)

    async def test_api_key_in_headers(self):
        client = self._client(api_key="secret123")
        self.assertEqual(
            client._headers["Authorization"], "Bearer secret123"
        )

    async def test_no_api_key_no_auth_header(self):
        client = self._client()
        self.assertNotIn("Authorization", client._headers)


if __name__ == "__main__":
    unittest.main()
