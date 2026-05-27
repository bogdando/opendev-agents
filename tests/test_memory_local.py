"""Tests for rag_mcp.memory.local module."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from rag_mcp.memory.local import LocalMemoryBackend


class TestRemember(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.backend = LocalMemoryBackend(str(self.root))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_remember_creates_file(self):
        result = asyncio.run(
            self.backend.remember("User prefers vim keybindings", "preference")
        )
        self.assertIn("uri", result)
        self.assertEqual("preference", result["category"])
        self.assertIn("saved_at", result)
        filepath = self.root / result["uri"]
        self.assertTrue(filepath.exists())

    def test_remember_default_category(self):
        result = asyncio.run(self.backend.remember("Some context info"))
        self.assertEqual("context", result["category"])

    def test_remember_invalid_category_defaults(self):
        result = asyncio.run(
            self.backend.remember("content", "invalid_cat")
        )
        self.assertEqual("context", result["category"])

    def test_remember_dedup(self):
        content = "Exact duplicate content"
        r1 = asyncio.run(self.backend.remember(content, "learning"))
        r2 = asyncio.run(self.backend.remember(content, "learning"))
        self.assertNotIn("deduplicated", r1)
        self.assertTrue(r2.get("deduplicated"))

    def test_remember_file_content(self):
        asyncio.run(
            self.backend.remember("Architecture uses microservices", "decision")
        )
        files = list((self.root / "decision").glob("*.md"))
        self.assertEqual(1, len(files))
        text = files[0].read_text()
        self.assertIn("category: decision", text)
        self.assertIn("saved_at:", text)
        self.assertIn("Architecture uses microservices", text)

    def test_remember_workflow_category(self):
        content = "## Deploy NFV\n1. Apply kustomization\n2. Verify bridges"
        result = asyncio.run(self.backend.remember(content, "workflow"))
        self.assertEqual("workflow", result["category"])
        filepath = self.root / result["uri"]
        self.assertTrue(filepath.exists())
        self.assertIn("Deploy NFV", filepath.read_text())


class TestRecall(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.backend = LocalMemoryBackend(str(self.root))
        asyncio.run(self._seed())

    async def _seed(self):
        await self.backend.remember(
            "User prefers dark theme and vim keybindings", "preference"
        )
        await self.backend.remember(
            "Decided to use PostgreSQL over MySQL for the project", "decision"
        )
        await self.backend.remember(
            "Nova scheduler uses filter-weigher architecture", "learning"
        )
        await self.backend.remember(
            "## Deploy RHOSO\n1. Apply edpm-nodeset\n2. Run tempest",
            "workflow",
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_recall_finds_relevant(self):
        results = asyncio.run(self.backend.recall("database PostgreSQL"))
        self.assertGreater(len(results), 0)
        contents = [r["content"] for r in results]
        self.assertTrue(
            any("PostgreSQL" in c for c in contents)
        )

    def test_recall_empty_on_no_match(self):
        results = asyncio.run(self.backend.recall("xyznonexistent"))
        self.assertEqual([], results)

    def test_recall_category_filter(self):
        results = asyncio.run(
            self.backend.recall("vim keybindings", category="preference")
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual("preference", r["category"])

    def test_recall_workflow(self):
        results = asyncio.run(
            self.backend.recall("deploy RHOSO tempest", category="workflow")
        )
        self.assertGreater(len(results), 0)
        self.assertEqual("workflow", results[0]["category"])

    def test_recall_top_k(self):
        results = asyncio.run(self.backend.recall("the", top_k=2))
        self.assertLessEqual(len(results), 2)

    def test_recall_nonexistent_dir(self):
        backend = LocalMemoryBackend("/nonexistent/path")
        results = asyncio.run(backend.recall("anything"))
        self.assertEqual([], results)

    def test_recall_result_shape(self):
        results = asyncio.run(self.backend.recall("Nova scheduler"))
        self.assertGreater(len(results), 0)
        r = results[0]
        self.assertIn("content", r)
        self.assertIn("category", r)
        self.assertIn("saved_at", r)
        self.assertIn("uri", r)


class TestListMemories(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.backend = LocalMemoryBackend(str(self.root))
        asyncio.run(self._seed())

    async def _seed(self):
        await self.backend.remember("Memory A", "preference")
        await self.backend.remember("Memory B", "decision")
        await self.backend.remember("Memory C", "context")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_list_all(self):
        results = asyncio.run(self.backend.list_memories())
        self.assertEqual(3, len(results))

    def test_list_with_category(self):
        results = asyncio.run(self.backend.list_memories(category="preference"))
        self.assertEqual(1, len(results))
        self.assertEqual("preference", results[0]["category"])

    def test_list_limit(self):
        results = asyncio.run(self.backend.list_memories(limit=2))
        self.assertEqual(2, len(results))

    def test_list_empty(self):
        backend = LocalMemoryBackend("/nonexistent")
        results = asyncio.run(backend.list_memories())
        self.assertEqual([], results)


if __name__ == "__main__":
    unittest.main()
