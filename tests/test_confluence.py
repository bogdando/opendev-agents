"""Tests for rag_mcp.backends.confluence module."""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

from rag_mcp.backends.confluence import ConfluenceBackend, _html_to_text


class TestHtmlToText(unittest.TestCase):

    def test_strips_tags(self):
        self.assertEqual("hello world", _html_to_text("<p>hello <b>world</b></p>"))

    def test_br_becomes_newline(self):
        self.assertIn("\n", _html_to_text("line1<br/>line2"))

    def test_paragraph_break(self):
        result = _html_to_text("<p>one</p><p>two</p>")
        self.assertIn("\n\n", result)

    def test_unescapes_entities(self):
        self.assertEqual("a & b", _html_to_text("a &amp; b"))

    def test_empty_string(self):
        self.assertEqual("", _html_to_text(""))


def _make_backend(spaces: list[str] | None = None) -> ConfluenceBackend:
    return ConfluenceBackend(
        base_url="https://example.atlassian.net/wiki",
        email="test@example.com",
        token="fake-token",
        spaces=spaces or ["MYSPACE"],
        max_response_chars=30000,
    )


def _confluence_page(
    title: str = "Test Page",
    body: str = "<p>test content</p>",
    space_key: str = "MYSPACE",
) -> dict:
    return {
        "title": title,
        "body": {"view": {"value": body}},
        "space": {"key": space_key},
        "version": {"number": 3},
        "_links": {"webui": f"/wiki/spaces/{space_key}/pages/12345"},
    }


class TestConfluenceListStores(unittest.TestCase):

    def test_lists_configured_spaces(self):
        backend = _make_backend(["FOO", "BAR"])
        with mock.patch.object(backend, "_get_space_info", new_callable=mock.AsyncMock) as m:
            m.return_value = {"key": "FOO", "name": "Foo Space"}
            stores = asyncio.run(backend.list_stores())

        self.assertEqual(2, len(stores))
        ids = [s["id"] for s in stores]
        self.assertIn("foo", ids)
        self.assertIn("bar", ids)

    def test_store_has_live_freshness(self):
        backend = _make_backend()
        with mock.patch.object(backend, "_get_space_info", new_callable=mock.AsyncMock) as m:
            m.return_value = {"key": "MYSPACE", "name": "My Space"}
            stores = asyncio.run(backend.list_stores())

        self.assertEqual("live", stores[0]["freshness"])
        self.assertEqual("credentialed", stores[0]["access"])


class TestConfluenceGetStore(unittest.TestCase):

    def test_returns_matching_store(self):
        backend = _make_backend(["MYSPACE"])
        with mock.patch.object(backend, "_get_space_info", new_callable=mock.AsyncMock) as m:
            m.return_value = {"key": "MYSPACE", "name": "My Space"}
            store = asyncio.run(backend.get_store("myspace"))

        self.assertIsNotNone(store)
        self.assertEqual("myspace", store["id"])

    def test_returns_none_for_unknown(self):
        backend = _make_backend(["MYSPACE"])
        with mock.patch.object(backend, "_get_space_info", new_callable=mock.AsyncMock) as m:
            m.return_value = {"key": "MYSPACE", "name": "My Space"}
            store = asyncio.run(backend.get_store("nonexistent"))

        self.assertIsNone(store)


class TestConfluenceSearch(unittest.TestCase):

    def test_returns_empty_for_unknown_store(self):
        backend = _make_backend(["MYSPACE"])
        results = asyncio.run(backend.search("test", "unknown", 5))
        self.assertEqual([], results)

    def test_formats_results(self):
        backend = _make_backend(["MYSPACE"])
        pages = [_confluence_page(title="RHOSO Guide", body="<p>operator setup</p>")]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = mock.MagicMock()
        mock_response.json.return_value = {"results": pages}

        with mock.patch.object(backend._client, "get", new_callable=mock.AsyncMock) as m:
            m.return_value = mock_response
            results = asyncio.run(backend.search("operator", "myspace", 5))

        self.assertEqual(1, len(results))
        self.assertEqual("operator setup", results[0]["text"])
        self.assertEqual("RHOSO Guide", results[0]["metadata"]["title"])
        self.assertEqual("myspace", results[0]["metadata"]["store_id"])
        self.assertIn("/wiki/spaces/MYSPACE", results[0]["source"])

    def test_truncates_at_budget(self):
        backend = ConfluenceBackend(
            base_url="https://example.atlassian.net/wiki",
            email="t@e.com",
            token="t",
            spaces=["S"],
            max_response_chars=20,
        )
        pages = [
            _confluence_page(title="P1", body="<p>" + "x" * 50 + "</p>"),
            _confluence_page(title="P2", body="<p>should not appear</p>"),
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = mock.MagicMock()
        mock_response.json.return_value = {"results": pages}

        with mock.patch.object(backend._client, "get", new_callable=mock.AsyncMock) as m:
            m.return_value = mock_response
            results = asyncio.run(backend.search("x", "s", 5))

        self.assertEqual(1, len(results))
        self.assertIn("[truncated]", results[0]["text"])

    def test_cql_escapes_quotes(self):
        backend = _make_backend(["MYSPACE"])

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = mock.MagicMock()
        mock_response.json.return_value = {"results": []}

        with mock.patch.object(backend._client, "get", new_callable=mock.AsyncMock) as m:
            m.return_value = mock_response
            asyncio.run(backend.search('test "quoted"', "myspace", 5))

        call_kwargs = m.call_args
        cql = call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {}))["cql"]
        self.assertIn('\\"quoted\\"', cql)


class TestResolveSpaceKey(unittest.TestCase):

    def test_case_insensitive_match(self):
        backend = _make_backend(["OpenstackK8S"])
        self.assertEqual("OpenstackK8S", backend._resolve_space_key("openstackk8s"))

    def test_no_match(self):
        backend = _make_backend(["MYSPACE"])
        self.assertIsNone(backend._resolve_space_key("other"))


if __name__ == "__main__":
    unittest.main()
