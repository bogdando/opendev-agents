"""Tests for rag_mcp.formatting module."""

from __future__ import annotations

import unittest

from rag_mcp.formatting import format_results


def _make_result(
    title: str = "Test Title",
    text: str = "body",
    source: str = "src.md",
    score: float | None = None,
) -> dict:
    r: dict = {
        "text": text,
        "source": source,
        "metadata": {"title": title},
    }
    if score is not None:
        r["score"] = score
    return r


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

    def test_score_rendered_when_present(self):
        out = format_results([_make_result(score=0.85)], 30000)
        self.assertIn("relevance: 0.85", out)

    def test_score_omitted_when_absent(self):
        out = format_results([_make_result()], 30000)
        self.assertNotIn("relevance", out)

    def test_scores_shown_for_each_result(self):
        results = [
            _make_result(title="A", score=1.0),
            _make_result(title="B", score=0.5),
        ]
        out = format_results(results, 30000)
        self.assertIn("## A  (relevance: 1.00)", out)
        self.assertIn("## B  (relevance: 0.50)", out)


if __name__ == "__main__":
    unittest.main()
