"""Tests for rag_mcp.formatting module."""

from __future__ import annotations

import unittest

from rag_mcp.formatting import format_results


def _make_result(title: str = "Test Title", text: str = "body", source: str = "src.md") -> dict:
    return {"text": text, "source": source, "metadata": {"title": title}}


class TestFormatResults(unittest.TestCase):

    def test_empty_results(self):
        self.assertEqual("No results found.", format_results([], 30000))

    def test_single_result(self):
        out = format_results([_make_result()], 30000)
        self.assertIn("## Test Title", out)
        self.assertIn("body", out)
        self.assertIn("**Source**: src.md", out)

    def test_multiple_results_separated(self):
        results = [_make_result(title=f"T{i}") for i in range(3)]
        out = format_results(results, 30000)
        self.assertIn("## T0", out)
        self.assertIn("## T1", out)
        self.assertIn("## T2", out)
        self.assertEqual(2, out.count("---"))

    def test_budget_truncation(self):
        results = [_make_result(text="x" * 500, title=f"T{i}") for i in range(10)]
        out = format_results(results, 1200)
        self.assertIn("Budget reached", out)
        self.assertNotIn("## T9", out)

    def test_missing_metadata_uses_defaults(self):
        result = {"text": "content", "source": "s.md"}
        out = format_results([result], 30000)
        self.assertIn("## Untitled", out)

    def test_missing_source_uses_unknown(self):
        result = {"text": "content", "metadata": {"title": "T"}}
        out = format_results([result], 30000)
        self.assertIn("**Source**: unknown", out)


if __name__ == "__main__":
    unittest.main()
