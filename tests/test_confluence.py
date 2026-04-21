"""Tests for rag_mcp.backends.confluence module."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from rag_mcp.backends.confluence import (
    ConfluenceBackend,
    _html_to_text,
    _site_origin,
    _wiki_base_url,
    _wiki_phrase_fallback_cql,
    _wiki_query_tokens,
    _wiki_search_cql,
)


class TestWikiBaseUrl(unittest.TestCase):

    def test_appends_wiki_for_site_root(self):
        self.assertEqual(
            "https://example.atlassian.net/wiki",
            _wiki_base_url("https://example.atlassian.net"),
        )

    def test_preserves_explicit_wiki_suffix(self):
        self.assertEqual(
            "https://example.atlassian.net/wiki",
            _wiki_base_url("https://example.atlassian.net/wiki"),
        )

    def test_strips_trailing_slash(self):
        self.assertEqual(
            "https://example.atlassian.net/wiki",
            _wiki_base_url("https://example.atlassian.net/wiki/"),
        )

    def test_backend_normalizes_site_root(self):
        b = ConfluenceBackend(
            base_url="https://example.atlassian.net",
            email="t@e.com",
            token="t",
            spaces=["S"],
            max_response_chars=1000,
            auth_mode="basic",
        )
        self.assertEqual("https://example.atlassian.net/wiki", b._public_wiki_base)


class TestSiteOrigin(unittest.TestCase):

    def test_strips_wiki_path(self):
        self.assertEqual(
            "https://example.atlassian.net",
            _site_origin("https://example.atlassian.net/wiki"),
        )

    def test_site_root(self):
        self.assertEqual(
            "https://example.atlassian.net",
            _site_origin("https://example.atlassian.net"),
        )


class TestConfluenceOAuth(unittest.TestCase):

    def test_oauth_sends_bearer_and_accept_json(self):
        b = ConfluenceBackend(
            base_url="https://example.atlassian.net",
            email="",
            token="oauth-access-token",
            spaces=["S"],
            max_response_chars=1000,
            auth_mode="oauth",
            cloud_id="cid-1111-2222",
        )
        self.assertEqual(
            "Bearer oauth-access-token",
            b._client.headers.get("Authorization"),
        )
        self.assertEqual("application/json", b._client.headers.get("Accept"))

    def test_basic_does_not_set_bearer_header(self):
        b = ConfluenceBackend(
            base_url="https://example.atlassian.net",
            email="u@e.com",
            token="classic-token",
            spaces=["S"],
            max_response_chars=1000,
            auth_mode="basic",
        )
        self.assertIsNone(b._client.headers.get("Authorization"))
        self.assertIsNotNone(b._client.auth)

    def test_oauth_gateway_from_cloud_id(self):
        b = ConfluenceBackend(
            base_url="https://example.atlassian.net/wiki",
            email="",
            token="t",
            spaces=["S"],
            max_response_chars=1000,
            auth_mode="oauth",
            cloud_id="aaa-bbbb-cccc-dddd",
        )
        out = asyncio.run(b._ensure_oauth_api_base())
        self.assertEqual(
            "https://api.atlassian.com/ex/confluence/aaa-bbbb-cccc-dddd",
            out,
        )

    def test_oauth_discover_gateway_from_accessible_resources(self):
        b = ConfluenceBackend(
            base_url="https://example.atlassian.net",
            email="",
            token="t",
            spaces=["S"],
            max_response_chars=1000,
            auth_mode="oauth",
            cloud_id="",
        )
        ar = mock.MagicMock()
        ar.status_code = 200
        ar.raise_for_status = mock.MagicMock()
        ar.json.return_value = [
            {
                "id": "discovered-cloud-id",
                "url": "https://example.atlassian.net",
                "scopes": ["read:confluence-content.all"],
            },
        ]

        async def _run():
            with mock.patch.object(b._client, "get", new_callable=mock.AsyncMock) as m:
                m.return_value = ar
                out = await b._ensure_oauth_api_base()
            self.assertEqual(
                "https://api.atlassian.com/ex/confluence/discovered-cloud-id",
                out,
            )
            m.assert_called()
            call_urls = [c.args[0] for c in m.call_args_list]
            self.assertIn(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                call_urls,
            )

        asyncio.run(_run())


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
        auth_mode="basic",
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
            auth_mode="basic",
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
        # Non-empty first response so phrase fallback does not run (fallback
        # would use the full query string as one CQL literal).
        mock_response.json.return_value = {"results": [_confluence_page()]}

        with mock.patch.object(backend._client, "get", new_callable=mock.AsyncMock) as m:
            m.return_value = mock_response
            asyncio.run(backend.search('test "quoted"', "myspace", 5))

        call_kwargs = m.call_args
        cql = call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {}))["cql"]
        self.assertIn('text ~ "test"', cql)
        self.assertIn('text ~ "quoted"', cql)
        self.assertIn("title ~", cql)

    def test_phrase_fallback_when_and_returns_nothing(self):
        backend = _make_backend(["MYSPACE"])
        empty = mock.MagicMock()
        empty.status_code = 200
        empty.raise_for_status = mock.MagicMock()
        empty.json.return_value = {"results": []}
        hit = mock.MagicMock()
        hit.status_code = 200
        hit.raise_for_status = mock.MagicMock()
        hit.json.return_value = {"results": [_confluence_page()]}

        with mock.patch.object(backend._client, "get", new_callable=mock.AsyncMock) as m:
            m.side_effect = [empty, hit]
            results = asyncio.run(backend.search("foo bar", "myspace", 5))

        self.assertEqual(2, m.call_count)
        self.assertEqual(1, len(results))


class TestWikiCqlHelpers(unittest.TestCase):

    def test_search_cql_and_tokens_title_or_text(self):
        cql = _wiki_search_cql("RHOSO", ["nova", "cell"])
        self.assertIn('space = "RHOSO"', cql)
        self.assertIn('type in ("page", "blogpost")', cql)
        self.assertIn('(text ~ "nova" OR title ~ "nova")', cql)
        self.assertIn('(text ~ "cell" OR title ~ "cell")', cql)
        self.assertIn("order by lastModified desc", cql)

    def test_query_tokens_strips_quotes(self):
        self.assertEqual(["test", "quoted"], _wiki_query_tokens('test "quoted"'))

    def test_phrase_fallback_cql(self):
        cql = _wiki_phrase_fallback_cql("S", "hello world")
        self.assertIn('space = "S"', cql)
        self.assertIn('text ~ "hello world"', cql)

    def test_phrase_fallback_escapes_inner_quotes(self):
        cql = _wiki_phrase_fallback_cql("S", "say \"hi\"")
        self.assertIn('\\"hi\\"', cql)


class TestResolveSpaceKey(unittest.TestCase):

    def test_case_insensitive_match(self):
        backend = _make_backend(["OpenstackK8S"])
        self.assertEqual("OpenstackK8S", backend._resolve_space_key("openstackk8s"))

    def test_no_match(self):
        backend = _make_backend(["MYSPACE"])
        self.assertIsNone(backend._resolve_space_key("other"))


if __name__ == "__main__":
    unittest.main()
