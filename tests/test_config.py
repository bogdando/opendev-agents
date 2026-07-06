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

    def test_proxy_url_from_https_proxy(self):
        env = {"HTTPS_PROXY": "http://proxy:8080"}
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
            self.assertEqual("http://proxy:8080", cfg.proxy_url)

    def test_proxy_url_from_http_proxy(self):
        with mock.patch.dict(
            os.environ,
            {"HTTP_PROXY": "http://hp:3128"},
            clear=True,
        ):
            cfg = ServerConfig()
            self.assertEqual("http://hp:3128", cfg.proxy_url)

    def test_proxy_url_none_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = ServerConfig()
            self.assertIsNone(cfg.proxy_url)

    def test_effective_server_name_defaults_mock(self):
        cfg = ServerConfig(backend="mock")
        self.assertEqual("rag-knowledge", cfg.effective_server_name)

    def test_effective_server_name_defaults_solr(self):
        cfg = ServerConfig(backend="solr")
        self.assertEqual("rag-knowledge-okp", cfg.effective_server_name)

    def test_effective_server_name_defaults_confluence(self):
        cfg = ServerConfig(backend="confluence")
        self.assertEqual("rag-knowledge-wiki", cfg.effective_server_name)

    def test_effective_server_name_override(self):
        cfg = ServerConfig(backend="mock", server_name="custom-rag")
        self.assertEqual("custom-rag", cfg.effective_server_name)


class TestEmptyEnvFallback(unittest.TestCase):
    """Empty-string env vars fall back to field defaults."""

    def test_empty_int_fields_use_defaults(self):
        env = {
            "RAG_MCP_PORT": "",
            "RAG_MCP_MAX_RESPONSE_CHARS": "",
            "RAG_MCP_PNG_MAX_PAGES": "",
            "RAG_MCP_PNG_MAX_CHARS_PER_STORE": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
        self.assertEqual(8000, cfg.port)
        self.assertEqual(30000, cfg.max_response_chars)
        self.assertEqual(3, cfg.png_max_pages)
        self.assertEqual(4500, cfg.png_max_chars_per_store)

    def test_empty_str_fields_use_defaults(self):
        env = {
            "RAG_MCP_TRANSPORT": "",
            "RAG_MCP_BACKEND": "",
            "RAG_MCP_LOG_LEVEL": "",
            "RAG_MCP_KNOWLEDGE_DIR": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
        self.assertEqual("stdio", cfg.transport)
        self.assertEqual("mock", cfg.backend)
        self.assertEqual("INFO", cfg.log_level)
        self.assertEqual("./knowledge", cfg.knowledge_dir)

    def test_empty_bool_field_uses_default(self):
        env = {"RAG_MCP_PNG_WRAP": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
        self.assertFalse(cfg.png_wrap)

    def test_explicit_values_override_defaults(self):
        env = {
            "RAG_MCP_PORT": "9090",
            "RAG_MCP_BACKEND": "solr",
            "RAG_MCP_PNG_MAX_PAGES": "5",
            "RAG_MCP_PNG_MAX_CHARS_PER_STORE": "6000",
            "RAG_MCP_PNG_WRAP": "true",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
        self.assertEqual(9090, cfg.port)
        self.assertEqual("solr", cfg.backend)
        self.assertEqual(5, cfg.png_max_pages)
        self.assertEqual(6000, cfg.png_max_chars_per_store)
        self.assertTrue(cfg.png_wrap)

    def test_mixed_empty_and_explicit(self):
        env = {
            "RAG_MCP_PORT": "",
            "RAG_MCP_BACKEND": "confluence",
            "RAG_MCP_PNG_MAX_PAGES": "",
            "RAG_MCP_PNG_MAX_CHARS_PER_STORE": "8000",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig()
        self.assertEqual(8000, cfg.port)
        self.assertEqual("confluence", cfg.backend)
        self.assertEqual(3, cfg.png_max_pages)
        self.assertEqual(8000, cfg.png_max_chars_per_store)


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

    def test_confluence_backend_prepends_https_for_bare_hostname(self):
        from rag_mcp.backends import get_backend

        env = {
            "CONFLUENCEURL": "example.atlassian.net",
            "CONFLUENCEEMAIL": "a@b.com",
            "CONFLUENCETOKEN": "tok",
            "CONFLUENCESPACE": "SPC",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServerConfig(backend="confluence")
            backend = get_backend(cfg)
        self.assertEqual(
            "https://example.atlassian.net/wiki",
            backend._base_url,
        )


if __name__ == "__main__":
    unittest.main()
