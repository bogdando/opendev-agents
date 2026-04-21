"""Tests for rag_mcp.config module."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from rag_mcp.config import ServerConfig


class TestServerConfig(unittest.TestCase):

    def test_defaults(self):
        cfg = ServerConfig()
        self.assertEqual("stdio", cfg.transport)
        self.assertEqual("mock", cfg.backend)
        self.assertEqual("./knowledge", cfg.knowledge_dir)
        self.assertEqual("http://localhost:8983", cfg.solr_url)
        self.assertEqual(30000, cfg.max_response_chars)
        self.assertEqual("oauth", cfg.confluence_auth)

    def test_backend_literal_accepts_mock(self):
        cfg = ServerConfig(backend="mock")
        self.assertEqual("mock", cfg.backend)

    def test_backend_literal_accepts_solr(self):
        cfg = ServerConfig(backend="solr")
        self.assertEqual("solr", cfg.backend)

    def test_max_response_chars_minimum(self):
        cfg = ServerConfig(max_response_chars=1)
        self.assertEqual(1, cfg.max_response_chars)

    def test_confluence_short_env_names(self):
        env = {
            "CONFLUENCEURL": "https://x.atlassian.net/wiki",
            "CONFLUENCEEMAIL": "a@b.com",
            "CONFLUENCETOKEN": "tok",
            "CONFLUENCESPACE": "S1,S2",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
        self.assertEqual("https://x.atlassian.net/wiki", cfg.confluence_url)
        self.assertEqual("a@b.com", cfg.confluence_email)
        self.assertEqual("tok", cfg.confluence_token)
        self.assertEqual("S1,S2", cfg.confluence_space)

    def test_confluence_auth_oauth_env(self):
        env = {
            "CONFLUENCEURL": "https://x.atlassian.net",
            "CONFLUENCETOKEN": "tok",
            "CONFLUENCESPACE": "S",
            "CONFLUENCEAUTH": "oauth",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
        self.assertEqual("oauth", cfg.confluence_auth)

    def test_confluence_cloud_id_env(self):
        env = {
            "CONFLUENCECLOUDID": "aaa-bbbb-cccc-dddd",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
        self.assertEqual("aaa-bbbb-cccc-dddd", cfg.confluence_cloud_id)


class TestBackendFactory(unittest.TestCase):

    def test_mock_backend(self):
        from rag_mcp.backends import get_backend
        cfg = ServerConfig(backend="mock", knowledge_dir="/tmp")
        backend = get_backend(cfg)
        self.assertIsNotNone(backend)

    def test_solr_backend(self):
        from rag_mcp.backends import get_backend
        cfg = ServerConfig(backend="solr")
        backend = get_backend(cfg)
        self.assertIsNotNone(backend)

    def test_unknown_backend_raises(self):
        from rag_mcp.backends import get_backend
        cfg = ServerConfig.__new__(ServerConfig)
        object.__setattr__(cfg, "backend", "unknown")
        object.__setattr__(cfg, "knowledge_dir", "/tmp")
        object.__setattr__(cfg, "solr_url", "http://localhost")
        object.__setattr__(cfg, "max_response_chars", 30000)
        with self.assertRaises(ValueError):
            get_backend(cfg)

    def test_confluence_oauth_ok_without_email(self):
        from rag_mcp.backends import get_backend

        env = {
            "RAG_MCP_BACKEND": "confluence",
            "CONFLUENCEURL": "https://x.atlassian.net/wiki",
            "CONFLUENCEEMAIL": "",
            "CONFLUENCETOKEN": "oauth-token",
            "CONFLUENCEAUTH": "oauth",
            "CONFLUENCESPACE": "S",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
            backend = get_backend(cfg)
        self.assertIsNotNone(backend)

    def test_confluence_basic_requires_email(self):
        from rag_mcp.backends import get_backend

        env = {
            "RAG_MCP_BACKEND": "confluence",
            "CONFLUENCEURL": "https://x.atlassian.net/wiki",
            "CONFLUENCEEMAIL": "",
            "CONFLUENCETOKEN": "tok",
            "CONFLUENCEAUTH": "basic",
            "CONFLUENCESPACE": "S",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
            with self.assertRaises(ValueError) as ctx:
                get_backend(cfg)
        self.assertIn("CONFLUENCEEMAIL", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
