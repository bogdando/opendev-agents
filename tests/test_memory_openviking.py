"""Tests for rag_mcp.memory.openviking module (mocked HTTP)."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from rag_mcp.memory.openviking import OpenVikingMemoryBackend


def _mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestRemember(unittest.TestCase):

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            account="default",
            user="testuser",
            agent_id="test-agent",
        )

    def test_remember_calls_content_write(self):
        mock_resp = _mock_response({"status": "ok", "result": {"uri": "viking://..."}})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("test content", "workflow"))

        self.assertEqual("workflow", result["category"])
        self.assertIn("uri", result)
        self.assertIn("saved_at", result)
        self.assertNotIn("error", result)

        call_args = client_instance.post.call_args
        self.assertIn("/api/v1/content/write", call_args[0][0])
        payload = call_args[1]["json"]
        self.assertEqual("create", payload["mode"])
        self.assertTrue(payload["wait"])
        self.assertIn("category: workflow", payload["content"])
        self.assertIn("test content", payload["content"])

    def test_remember_uri_includes_category(self):
        mock_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("info", "decision"))

        self.assertIn("/decision/", result["uri"])
        self.assertTrue(result["uri"].startswith("viking://user/testuser/memories/"))

    def test_remember_invalid_category_defaults_to_context(self):
        mock_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("info", "bogus"))

        self.assertEqual("context", result["category"])

    def test_remember_http_error_returns_error_field(self):
        mock_resp = _mock_response({}, status_code=500)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("content", "workflow"))

        self.assertIn("error", result)


class TestRecall(unittest.TestCase):

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            account="default",
            user="testuser",
            agent_id="test-agent",
        )

    def test_recall_parses_memories_from_result(self):
        search_response = {
            "status": "ok",
            "result": {
                "memories": [
                    {
                        "uri": "viking://user/testuser/memories/workflow/20260527.md",
                        "score": 0.85,
                        "content": "",
                        "category": "workflow",
                    }
                ],
                "resources": [],
            },
        }
        read_response = {
            "status": "ok",
            "result": "---\ncategory: workflow\n---\n\nThe actual memory content",
        }

        mock_search_resp = _mock_response(search_response)
        mock_read_resp = _mock_response(read_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_search_resp
            client_instance.get.return_value = mock_read_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.recall("memory content"))

        self.assertEqual(1, len(results))
        self.assertEqual("workflow", results[0]["category"])
        self.assertIn("The actual memory content", results[0]["content"])
        self.assertIn("viking://", results[0]["uri"])

    def test_recall_uses_inline_content_when_present(self):
        search_response = {
            "status": "ok",
            "result": {
                "memories": [
                    {
                        "uri": "viking://user/testuser/memories/learning/item.md",
                        "score": 0.9,
                        "content": "Inline content from search",
                        "category": "learning",
                    }
                ],
                "resources": [],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.recall("something"))

        self.assertEqual("Inline content from search", results[0]["content"])
        client_instance.get.assert_not_called()

    def test_recall_with_category_filter(self):
        search_response = {"status": "ok", "result": {"memories": []}}
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(self.backend.recall("query", category="preference"))

        payload = client_instance.post.call_args[1]["json"]
        self.assertIn("/preference", payload["target_uri"])

    def test_recall_http_error_returns_empty(self):
        mock_resp = _mock_response({}, status_code=500)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.recall("anything"))

        self.assertEqual([], results)

    def test_recall_top_k_passed_as_limit(self):
        search_response = {"status": "ok", "result": {"memories": []}}
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(self.backend.recall("query", top_k=3))

        payload = client_instance.post.call_args[1]["json"]
        self.assertEqual(3, payload["limit"])


class TestReadContent(unittest.TestCase):

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            account="default",
            user="testuser",
            agent_id="test-agent",
        )

    def test_read_content_string_result(self):
        mock_resp = _mock_response({"status": "ok", "result": "plain text content"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.get.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            content = asyncio.run(self.backend._read_content("viking://some/uri.md"))

        self.assertEqual("plain text content", content)

    def test_read_content_dict_result(self):
        mock_resp = _mock_response(
            {"status": "ok", "result": {"content": "dict content", "uri": "x"}}
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.get.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            content = asyncio.run(self.backend._read_content("viking://some/uri.md"))

        self.assertEqual("dict content", content)

    def test_read_content_http_error_returns_empty(self):
        mock_resp = _mock_response({}, status_code=404)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.get.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            content = asyncio.run(self.backend._read_content("viking://missing.md"))

        self.assertEqual("", content)


class TestListMemories(unittest.TestCase):

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            account="default",
            user="testuser",
            agent_id="test-agent",
        )

    def test_list_parses_entries(self):
        ls_response = {
            "status": "ok",
            "entries": [
                {"name": "item1.md", "uri": "viking://user/testuser/memories/workflow/item1.md", "updated_at": "2026-05-27"},
                {"name": "item2.md", "uri": "viking://user/testuser/memories/workflow/item2.md", "updated_at": "2026-05-26"},
            ],
        }
        mock_resp = _mock_response(ls_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.get.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.list_memories(category="workflow"))

        self.assertEqual(2, len(results))
        self.assertEqual("item1.md", results[0]["content"])
        self.assertEqual("workflow", results[0]["category"])

    def test_list_respects_limit(self):
        ls_response = {
            "status": "ok",
            "entries": [{"name": f"f{i}.md", "uri": f"viking://u/{i}"} for i in range(10)],
        }
        mock_resp = _mock_response(ls_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.get.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.list_memories(limit=3))

        self.assertEqual(3, len(results))

    def test_list_http_error_returns_empty(self):
        mock_resp = _mock_response({}, status_code=500)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.get.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.list_memories())

        self.assertEqual([], results)


class TestMemoryPrefix(unittest.TestCase):

    def test_prefix_uses_user(self):
        backend = OpenVikingMemoryBackend(user="myuser")
        self.assertEqual("viking://user/myuser/memories", backend._memory_prefix())

    def test_prefix_default_user(self):
        backend = OpenVikingMemoryBackend()
        self.assertEqual("viking://user/developer/memories", backend._memory_prefix())


if __name__ == "__main__":
    unittest.main()
