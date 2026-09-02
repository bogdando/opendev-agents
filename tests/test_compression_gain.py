"""Tests for compression gain check in rag_mcp.formatting module."""

from __future__ import annotations

import unittest

from rag_mcp.formatting import (
    _has_compression_gain,
    _select_content,
)


def _meta(l0: str | None = None, l1: str | None = None) -> dict:
    m: dict = {}
    if l0 is not None:
        m["l0_summary"] = l0
    if l1 is not None:
        m["l1_summary"] = l1
    return m


class TestHasCompressionGain(unittest.TestCase):

    def test_shorter_summary_has_gain(self):
        self.assertTrue(
            _has_compression_gain("short", "much longer original text here"),
        )

    def test_longer_summary_has_no_gain(self):
        self.assertFalse(
            _has_compression_gain(
                "a very long summary that exceeds the original", "short"
            ),
        )

    def test_equal_length_has_no_gain(self):
        self.assertFalse(_has_compression_gain("same", "same"))

    def test_empty_summary_has_no_gain(self):
        self.assertFalse(_has_compression_gain("", "original"))

    def test_empty_original_has_no_gain(self):
        self.assertFalse(_has_compression_gain("summary", ""))


class TestSelectContentCompressionGain(unittest.TestCase):

    def test_l0_with_gain_returns_summary(self):
        full = "x" * 500
        result = _select_content(full, _meta(l0="Short L0"), "L0")
        self.assertEqual(result, "Short L0")

    def test_l0_no_gain_returns_original(self):
        full = "short"
        result = _select_content(full, _meta(l0="verbose L0 " * 10), "L0")
        self.assertEqual(result, full)

    def test_l1_with_gain_returns_summary(self):
        full = "x" * 500
        result = _select_content(full, _meta(l1="Brief overview"), "L1")
        self.assertEqual(result, "Brief overview")

    def test_l1_no_gain_returns_original(self):
        full = "short"
        result = _select_content(full, _meta(l1="verbose L1 " * 10), "L1")
        self.assertEqual(result, full)

    def test_l2_always_returns_original(self):
        full = "original"
        result = _select_content(
            full, _meta(l0="x" * 9999, l1="x" * 9999), "L2"
        )
        self.assertEqual(result, full)

    def test_l0_no_sidecar_uses_extractive(self):
        full = "First sentence. Second sentence. Third."
        result = _select_content(full, {}, "L0")
        self.assertIn("First sentence.", result)
        self.assertNotEqual(result, full)

    def test_l1_no_sidecar_uses_extractive(self):
        full = "x" * 3000
        result = _select_content(full, {}, "L1")
        self.assertLessEqual(len(result), 2000)

    def test_content_id_accepted(self):
        full = "short"
        result = _select_content(
            full, _meta(l1="verbose " * 20), "L1", content_id="doc.md"
        )
        self.assertEqual(result, full)


class TestSelectContentRealWorld(unittest.TestCase):

    def test_short_memory_fallback(self):
        original = "Set ENV=foo"
        l1 = (
            "The adoption process requires environment variables "
            "to be configured before execution."
        )
        result = _select_content(original, _meta(l1=l1), "L1")
        self.assertEqual(result, original)

    def test_yaml_config_fallback(self):
        original = "# Config\nkey: value\nbackup: true"
        l1 = (
            "The configuration file defines control plane settings "
            "with specific focus on MariaDB database backend."
        )
        result = _select_content(original, _meta(l1=l1), "L1")
        self.assertEqual(result, original)

    def test_workflow_with_gain(self):
        original = (
            "To upgrade Nova:\n"
            "1. Drain VMs\n2. Update packages\n"
            "3. Verify services\nTakes 4 hours."
        )
        l1 = "Nova upgrade: drain, update, verify"
        result = _select_content(original, _meta(l1=l1), "L1")
        self.assertEqual(result, l1)


if __name__ == "__main__":
    unittest.main()
