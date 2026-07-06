"""Tests for rag_mcp.png_wrap module."""

from __future__ import annotations

import sys
import unittest
from unittest import mock

# Ensure PIL is mockable so minify_text (pure-Python) can be tested
# even without Pillow installed.
HAS_PILLOW = True
try:
    import PIL  # noqa: F401
except ImportError:
    HAS_PILLOW = False
    _fake_pil = mock.MagicMock()
    sys.modules["PIL"] = _fake_pil
    sys.modules["PIL.Image"] = _fake_pil
    sys.modules["PIL.ImageDraw"] = _fake_pil
    sys.modules["PIL.ImageFont"] = _fake_pil
    # Force fresh import in case earlier test left a stale entry
    sys.modules.pop("rag_mcp.png_wrap", None)

from rag_mcp.png_wrap import (  # noqa: E402
    FONT_SIZE,
    FRAME_SIZE,
    minify_text,
)


class TestMinifyText(unittest.TestCase):
    """Test markdown minification for dense PNG rendering."""

    def test_strips_heading_markers(self):
        text = "## Title\n\nSome content\n### Subsection\nMore"
        out = minify_text(text)
        self.assertNotIn("##", out)
        self.assertIn("Title", out)
        self.assertIn("Subsection", out)

    def test_strips_bold_markers(self):
        text = "This is **bold** text and **more bold**."
        out = minify_text(text)
        self.assertNotIn("**", out)
        self.assertIn("bold", out)
        self.assertIn("more bold", out)

    def test_strips_italic_markers(self):
        text = "This is *italic* text."
        out = minify_text(text)
        self.assertNotIn("*", out)
        self.assertIn("italic", out)

    def test_strips_horizontal_rules(self):
        text = "Above\n\n---\n\nBelow"
        out = minify_text(text)
        self.assertNotIn("---", out)
        self.assertIn("Above", out)
        self.assertIn("Below", out)

    def test_collapses_multiple_blank_lines(self):
        text = "First\n\n\n\n\nSecond"
        out = minify_text(text)
        self.assertNotIn("\n\n\n", out)
        self.assertIn("First", out)
        self.assertIn("Second", out)

    def test_strips_trailing_whitespace(self):
        text = "line one   \nline two\t\t\n"
        out = minify_text(text)
        for line in out.splitlines():
            self.assertEqual(line.rstrip(), line)

    def test_preserves_semantic_content(self):
        text = (
            "## Deploy Nova\n\n"
            "Run **openstack** server create with *flavor* m1.large.\n\n"
            "---\n\n"
            "**Source**: docs/deploy.md"
        )
        out = minify_text(text)
        self.assertIn("Deploy Nova", out)
        self.assertIn("openstack", out)
        self.assertIn("server create", out)
        self.assertIn("flavor", out)
        self.assertIn("m1.large", out)
        self.assertIn("Source", out)

    def test_empty_input(self):
        self.assertEqual("", minify_text(""))
        self.assertEqual("", minify_text("   \n\n   "))

    def test_preserves_code_backticks(self):
        text = "Use `oc get pods` to list."
        out = minify_text(text)
        self.assertIn("`oc get pods`", out)

    def test_preserves_bullet_lists(self):
        text = "- item one\n- item two\n- item three"
        out = minify_text(text)
        self.assertIn("- item one", out)
        self.assertIn("- item two", out)

    def test_nested_bold_italic(self):
        text = "This has ***bold italic*** content."
        out = minify_text(text)
        self.assertNotIn("***", out)
        self.assertIn("bold italic", out)


class TestPngWrapConstants(unittest.TestCase):
    """Verify module-level constants are sane."""

    def test_frame_size(self):
        self.assertEqual(1568, FRAME_SIZE)

    def test_font_size(self):
        self.assertEqual(20, FONT_SIZE)

    @unittest.skipUnless(HAS_PILLOW, "Pillow not installed")
    def test_usable_dimensions_positive(self):
        from rag_mcp.png_wrap import _USABLE_HEIGHT, _USABLE_WIDTH
        self.assertGreater(_USABLE_WIDTH, 0)
        self.assertGreater(_USABLE_HEIGHT, 0)


@unittest.skipUnless(HAS_PILLOW, "Pillow not installed")
class TestTextToPngFrames(unittest.TestCase):
    """Integration tests requiring real Pillow rendering."""

    def test_short_text_single_frame(self):
        from rag_mcp.png_wrap import text_to_png_frames
        frames = text_to_png_frames("Hello world")
        self.assertEqual(1, len(frames))
        self.assertTrue(frames[0].startswith(b"\x89PNG"))

    def test_empty_text_produces_one_frame(self):
        from rag_mcp.png_wrap import text_to_png_frames
        frames = text_to_png_frames("")
        self.assertEqual(1, len(frames))

    def test_wrap_as_images_returns_image_objects(self):
        from rag_mcp.png_wrap import wrap_as_images
        images = wrap_as_images("Test content for rendering.")
        self.assertIsInstance(images, list)
        self.assertGreater(len(images), 0)


if __name__ == "__main__":
    unittest.main()
