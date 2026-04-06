"""Tests for rag_mcp.backends.solr module (no Solr instance required)."""

from __future__ import annotations

import asyncio
import unittest

from rag_mcp.backends.solr import SolrBackend


class TestSolrBackendStoreMetadata(unittest.TestCase):

    def setUp(self):
        self.backend = SolrBackend("http://localhost:8983", 30000)

    def test_list_stores_returns_okp(self):
        stores = asyncio.run(self.backend.list_stores())
        self.assertEqual(1, len(stores))
        self.assertEqual("okp", stores[0]["id"])

    def test_store_annotations(self):
        stores = asyncio.run(self.backend.list_stores())
        s = stores[0]
        self.assertEqual("credentialed", s["access"])
        self.assertEqual("live", s["freshness"])
        self.assertIsInstance(s["coverage"], list)
        self.assertIn("documentation", s["coverage"])
        self.assertIn("solutions", s["coverage"])
        self.assertEqual(-1, s["doc_count"])

    def test_get_store_existing(self):
        store = asyncio.run(self.backend.get_store("okp"))
        self.assertIsNotNone(store)
        self.assertEqual("okp", store["id"])

    def test_get_store_missing(self):
        store = asyncio.run(self.backend.get_store("nonexistent"))
        self.assertIsNone(store)

    def test_solr_endpoint_constructed(self):
        self.assertEqual(
            "http://localhost:8983/solr/portal/select",
            self.backend._solr_endpoint,
        )


if __name__ == "__main__":
    unittest.main()
