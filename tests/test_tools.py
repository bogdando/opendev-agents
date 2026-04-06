"""Tests for rag_mcp.tools module (recovery hints and resource rendering)."""

from __future__ import annotations

import unittest

from rag_mcp.tools import _build_recovery_hints


def _make_stores() -> list[dict]:
    return [
        {"id": "docs", "description": "Community documentation"},
        {"id": "code", "description": "Architecture and specs"},
        {"id": "okp", "description": "Red Hat KB articles"},
    ]


class TestBuildRecoveryHints(unittest.TestCase):

    def test_multi_word_query_suggests_broader_terms(self):
        out = _build_recovery_hints("cyborg accelerator driver", "docs", _make_stores())
        self.assertIn('"cyborg"', out)
        self.assertIn('"accelerator"', out)
        self.assertIn('"driver"', out)
        self.assertIn("Try broader terms", out)

    def test_single_word_query_no_broader_suggestion(self):
        out = _build_recovery_hints("xyznonexistent", "docs", _make_stores())
        self.assertNotIn("Try broader terms", out)

    def test_other_stores_suggested(self):
        out = _build_recovery_hints("test", "docs", _make_stores())
        self.assertIn('"code"', out)
        self.assertIn('"okp"', out)
        self.assertNotIn('Try a different store: "docs"', out)

    def test_searched_store_in_header(self):
        out = _build_recovery_hints("query", "docs", _make_stores())
        self.assertIn('in store "docs"', out)

    def test_available_stores_listed(self):
        out = _build_recovery_hints("query", "docs", _make_stores())
        self.assertIn("Available stores: docs, code, okp", out)

    def test_single_store_no_alternatives(self):
        stores = [{"id": "only", "description": "The only store"}]
        out = _build_recovery_hints("query", "only", stores)
        self.assertNotIn("Try a different store", out)
        self.assertIn("Available stores: only", out)

    def test_suggestions_header_present(self):
        out = _build_recovery_hints("query", "docs", _make_stores())
        self.assertIn("**Suggestions**:", out)


class TestRecoveryHintsFormat(unittest.TestCase):
    """Verify the output matches the spec example structure."""

    def test_format_matches_spec_pattern(self):
        out = _build_recovery_hints("cyborg accelerator API", "openstack-docs", [
            {"id": "openstack-docs", "description": "Community docs, API refs"},
            {"id": "openstack-code", "description": "Architecture decisions and specs"},
        ])
        lines = out.strip().split("\n")
        self.assertIn("No results found for", lines[0])
        self.assertEqual("", lines[1])
        self.assertEqual("**Suggestions**:", lines[2])
        for line in lines[3:]:
            self.assertTrue(line.startswith("- "), f"Expected bullet: {line!r}")


if __name__ == "__main__":
    unittest.main()
