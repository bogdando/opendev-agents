"""Tests for rag_mcp.tools module (recovery hints and resource rendering)."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from rag_mcp.tools import (
    _build_recovery_hints,
    _find_unmatched_terms,
    search,
)


def _make_stores() -> list[dict]:
    return [
        {"id": "docs", "description": "Community documentation"},
        {"id": "code", "description": "Architecture and specs"},
        {"id": "okp", "description": "Red Hat KB articles"},
    ]


def _make_result(
    title: str = "Doc", text: str = "body", source: str = "s.md"
) -> dict:
    return {
        "text": text,
        "source": source,
        "metadata": {"title": title, "store_id": "docs"},
    }


class TestFindUnmatchedTerms(unittest.TestCase):
    """Tests for the _find_unmatched_terms helper."""

    def test_all_terms_present(self):
        results = [_make_result(text="nova triage bugs")]
        self.assertEqual(
            [], _find_unmatched_terms("triage bugs nova", results)
        )

    def test_one_term_missing(self):
        results = [_make_result(text="triage bugs report")]
        unmatched = _find_unmatched_terms(
            "triage bugs cyborg", results
        )
        self.assertEqual(["cyborg"], unmatched)

    def test_multiple_terms_missing(self):
        results = [_make_result(text="nova compute manager")]
        unmatched = _find_unmatched_terms(
            "cyborg accelerator nova", results
        )
        self.assertIn("cyborg", unmatched)
        self.assertIn("accelerator", unmatched)
        self.assertNotIn("nova", unmatched)

    def test_single_meaningful_term_returns_empty(self):
        results = [_make_result(text="unrelated content")]
        self.assertEqual(
            [], _find_unmatched_terms("cyborg", results)
        )

    def test_stop_words_filtered(self):
        results = [_make_result(text="triage report")]
        unmatched = _find_unmatched_terms(
            "how to triage in cyborg", results
        )
        self.assertNotIn("how", unmatched)
        self.assertNotIn("to", unmatched)
        self.assertNotIn("in", unmatched)
        self.assertIn("cyborg", unmatched)

    def test_short_words_filtered(self):
        results = [_make_result(text="triage report")]
        unmatched = _find_unmatched_terms(
            "db triage cyborg", results
        )
        self.assertNotIn("db", unmatched)
        self.assertIn("cyborg", unmatched)

    def test_case_insensitive(self):
        results = [_make_result(text="Cyborg Accelerator")]
        self.assertEqual(
            [],
            _find_unmatched_terms("cyborg accelerator", results),
        )

    def test_all_stop_words_returns_empty(self):
        results = [_make_result(text="something")]
        self.assertEqual(
            [], _find_unmatched_terms("how to do", results)
        )

    def test_checks_all_results(self):
        results = [
            _make_result(text="nova triage"),
            _make_result(text="cyborg driver"),
        ]
        self.assertEqual(
            [],
            _find_unmatched_terms("triage cyborg", results),
        )

    def test_empty_results_list(self):
        unmatched = _find_unmatched_terms("triage cyborg", [])
        self.assertIn("triage", unmatched)
        self.assertIn("cyborg", unmatched)

    def test_substring_match_counts(self):
        results = [_make_result(text="cyborgian scheduler")]
        unmatched = _find_unmatched_terms(
            "cyborg scheduler", results
        )
        self.assertNotIn("cyborg", unmatched)
        self.assertNotIn("scheduler", unmatched)

    def test_no_substring_match(self):
        results = [_make_result(text="triaging cybernetics")]
        unmatched = _find_unmatched_terms(
            "triage cyborg", results
        )
        self.assertIn("triage", unmatched)
        self.assertIn("cyborg", unmatched)


class TestSearchHintIntegration(unittest.TestCase):
    """Test that search() appends unmatched-term hints."""

    def _run_search(self, query, results, stores=None):
        """Run search() with mocked backend and context."""
        if stores is None:
            stores = [
                {
                    "id": "docs",
                    "description": "Test store",
                },
            ]
        mock_backend = mock.AsyncMock()
        mock_backend.list_stores.return_value = stores
        mock_backend.search.return_value = results

        mock_config = mock.MagicMock()
        mock_config.max_response_chars = 50000

        mock_app = mock.MagicMock()
        mock_app.backend = mock_backend
        mock_app.config = mock_config

        mock_ctx = mock.MagicMock()

        with mock.patch(
            "rag_mcp.tools.get_app_context",
            autospec=True,
            return_value=mock_app,
        ):
            return asyncio.run(
                search(mock_ctx, query, "docs")
            )

    def test_hint_appended_when_term_missing(self):
        results = [
            _make_result(text="nova triage bugs report"),
        ]
        out = self._run_search("triage bugs cyborg", results)
        self.assertIn("No documents in store", out)
        self.assertIn('"cyborg"', out)
        self.assertIn("matched only the", out)

    def test_no_hint_when_all_terms_present(self):
        results = [
            _make_result(text="nova triage bugs report"),
        ]
        out = self._run_search("triage bugs nova", results)
        self.assertNotIn("No documents in store", out)

    def test_no_hint_for_single_term(self):
        results = [_make_result(text="nova compute")]
        out = self._run_search("cyborg", results)
        self.assertNotIn("No documents in store", out)

    def test_hint_with_stop_words_in_query(self):
        results = [
            _make_result(text="triage bugs report"),
        ]
        out = self._run_search(
            "how to triage bugs in cyborg", results
        )
        self.assertIn('"cyborg"', out)
        self.assertNotIn('"how"', out)

    def test_no_results_returns_recovery_hints(self):
        stores = [
            {"id": "docs", "description": "Test store"},
            {"id": "other", "description": "Other store"},
        ]
        out = self._run_search("xyzzy", [], stores)
        self.assertIn("No results found", out)
        self.assertIn("**Suggestions**:", out)

    def test_results_still_contain_original_content(self):
        results = [
            _make_result(
                title="Triage Guide",
                text="How to triage bugs",
            ),
        ]
        out = self._run_search("triage bugs cyborg", results)
        self.assertIn("## Triage Guide", out)
        self.assertIn("How to triage bugs", out)
        self.assertIn("No documents in store", out)


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
