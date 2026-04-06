"""Tests for rag_mcp.config module."""

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
