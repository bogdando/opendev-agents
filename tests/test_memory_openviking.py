"""Tests for rag_mcp.memory.openviking module (mocked HTTP)."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from rag_mcp.memory.openviking import (
    OpenVikingMemoryBackend,
    _build_memory_dict,
    _category_from_uri,
    _filter_by_date,
    _keyword_overlap,
    _parse_iso_dt,
    _query_keywords,
    _saved_at_from_uri,
)


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


def _no_dup_response():
    """Search response with no matches (dedup check passes)."""
    return _mock_response({"status": "ok", "result": {"memories": []}})


def _dup_response(uri="viking://user/testuser/memories/learning/old.md", score=0.92):
    """Search response with a high-scoring duplicate."""
    return _mock_response({
        "status": "ok",
        "result": {
            "memories": [{
                "uri": uri,
                "score": score,
                "category": "learning",
                "saved_at": "2026-08-25T00:00:00",
            }],
        },
    })


class TestRemember(unittest.TestCase):

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            account="default",
            user="testuser",
            agent_id="test-agent",
        )
        self._vlm_patcher = patch.object(
            self.backend, "_trigger_vlm", new_callable=AsyncMock,
        )
        self._vlm_patcher.start()

    def tearDown(self):
        self._vlm_patcher.stop()

    def test_remember_calls_content_write(self):
        no_dup = _no_dup_response()
        write_resp = _mock_response({"status": "ok", "result": {"uri": "viking://..."}})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [no_dup, write_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("test content", "workflow"))

        self.assertEqual("workflow", result["category"])
        self.assertIn("uri", result)
        self.assertIn("saved_at", result)
        self.assertNotIn("error", result)

        write_call = client_instance.post.call_args_list[1]
        self.assertIn("/api/v1/content/write", write_call[0][0])
        payload = write_call[1]["json"]
        self.assertEqual("create", payload["mode"])
        self.assertTrue(payload["wait"])
        self.assertIn("category: workflow", payload["content"])
        self.assertIn("test content", payload["content"])

    def test_remember_uri_includes_category(self):
        no_dup = _no_dup_response()
        write_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [no_dup, write_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("info", "decision"))

        self.assertIn("/decision/", result["uri"])
        self.assertTrue(result["uri"].startswith("viking://user/testuser/memories/"))

    def test_remember_invalid_category_defaults_to_context(self):
        no_dup = _no_dup_response()
        write_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [no_dup, write_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("info", "bogus"))

        self.assertEqual("context", result["category"])

    def test_remember_http_error_returns_error_field(self):
        no_dup = _no_dup_response()
        write_resp = _mock_response({}, status_code=500)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [no_dup, write_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("content", "workflow"))

        self.assertIn("error", result)


class TestWriteTimeDedup(unittest.TestCase):

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            account="default",
            user="testuser",
            agent_id="test-agent",
            dedup_threshold=0.85,
        )
        self._vlm_patcher = patch.object(
            self.backend, "_trigger_vlm", new_callable=AsyncMock,
        )
        self._vlm_patcher.start()

    def tearDown(self):
        self._vlm_patcher.stop()

    def test_remember_skips_write_when_duplicate_found(self):
        dup_resp = _dup_response(score=0.92)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = dup_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("same content", "learning"))

        self.assertTrue(result.get("deduplicated"))
        self.assertIn("viking://", result["uri"])
        # Only one POST (the dedup search), no write call
        self.assertEqual(1, client_instance.post.call_count)

    def test_remember_writes_when_below_threshold(self):
        low_score = _dup_response(score=0.60)
        write_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [low_score, write_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("different content", "learning"))

        self.assertNotIn("deduplicated", result)
        self.assertEqual(2, client_instance.post.call_count)

    def test_remember_writes_when_no_existing_memories(self):
        no_dup = _no_dup_response()
        write_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [no_dup, write_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("brand new content", "context"))

        self.assertNotIn("deduplicated", result)
        self.assertEqual(2, client_instance.post.call_count)

    def test_dedup_disabled_when_threshold_zero(self):
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_threshold=0.0,
        )
        write_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch.object(backend, "_trigger_vlm", new_callable=AsyncMock):
            client_instance = AsyncMock()
            client_instance.post.return_value = write_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(backend.remember("content", "learning"))

        self.assertNotIn("deduplicated", result)
        self.assertEqual(1, client_instance.post.call_count)

    def test_dedup_search_error_does_not_block_write(self):
        search_err = _mock_response({}, status_code=500)
        write_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [search_err, write_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            result = asyncio.run(self.backend.remember("content", "context"))

        self.assertNotIn("deduplicated", result)
        self.assertNotIn("error", result)

    def test_dedup_search_truncates_content_to_2000(self):
        no_dup = _no_dup_response()
        write_resp = _mock_response({"status": "ok"})
        long_content = "x" * 5000

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [no_dup, write_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(self.backend.remember(long_content, "context"))

        search_call = client_instance.post.call_args_list[0]
        query = search_call[1]["json"]["query"]
        self.assertEqual(2000, len(query))

    def test_dedup_query_includes_frontmatter_stub(self):
        no_dup = _no_dup_response()
        write_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [no_dup, write_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(self.backend.remember("some content", "workflow"))

        search_call = client_instance.post.call_args_list[0]
        query = search_call[1]["json"]["query"]
        self.assertTrue(query.startswith("---\ncategory: workflow\n---\n\n"))


class TestTriggerVlm(unittest.TestCase):
    """Test the fire-and-forget VLM trigger via temp_upload + add_resource."""

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            vlm_enabled=True,
        )

    def test_trigger_vlm_calls_temp_upload_and_add_resource(self):
        upload_resp = _mock_response({
            "status": "ok",
            "result": {"temp_file_id": "upload_abc123.md"},
        })
        add_resp = _mock_response({"status": "ok"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [upload_resp, add_resp]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(self.backend._trigger_vlm(
                "full content", "learning", "20260826T180000Z.md",
            ))

        self.assertEqual(2, client_instance.post.call_count)
        upload_call = client_instance.post.call_args_list[0]
        self.assertIn("/api/v1/resources/temp_upload", upload_call[0][0])
        add_call = client_instance.post.call_args_list[1]
        self.assertIn("/api/v1/resources", add_call[0][0])
        add_json = add_call[1]["json"]
        self.assertEqual("upload_abc123.md", add_json["temp_file_id"])
        self.assertIn("resources/memories/learning/20260826T180000Z.md", add_json["to"])
        self.assertFalse(add_json["wait"])

    def test_trigger_vlm_swallows_http_error(self):
        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = httpx.ConnectError("refused")
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(self.backend._trigger_vlm(
                "content", "context", "test.md",
            ))


class TestVlmAbstractEnrichment(unittest.TestCase):
    """Test recall enriches memory results with VLM abstracts from resources."""

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=0,
            vlm_enabled=True,
        )

    def test_recall_enriches_l0_from_resource_abstracts(self):
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/doc.md",
                    "score": 0.8,
                    "content": "Full content here",
                    "abstract": "",
                }],
                "resources": [],
            },
        }
        resource_response = {
            "status": "ok",
            "result": {
                "resources": [{
                    "uri": "viking://user/testuser/resources/memories/learning/doc.md/doc.md",
                    "score": 0.7,
                    "abstract": "VLM-generated one-line abstract",
                }],
            },
        }
        mock_search = _mock_response(search_response)
        mock_resource = _mock_response(resource_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.side_effect = [mock_search, mock_resource]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.recall("query", detail_level="L0"))

        self.assertEqual(1, len(results))
        self.assertEqual("VLM-generated one-line abstract", results[0]["l0_summary"])

    def test_recall_skips_resource_search_when_abstracts_present(self):
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/doc.md",
                    "score": 0.8,
                    "content": "Full content",
                    "abstract": "Already has abstract",
                }],
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

            results = asyncio.run(self.backend.recall("query", detail_level="L0"))

        self.assertEqual("Already has abstract", results[0]["l0_summary"])
        self.assertEqual(1, client_instance.post.call_count)


    def test_vlm_disabled_skips_resource_search(self):
        """When vlm_enabled=False, recall does no resource enrichment."""
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=0,
            vlm_enabled=False,
        )
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/doc.md",
                    "score": 0.8,
                    "content": "Full content here",
                }],
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

            results = asyncio.run(backend.recall("query", detail_level="L0"))

        self.assertEqual(1, len(results))
        self.assertNotIn("l0_summary", results[0])
        self.assertEqual(1, client_instance.post.call_count)


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
        self.assertEqual(9, payload["limit"])  # always top_k * 3


class TestRecallDedup(unittest.TestCase):

    def test_recall_uses_context_face_with_session_id(self):
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=5,
        )
        search_response = {"status": "ok", "result": {"entries": []}}
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(backend.recall("query", session_id="cu-abc123"))

        payload = client_instance.post.call_args[1]["json"]
        self.assertEqual("context", payload["mode"])
        self.assertEqual("cu-abc123", payload["session_id"])
        self.assertEqual(5, payload["dedup_turns"])
        self.assertNotIn("target_uri", payload)

    def test_recall_context_mode_parses_entries(self):
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=5,
        )
        search_response = {
            "status": "ok",
            "result": {
                "entries": [{
                    "uri": "viking://user/testuser/memories/learning/item.md",
                    "category": "memories",
                    "score": 0.85,
                    "detail": "overview",
                    "text": "The context mode text content",
                    "origin": "self",
                }],
                "stats": {"dedup": {"turns": 5, "status": "ok", "cooled": 0}},
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(backend.recall("query", session_id="s1"))

        self.assertEqual(1, len(results))
        self.assertEqual("The context mode text content", results[0]["content"])
        self.assertEqual("The context mode text content", results[0]["l1_summary"])
        self.assertEqual(0.85, results[0]["score"])

    def test_recall_no_context_face_without_session_id(self):
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=5,
        )
        search_response = {"status": "ok", "result": {"memories": []}}
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(backend.recall("query"))

        payload = client_instance.post.call_args[1]["json"]
        self.assertNotIn("mode", payload)
        self.assertNotIn("session_id", payload)
        self.assertNotIn("dedup_turns", payload)
        self.assertIn("target_uri", payload)

    def test_recall_fixed_client_id_same_session(self):
        """Same client_id on consecutive calls uses same dedup window."""
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=5,
        )
        search_response = {"status": "ok", "result": {"entries": []}}
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(backend.recall("query", session_id="fixed-id"))
            asyncio.run(backend.recall("query", session_id="fixed-id"))

        calls = client_instance.post.call_args_list
        self.assertEqual(2, len(calls))
        for call in calls:
            payload = call[1]["json"]
            self.assertEqual("fixed-id", payload["session_id"])
            self.assertEqual("context", payload["mode"])

    def test_recall_different_client_ids_separate_sessions(self):
        """Different client_ids create independent dedup windows."""
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=5,
        )
        search_response = {"status": "ok", "result": {"entries": []}}
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(backend.recall("query", session_id="session-A"))
            asyncio.run(backend.recall("query", session_id="session-B"))

        calls = client_instance.post.call_args_list
        payloads = [c[1]["json"] for c in calls]
        self.assertEqual("session-A", payloads[0]["session_id"])
        self.assertEqual("session-B", payloads[1]["session_id"])

    def test_recall_no_context_face_when_dedup_turns_zero(self):
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=0,
        )
        search_response = {"status": "ok", "result": {"memories": []}}
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(backend.recall("query", session_id="cu-abc123"))

        payload = client_instance.post.call_args[1]["json"]
        self.assertNotIn("mode", payload)


class TestBuildMemoryDict(unittest.TestCase):
    """Unit tests for _build_memory_dict tier routing."""

    def _item(self, **overrides):
        base = {"saved_at": "2026-08-26", "score": 0.9}
        base.update(overrides)
        return base

    def test_abstract_detail_at_l0(self):
        mem = _build_memory_dict(
            "Short abstract text", "abstract", self._item(),
            "viking://u/memories/learning/x.md", "learning", "L0",
        )
        self.assertEqual("Short abstract text", mem["l0_summary"])
        self.assertEqual("", mem["content"])

    def test_abstract_detail_at_l1(self):
        mem = _build_memory_dict(
            "Short abstract text", "abstract", self._item(),
            "viking://u/memories/learning/x.md", "learning", "L1",
        )
        self.assertEqual("Short abstract text", mem["l0_summary"])
        self.assertEqual("Short abstract text", mem["content"])

    def test_abstract_detail_at_l2(self):
        """At L2, abstract text goes to l0_summary; content left empty for _read_content."""
        mem = _build_memory_dict(
            "Short abstract text", "abstract", self._item(),
            "viking://u/memories/learning/x.md", "learning", "L2",
        )
        self.assertEqual("Short abstract text", mem["l0_summary"])
        self.assertEqual("", mem["content"])

    def test_overview_detail_sets_l1(self):
        mem = _build_memory_dict(
            "Longer overview paragraph", "overview", self._item(),
            "viking://u/memories/learning/x.md", "learning", "L1",
        )
        self.assertEqual("Longer overview paragraph", mem["l1_summary"])
        self.assertEqual("Longer overview paragraph", mem["content"])
        self.assertNotIn("l0_summary", mem)

    def test_full_detail_no_sidecars(self):
        mem = _build_memory_dict(
            "Full content here", "full", self._item(),
            "viking://u/memories/learning/x.md", "learning", "L2",
        )
        self.assertEqual("Full content here", mem["content"])
        self.assertNotIn("l0_summary", mem)
        self.assertNotIn("l1_summary", mem)

    def test_no_detail_field_treated_as_full(self):
        mem = _build_memory_dict(
            "Content without detail", "", self._item(),
            "viking://u/memories/learning/x.md", "learning", "L2",
        )
        self.assertEqual("Content without detail", mem["content"])

    def test_existing_abstract_field_preferred_over_text(self):
        item = self._item(abstract="VLM abstract")
        mem = _build_memory_dict(
            "Overview text", "abstract", item,
            "viking://u/memories/learning/x.md", "learning", "L0",
        )
        self.assertEqual("VLM abstract", mem["l0_summary"])

    def test_existing_overview_field_preferred_over_text(self):
        item = self._item(overview="VLM overview")
        mem = _build_memory_dict(
            "Full text", "overview", item,
            "viking://u/memories/learning/x.md", "learning", "L1",
        )
        self.assertEqual("VLM overview", mem["l1_summary"])


class TestDetailTierRecall(unittest.TestCase):
    """Integration tests: recall with detail tier mapping end-to-end."""

    def _make_backend(self):
        return OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=5,
        )

    def test_l0_recall_abstract_entry_no_read_content(self):
        """L0 recall with abstract entry should NOT fetch full content."""
        backend = self._make_backend()
        search_response = {
            "status": "ok",
            "result": {
                "entries": [{
                    "uri": "viking://user/testuser/memories/learning/x.md",
                    "score": 0.8, "detail": "abstract",
                    "text": "One-line abstract",
                    "category": "memories",
                }],
                "stats": {},
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(backend.recall(
                "query", session_id="s1", detail_level="L0",
            ))

        self.assertEqual(1, len(results))
        self.assertEqual("One-line abstract", results[0]["l0_summary"])
        self.assertEqual("", results[0]["content"])

    def test_l2_recall_abstract_entry_fetches_full(self):
        """L2 recall with abstract entry should fetch full content."""
        backend = self._make_backend()
        search_response = {
            "status": "ok",
            "result": {
                "entries": [{
                    "uri": "viking://user/testuser/memories/learning/x.md",
                    "score": 0.8, "detail": "abstract",
                    "text": "One-line abstract",
                    "category": "memories",
                }],
                "stats": {},
            },
        }
        read_response = {
            "status": "ok",
            "result": "Full memory content from OV",
        }
        mock_search = _mock_response(search_response)
        mock_read = _mock_response(read_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_search
            client_instance.get.return_value = mock_read
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(backend.recall(
                "query", session_id="s1", detail_level="L2",
            ))

        self.assertEqual("Full memory content from OV", results[0]["content"])
        self.assertEqual("One-line abstract", results[0]["l0_summary"])

    def test_l1_recall_overview_entry_uses_text_as_content(self):
        """L1 recall with overview entry uses text as both content and l1_summary."""
        backend = self._make_backend()
        search_response = {
            "status": "ok",
            "result": {
                "entries": [{
                    "uri": "viking://user/testuser/memories/learning/x.md",
                    "score": 0.8, "detail": "overview",
                    "text": "A longer overview paragraph about the topic.",
                    "category": "memories",
                }],
                "stats": {},
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(backend.recall(
                "query", session_id="s1", detail_level="L1",
            ))

        self.assertEqual("A longer overview paragraph about the topic.", results[0]["content"])
        self.assertEqual("A longer overview paragraph about the topic.", results[0]["l1_summary"])

    def test_overview_frontmatter_only_fetches_full(self):
        """Overview entry with only YAML frontmatter falls back to _read_content."""
        backend = self._make_backend()
        search_response = {
            "status": "ok",
            "result": {
                "entries": [{
                    "uri": "viking://user/testuser/memories/learning/x.md",
                    "score": 0.7, "detail": "overview",
                    "text": "---\ncategory: learning\nsaved_at: 2026-06-06\nagent_id: test\n---",
                    "category": "memories",
                }],
                "stats": {},
            },
        }
        read_response = {
            "status": "ok",
            "result": "---\ncategory: learning\n---\n\nActual content of the memory.",
        }
        mock_search = _mock_response(search_response)
        mock_read = _mock_response(read_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_search
            client_instance.get.return_value = mock_read
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(backend.recall(
                "query", session_id="s1", detail_level="L1",
            ))

        self.assertEqual(1, len(results))
        self.assertEqual("Actual content of the memory.", results[0]["content"])
        # GET called for _read_content; keyword fallback may also call list_memories
        self.assertGreaterEqual(client_instance.get.call_count, 1)

    def test_plain_search_no_detail_field(self):
        """Non-context recall (no detail field) behaves like full."""
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=0,
        )
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/x.md",
                    "score": 0.8,
                    "content": "Full raw content from plain search",
                }],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(backend.recall("query", detail_level="L0"))

        self.assertEqual("Full raw content from plain search", results[0]["content"])
        self.assertNotIn("l0_summary", results[0])


class TestRecallFieldMapping(unittest.TestCase):

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
        )

    def test_recall_maps_abstract_to_l0_summary(self):
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/item.md",
                    "score": 0.90,
                    "content": "full content here",
                    "category": "learning",
                    "abstract": "A one-line VLM-generated abstract.",
                    "overview": None,
                }],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.recall("query"))

        self.assertEqual("A one-line VLM-generated abstract.", results[0]["l0_summary"])
        self.assertNotIn("l1_summary", results[0])

    def test_recall_maps_overview_to_l1_summary(self):
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/item.md",
                    "score": 0.90,
                    "content": "full content here",
                    "category": "learning",
                    "abstract": "Short abstract.",
                    "overview": "A longer VLM-generated overview paragraph.",
                }],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.recall("query"))

        self.assertEqual("Short abstract.", results[0]["l0_summary"])
        self.assertEqual("A longer VLM-generated overview paragraph.", results[0]["l1_summary"])

    def test_recall_prefers_l0_summary_over_abstract(self):
        """If OV returns both field names, l0_summary wins."""
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/item.md",
                    "score": 0.90,
                    "content": "content",
                    "category": "learning",
                    "l0_summary": "From l0_summary field.",
                    "abstract": "From abstract field.",
                    "l1_summary": "From l1_summary field.",
                    "overview": "From overview field.",
                }],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.recall("query"))

        self.assertEqual("From l0_summary field.", results[0]["l0_summary"])
        self.assertEqual("From l1_summary field.", results[0]["l1_summary"])

    def test_recall_no_summaries_when_fields_empty(self):
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/item.md",
                    "score": 0.90,
                    "content": "content",
                    "category": "learning",
                    "abstract": "",
                    "overview": None,
                }],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.recall("query"))

        self.assertNotIn("l0_summary", results[0])
        self.assertNotIn("l1_summary", results[0])

    def test_recall_includes_score(self):
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/item.md",
                    "score": 0.75,
                    "content": "content",
                    "category": "learning",
                }],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(self.backend.recall("query"))

        self.assertEqual(0.75, results[0]["score"])


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


class TestCategoryFromUri(unittest.TestCase):

    def test_extracts_learning(self):
        uri = "viking://user/default/memories/learning/20260826.md"
        self.assertEqual("learning", _category_from_uri(uri))

    def test_extracts_workflow(self):
        uri = "viking://user/u/memories/workflow/file.md"
        self.assertEqual("workflow", _category_from_uri(uri))

    def test_unknown_segment_falls_back(self):
        uri = "viking://user/u/memories/bogus/file.md"
        self.assertEqual("context", _category_from_uri(uri))

    def test_no_memories_segment_falls_back(self):
        uri = "viking://user/u/resources/file.md"
        self.assertEqual("context", _category_from_uri(uri))


class TestRecallCategoryFallback(unittest.TestCase):

    def test_recall_extracts_category_from_uri_when_ov_returns_empty(self):
        """OV returns category='' — category should be inferred from URI."""
        backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
        )
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/learning/item.md",
                    "score": 0.90,
                    "content": "some content",
                    "category": "",
                }],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(backend.recall("query"))

        self.assertEqual("learning", results[0]["category"])


class TestSessionIdPrecedence(unittest.TestCase):
    """Test session_id precedence: client_id param > ctx > app."""

    def _make_backend(self, dedup_turns=5):
        return OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=dedup_turns,
        )

    def _run_recall_get_session_id(self, backend, session_id=""):
        search_response = {
            "status": "ok",
            "result": {"entries": []},
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(
                return_value=client_instance,
            )
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(backend.recall(
                "query", session_id=session_id,
            ))

        payload = client_instance.post.call_args[1]["json"]
        return payload.get("session_id", "")

    def test_explicit_client_id_used(self):
        backend = self._make_backend()
        sid = self._run_recall_get_session_id(
            backend, session_id="explicit-42",
        )
        self.assertEqual("explicit-42", sid)

    def test_empty_client_id_no_context_mode(self):
        """No session_id → plain search (no context mode)."""
        backend = self._make_backend()
        search_response = {
            "status": "ok",
            "result": {"memories": []},
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(
                return_value=client_instance,
            )
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            asyncio.run(backend.recall("query"))

        payload = client_instance.post.call_args[1]["json"]
        self.assertNotIn("session_id", payload)
        self.assertNotIn("mode", payload)

    def test_fixed_id_persists_across_calls(self):
        backend = self._make_backend()
        sid1 = self._run_recall_get_session_id(
            backend, session_id="stable-session",
        )
        sid2 = self._run_recall_get_session_id(
            backend, session_id="stable-session",
        )
        self.assertEqual(sid1, sid2)
        self.assertEqual("stable-session", sid1)

    def test_switched_id_changes_session(self):
        backend = self._make_backend()
        sid1 = self._run_recall_get_session_id(
            backend, session_id="session-alpha",
        )
        sid2 = self._run_recall_get_session_id(
            backend, session_id="session-beta",
        )
        self.assertNotEqual(sid1, sid2)


class TestKeywordHelpers(unittest.TestCase):
    """Unit tests for _query_keywords and _keyword_overlap."""

    def test_query_keywords_filters_stop_words(self):
        kws = _query_keywords("REFERENCE RESULTS for RAG MCP summarizer tests")
        self.assertNotIn("for", kws)
        self.assertIn("reference", kws)
        self.assertIn("results", kws)
        self.assertIn("rag", kws)
        self.assertIn("mcp", kws)
        self.assertIn("summarizer", kws)
        self.assertIn("tests", kws)

    def test_query_keywords_filters_short_words(self):
        kws = _query_keywords("I do it so no up my")
        # All are stop words or <=2 chars; fallback returns all
        self.assertGreater(len(kws), 0)

    def test_keyword_overlap_full_match(self):
        text = "REFERENCE RESULTS for RAG MCP summarizer tests"
        kws = _query_keywords("REFERENCE RESULTS RAG MCP summarizer tests")
        self.assertAlmostEqual(_keyword_overlap(text, kws), 1.0)

    def test_keyword_overlap_partial_match(self):
        text = "REFERENCE content about something else"
        kws = _query_keywords("REFERENCE RESULTS RAG MCP summarizer")
        self.assertGreater(_keyword_overlap(text, kws), 0.0)
        self.assertLess(_keyword_overlap(text, kws), 0.5)

    def test_keyword_overlap_no_match(self):
        text = "completely unrelated content about pods"
        kws = _query_keywords("REFERENCE RESULTS RAG MCP summarizer")
        self.assertEqual(_keyword_overlap(text, kws), 0.0)

    def test_keyword_overlap_empty_keywords(self):
        self.assertEqual(_keyword_overlap("any text", []), 0.0)


class TestHybridRecallKeywordFallback(unittest.TestCase):
    """Guaranteed BM25 slot: keyword fallback fires when semantic misses."""

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=0,
        )

    def test_keyword_fallback_fires_when_semantic_has_no_keyword_coverage(self):
        """Semantic returns results without query keywords → fallback finds match."""
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/context/unrelated.md",
                    "score": 0.9,
                    "content": "Completely unrelated content about kubernetes pods",
                    "category": "context",
                }],
            },
        }
        ls_response = {
            "entries": [
                {
                    "name": "target.md",
                    "uri": "viking://user/testuser/memories/context/target.md",
                    "updated_at": "2026-08-27",
                },
            ],
        }
        read_response = {
            "status": "ok",
            "result": "REFERENCE RESULTS for RAG MCP summarizer tests with granite model",
        }

        mock_search = _mock_response(search_response)
        mock_ls = _mock_response(ls_response)
        mock_read = _mock_response(read_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_search
            client_instance.get.side_effect = [mock_ls, mock_read]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(
                self.backend.recall("REFERENCE RESULTS RAG MCP summarizer")
            )

        contents = [r["content"] for r in results]
        self.assertTrue(any("REFERENCE RESULTS" in c for c in contents))

    def test_no_fallback_when_semantic_has_keyword_coverage(self):
        """Semantic results contain query keywords → no fallback needed."""
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/context/match.md",
                    "score": 0.85,
                    "content": "REFERENCE RESULTS for RAG MCP summarizer tests",
                    "category": "context",
                }],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(
                self.backend.recall("REFERENCE RESULTS RAG MCP summarizer")
            )

        self.assertEqual(1, len(results))
        # No GET calls for list_memories or _read_content
        client_instance.get.assert_not_called()

    def test_keyword_fallback_deduplicates_by_uri(self):
        """Fallback skips URIs already present in semantic results."""
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/context/target.md",
                    "score": 0.5,
                    "content": "Short unrelated snippet",
                    "category": "context",
                }],
            },
        }
        ls_response = {
            "entries": [
                {
                    "name": "target.md",
                    "uri": "viking://user/testuser/memories/context/target.md",
                    "updated_at": "2026-08-27",
                },
            ],
        }

        mock_search = _mock_response(search_response)
        mock_ls = _mock_response(ls_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_search
            client_instance.get.return_value = mock_ls
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(
                self.backend.recall("REFERENCE RESULTS RAG summarizer")
            )

        # Only the original result — fallback found no new URI
        self.assertEqual(1, len(results))

    def test_search_limit_always_x3(self):
        """search_limit is always top_k * 3 for all detail levels."""
        search_response = {"status": "ok", "result": {"memories": []}}
        mock_resp = _mock_response(search_response)

        for detail in ("L0", "L1", "L2"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                client_instance = AsyncMock()
                client_instance.post.return_value = mock_resp
                client_instance.__aenter__ = AsyncMock(return_value=client_instance)
                client_instance.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = client_instance

                asyncio.run(
                    self.backend.recall("query", top_k=5, detail_level=detail)
                )

            payload = client_instance.post.call_args[1]["json"]
            self.assertEqual(
                15, payload["limit"],
                f"detail_level={detail} should always use limit=15 (top_k*3)",
            )

    def test_partial_keyword_coverage_does_not_suppress_fallback(self):
        """Results with 60% keyword coverage should NOT suppress the fallback.

        This reproduces the real-world case where "Re-run RAG MCP summarizer
        regression" has partial keyword overlap (rag, mcp, summarizer = 3/5)
        but is not the exact match.  The 80% threshold should let the fallback
        fire and find the actual gold memory.
        """
        search_response = {
            "status": "ok",
            "result": {
                "memories": [{
                    "uri": "viking://user/testuser/memories/context/partial.md",
                    "score": 0.88,
                    "content": "Re-run RAG MCP summarizer regression (mock + OKP)",
                    "category": "context",
                }],
            },
        }
        ls_response = {
            "entries": [
                {
                    "name": "gold.md",
                    "uri": "viking://user/testuser/memories/workflow/gold.md",
                    "updated_at": "2026-08-27",
                },
            ],
        }
        read_response = {
            "status": "ok",
            "result": "REFERENCE RESULTS for RAG MCP summarizer tests with granite",
        }

        mock_search = _mock_response(search_response)
        mock_ls = _mock_response(ls_response)
        mock_read = _mock_response(read_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_search
            client_instance.get.side_effect = [mock_ls, mock_read]
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(
                self.backend.recall(
                    "REFERENCE RESULTS RAG MCP summarizer tests", top_k=5
                )
            )

        contents = [r["content"] for r in results]
        self.assertTrue(
            any("REFERENCE RESULTS for RAG MCP summarizer tests" in c for c in contents),
            "Fallback should find the exact keyword match",
        )

    def test_hybrid_rerank_boosts_keyword_matches(self):
        """Hybrid reranking promotes results with keyword overlap."""
        search_response = {
            "status": "ok",
            "result": {
                "memories": [
                    {
                        "uri": "viking://user/testuser/memories/context/no_kw.md",
                        "score": 0.95,
                        "content": "Unrelated high-similarity content about pods",
                        "category": "context",
                    },
                    {
                        "uri": "viking://user/testuser/memories/context/has_kw.md",
                        "score": 0.60,
                        "content": "REFERENCE RESULTS for RAG MCP summarizer tests",
                        "category": "context",
                    },
                ],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(
                self.backend.recall(
                    "REFERENCE RESULTS RAG MCP summarizer", top_k=2
                )
            )

        # Keyword-bearing result should be promoted to first by hybrid score
        self.assertIn("REFERENCE RESULTS", results[0]["content"])


class TestSavedAtFromUri(unittest.TestCase):
    """Extract ISO timestamp from viking memory URI filenames."""

    def test_standard_filename(self):
        uri = "viking://user/default/memories/context/20260826T112211Z.md"
        self.assertEqual(_saved_at_from_uri(uri), "2026-08-26T11:22:11+00:00")

    def test_no_extension(self):
        uri = "viking://user/default/memories/workflow/20260101T000000Z"
        self.assertEqual(_saved_at_from_uri(uri), "2026-01-01T00:00:00+00:00")

    def test_non_timestamp_filename(self):
        uri = "viking://user/default/memories/context/random-note.md"
        self.assertEqual(_saved_at_from_uri(uri), "")

    def test_empty_uri(self):
        self.assertEqual(_saved_at_from_uri(""), "")


class TestParseIsoDt(unittest.TestCase):
    """Parse ISO 8601 date/datetime strings."""

    def test_date_only(self):
        dt = _parse_iso_dt("2026-08-26")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 26)

    def test_datetime_with_offset(self):
        dt = _parse_iso_dt("2026-08-26T11:22:11+00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 11)
        self.assertEqual(dt.minute, 22)

    def test_datetime_with_z(self):
        dt = _parse_iso_dt("2026-08-26T11:22:11Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 11)

    def test_empty_string(self):
        self.assertIsNone(_parse_iso_dt(""))

    def test_invalid_string(self):
        self.assertIsNone(_parse_iso_dt("not-a-date"))


class TestFilterByDate(unittest.TestCase):
    """Client-side date-range filtering."""

    def setUp(self):
        self.items = [
            {"saved_at": "2026-08-25T10:00:00+00:00", "content": "day25"},
            {"saved_at": "2026-08-26T11:22:11+00:00", "content": "day26"},
            {"saved_at": "2026-08-27T09:00:00+00:00", "content": "day27"},
        ]

    def test_after_filter(self):
        dt_after = _parse_iso_dt("2026-08-26")
        result = _filter_by_date(self.items, dt_after, None)
        contents = [r["content"] for r in result]
        self.assertNotIn("day25", contents)
        self.assertIn("day26", contents)
        self.assertIn("day27", contents)

    def test_before_filter(self):
        dt_before = _parse_iso_dt("2026-08-27")
        result = _filter_by_date(self.items, None, dt_before)
        contents = [r["content"] for r in result]
        self.assertIn("day25", contents)
        self.assertIn("day26", contents)
        self.assertNotIn("day27", contents)

    def test_range_filter(self):
        dt_after = _parse_iso_dt("2026-08-26")
        dt_before = _parse_iso_dt("2026-08-27")
        result = _filter_by_date(self.items, dt_after, dt_before)
        self.assertEqual(1, len(result))
        self.assertEqual("day26", result[0]["content"])

    def test_empty_saved_at_excluded(self):
        items = [{"saved_at": "", "content": "no-ts"}]
        dt_after = _parse_iso_dt("2026-08-01")
        result = _filter_by_date(items, dt_after, None)
        self.assertEqual(0, len(result))


class TestRecallDateFilter(unittest.TestCase):
    """Integration: recall with saved_after/saved_before narrows results."""

    def setUp(self):
        self.backend = OpenVikingMemoryBackend(
            url="http://127.0.0.1:1933",
            user="testuser",
            agent_id="test-agent",
            dedup_turns=0,
        )

    def test_saved_after_filters_old_memories(self):
        """Only memories on or after saved_after are returned."""
        search_response = {
            "status": "ok",
            "result": {
                "memories": [
                    {
                        "uri": "viking://user/testuser/memories/context/20260825T100000Z.md",
                        "score": 0.9,
                        "content": "Old memory from Aug 25",
                        "category": "context",
                    },
                    {
                        "uri": "viking://user/testuser/memories/context/20260826T112211Z.md",
                        "score": 0.85,
                        "content": "REFERENCE RESULTS for RAG MCP summarizer tests",
                        "category": "context",
                    },
                ],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(
                self.backend.recall(
                    "REFERENCE RESULTS",
                    top_k=5,
                    saved_after="2026-08-26",
                )
            )

        contents = [r["content"] for r in results]
        self.assertNotIn("Old memory from Aug 25", contents)
        self.assertIn("REFERENCE RESULTS for RAG MCP summarizer tests", contents)

    def test_saved_before_filters_new_memories(self):
        """Only memories before saved_before are returned."""
        search_response = {
            "status": "ok",
            "result": {
                "memories": [
                    {
                        "uri": "viking://user/testuser/memories/context/20260826T112211Z.md",
                        "score": 0.9,
                        "content": "Target memory",
                        "category": "context",
                    },
                    {
                        "uri": "viking://user/testuser/memories/context/20260828T090000Z.md",
                        "score": 0.85,
                        "content": "Future memory",
                        "category": "context",
                    },
                ],
            },
        }
        mock_resp = _mock_response(search_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = client_instance

            results = asyncio.run(
                self.backend.recall(
                    "memory",
                    top_k=5,
                    saved_before="2026-08-27",
                )
            )

        contents = [r["content"] for r in results]
        self.assertIn("Target memory", contents)
        self.assertNotIn("Future memory", contents)

    def test_overfetch_x3_all_levels(self):
        """search_limit is always top_k * 3 regardless of detail_level."""
        search_response = {"status": "ok", "result": {"memories": []}}
        mock_resp = _mock_response(search_response)

        for detail in ("L0", "L1", "L2"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                client_instance = AsyncMock()
                client_instance.post.return_value = mock_resp
                client_instance.__aenter__ = AsyncMock(return_value=client_instance)
                client_instance.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = client_instance

                asyncio.run(
                    self.backend.recall("query", top_k=5, detail_level=detail)
                )

            payload = client_instance.post.call_args[1]["json"]
            self.assertEqual(
                15, payload["limit"],
                f"detail_level={detail} should always use limit=15 (top_k*3)",
            )


class TestMemoryPrefix(unittest.TestCase):

    def test_prefix_uses_user(self):
        backend = OpenVikingMemoryBackend(user="myuser")
        self.assertEqual("viking://user/myuser/memories", backend._memory_prefix())

    def test_prefix_default_user(self):
        backend = OpenVikingMemoryBackend()
        self.assertEqual("viking://user/developer/memories", backend._memory_prefix())


if __name__ == "__main__":
    unittest.main()
