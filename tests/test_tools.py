"""Tests for rag_mcp.tools module (recovery hints and resource rendering)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rag_mcp.tools import (
    _build_recovery_hints,
    _find_unmatched_terms,
    _resolve_mock_file_path,
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
        mock_config.png_wrap = False
        mock_config.tiered_retrieval = False

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


class TestSearchPngWrap(unittest.TestCase):
    """Test that search() returns Image objects when png_wrap=True."""

    def _run_search_png(self, query, results, stores=None):
        if stores is None:
            stores = [{"id": "docs", "description": "Test store"}]
        mock_backend = mock.AsyncMock()
        mock_backend.list_stores.return_value = stores
        mock_backend.search.return_value = results

        mock_config = mock.MagicMock()
        mock_config.max_response_chars = 50000
        mock_config.png_wrap = True
        mock_config.png_max_pages = 3
        mock_config.png_max_chars_per_store = 4500
        mock_config.tiered_retrieval = False

        mock_app = mock.MagicMock()
        mock_app.backend = mock_backend
        mock_app.config = mock_config

        mock_ctx = mock.MagicMock()

        fake_image = mock.MagicMock()
        fake_wrap = mock.MagicMock(return_value=[fake_image])

        fake_png_mod = mock.MagicMock(
            wrap_as_images=fake_wrap,
        )

        with mock.patch(
            "rag_mcp.tools.get_app_context",
            autospec=True,
            return_value=mock_app,
        ), mock.patch.dict(
            "sys.modules",
            {"rag_mcp.png_wrap": fake_png_mod},
        ):
            return asyncio.run(search(mock_ctx, query, "docs"))

    def test_returns_list_when_png_wrap_enabled(self):
        results = [_make_result(text="some content here")]
        out = self._run_search_png("content", results)
        self.assertIsInstance(out, list)
        self.assertGreater(len(out), 0)

    def test_no_results_still_returns_string(self):
        """Recovery hints are plain text even when png_wrap is on."""
        mock_backend = mock.AsyncMock()
        mock_backend.list_stores.return_value = [
            {"id": "docs", "description": "Test"},
        ]
        mock_backend.search.return_value = []

        mock_config = mock.MagicMock()
        mock_config.max_response_chars = 50000
        mock_config.png_wrap = True
        mock_config.tiered_retrieval = False

        mock_app = mock.MagicMock()
        mock_app.backend = mock_backend
        mock_app.config = mock_config
        mock_ctx = mock.MagicMock()

        with mock.patch(
            "rag_mcp.tools.get_app_context",
            autospec=True,
            return_value=mock_app,
        ):
            out = asyncio.run(search(mock_ctx, "xyzzy", "docs"))
        self.assertIsInstance(out, str)
        self.assertIn("No results found", out)

    def test_unknown_store_still_returns_string(self):
        """Error messages stay as text regardless of png_wrap."""
        mock_backend = mock.AsyncMock()
        mock_backend.list_stores.return_value = [
            {"id": "docs", "description": "Test"},
        ]

        mock_config = mock.MagicMock()
        mock_config.max_response_chars = 50000
        mock_config.png_wrap = True
        mock_config.tiered_retrieval = False

        mock_app = mock.MagicMock()
        mock_app.backend = mock_backend
        mock_app.config = mock_config
        mock_ctx = mock.MagicMock()

        with mock.patch(
            "rag_mcp.tools.get_app_context",
            autospec=True,
            return_value=mock_app,
        ):
            out = asyncio.run(search(mock_ctx, "q", "nonexistent"))
        self.assertIsInstance(out, str)
        self.assertIn("Unknown store", out)


class TestResolveMockFilePath(unittest.TestCase):
    """Mock source is relative to knowledge_dir, not store_dir."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.knowledge_dir = Path(self._tmpdir.name)
        self.store_dir = self.knowledge_dir / "nova-docs"
        self.doc = self.store_dir / "admin" / "scheduling.rst"
        self.doc.parent.mkdir(parents=True)
        self.doc.write_text("scheduler content\n")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_source_relative_to_knowledge_dir(self):
        result = {"source": "nova-docs/admin/scheduling.rst", "metadata": {}}
        resolved = _resolve_mock_file_path(
            result, self.knowledge_dir, self.store_dir
        )
        self.assertEqual(resolved, self.doc)

    def test_store_dir_join_would_miss(self):
        """The old join (store_dir / source) does not exist."""
        source = "nova-docs/admin/scheduling.rst"
        self.assertFalse((self.store_dir / source).is_file())
        result = {"source": source, "metadata": {}}
        self.assertEqual(
            _resolve_mock_file_path(result, self.knowledge_dir, self.store_dir),
            self.doc,
        )

    def test_metadata_file_path_preferred(self):
        result = {
            "source": "wrong/path.rst",
            "metadata": {"file_path": str(self.doc)},
        }
        resolved = _resolve_mock_file_path(
            result, self.knowledge_dir, self.store_dir
        )
        self.assertEqual(resolved, self.doc)

    def test_missing_file_returns_none(self):
        result = {"source": "nova-docs/missing.rst", "metadata": {}}
        self.assertIsNone(
            _resolve_mock_file_path(result, self.knowledge_dir, self.store_dir)
        )


if __name__ == "__main__":
    unittest.main()
