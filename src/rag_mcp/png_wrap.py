"""Render text into 1568x1568 PNG frames for dense context transfer.

Each frame is a monospace-rendered page of the search results,
returned as ImageContent via FastMCP's Image helper.  This bypasses
token-budget constraints by encoding results in the vision pathway.

Parameters are tuned based on pxpipe's empirical findings:
- 1568px is Claude's documented vision maximum (no upscale penalty)
- 20pt font balances density with reliable retrieval (pxpipe showed
  22pt=100% accuracy, 16pt=17%; we use 20pt as safe middle ground
  that works across model families including Opus/Sonnet)
- Minification strips redundant markdown formatting before render
"""

from __future__ import annotations

import io
import re
import textwrap
from typing import TYPE_CHECKING

from PIL import Image as PILImage, ImageDraw, ImageFont

if TYPE_CHECKING:
    from fastmcp.utilities.types import Image

FRAME_SIZE = 1568
MARGIN = 20
FONT_SIZE = 20
LINE_SPACING = 3

_USABLE_WIDTH = FRAME_SIZE - 2 * MARGIN
_USABLE_HEIGHT = FRAME_SIZE - 2 * MARGIN


def _get_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a monospace font, falling back to the default bitmap font."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/liberation-mono/LiberationMono-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, FONT_SIZE)
        except OSError:
            continue
    return ImageFont.load_default()


def _measure_line_height(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    bbox = font.getbbox("Ag")
    return (bbox[3] - bbox[1]) + LINE_SPACING


def _wrap_char_width(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    """Determine how many monospace characters fit in the usable width."""
    char_w = font.getbbox("M")[2] - font.getbbox("M")[0]
    return max(1, _USABLE_WIDTH // char_w)


def minify_text(text: str) -> str:
    """Strip visual-only markdown formatting that is redundant when rendered.

    Removes heading markers, bold/italic markers, horizontal rules,
    collapses multiple blank lines, and strips trailing whitespace.
    Semantic content is preserved.
    """
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip()


def text_to_png_frames(text: str, *, do_minify: bool = True) -> list[bytes]:
    """Split *text* into 1568x1568 PNG images, one per page.

    Returns a list of PNG-encoded byte buffers.
    """
    if do_minify:
        text = minify_text(text)

    font = _get_font()
    line_h = _measure_line_height(font)
    wrap_width = _wrap_char_width(font)
    lines_per_frame = max(1, _USABLE_HEIGHT // line_h)

    wrapped_lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            wrapped_lines.append("")
        else:
            wrapped_lines.extend(textwrap.wrap(raw_line, width=wrap_width))

    frames: list[bytes] = []
    for offset in range(0, len(wrapped_lines), lines_per_frame):
        page_lines = wrapped_lines[offset : offset + lines_per_frame]
        img = PILImage.new("RGB", (FRAME_SIZE, FRAME_SIZE), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        y = MARGIN
        for line in page_lines:
            draw.text((MARGIN, y), line, fill=(0, 0, 0), font=font)
            y += line_h

        page_num = (offset // lines_per_frame) + 1
        total_pages = -(-len(wrapped_lines) // lines_per_frame)
        footer = f"— page {page_num}/{total_pages} —"
        fw = draw.textlength(footer, font=font)
        draw.text(
            ((FRAME_SIZE - fw) / 2, FRAME_SIZE - MARGIN - line_h),
            footer,
            fill=(128, 128, 128),
            font=font,
        )

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        frames.append(buf.getvalue())

    return frames or [_empty_frame()]


def _empty_frame() -> bytes:
    """Return a single blank frame with a 'no results' note."""
    img = PILImage.new("RGB", (FRAME_SIZE, FRAME_SIZE), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _get_font()
    draw.text((MARGIN, MARGIN), "No results.", fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def wrap_as_images(text: str) -> list["Image"]:
    """Convert text into a list of FastMCP Image objects (PNG frames)."""
    try:
        from fastmcp.utilities.types import Image
    except ImportError:
        from mcp.server.fastmcp.utilities.types import Image

    frames = text_to_png_frames(text)
    return [Image(data=frame, format="png") for frame in frames]
