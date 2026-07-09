"""Render text into 1568x1568 PNG frames for dense context transfer.

Each frame is a monospace-rendered page of the search results,
returned as ImageContent via FastMCP's Image helper.  This bypasses
token-budget constraints by encoding results in the vision pathway.

Text is packed using the same newline-flattening approach as txt2png:
newlines become spaces, multiple spaces are collapsed, and the flat
stream is re-wrapped to the frame width. This maximises character
density per frame compared to preserving original line breaks.

Parameters are tuned based on pxpipe's empirical findings:
- 1568px is Claude's documented vision maximum (no upscale penalty)
- 19pt font balances density with reliable retrieval
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
FONT_SIZE = 19
LINE_SPACING = 2

_USABLE_WIDTH = FRAME_SIZE - 2 * MARGIN
_USABLE_HEIGHT = FRAME_SIZE - 2 * MARGIN

_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07')


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


def _calibrate(font: ImageFont.FreeTypeFont | ImageFont.ImageFont):
    """Return (wrap_width, lines_per_frame, line_height) for the loaded font."""
    bbox = font.getbbox("Ag")
    line_h = (bbox[3] - bbox[1]) + LINE_SPACING
    char_w = font.getbbox("M")[2] - font.getbbox("M")[0]
    wrap_width = max(1, _USABLE_WIDTH // char_w - 2)
    lines_per_frame = max(1, _USABLE_HEIGHT // line_h - 1)
    return wrap_width, lines_per_frame, line_h


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


def _consume_frame(buf: str, wrap_width: int,
                   lines_per_frame: int) -> tuple[str, str]:
    """Wrap *buf* and extract exactly one frame's worth of lines.

    Returns ``(frame_text, remaining_buf)`` where *frame_text* contains
    newline-joined wrapped lines ready for rendering and *remaining_buf*
    is the unconsumed tail.
    """
    window = lines_per_frame * (wrap_width + 1) * 2
    candidate = re.sub(r"  +", " ", buf[:window])
    tail = buf[window:]

    wrapped = textwrap.wrap(candidate, width=wrap_width, break_on_hyphens=False)
    frame_lines = wrapped[:lines_per_frame]
    rest_lines = wrapped[lines_per_frame:]

    frame_text = "\n".join(frame_lines)
    remaining = " ".join(rest_lines)
    if tail:
        remaining = (remaining + " " + tail) if remaining else tail

    return frame_text, remaining


def text_to_png_frames(text: str, *, do_minify: bool = True) -> list[bytes]:
    """Split *text* into 1568x1568 PNG images, one per page.

    Newlines are replaced with spaces (newline packing) and the flat
    stream is re-wrapped to the frame width for maximum density.
    Returns a list of PNG-encoded byte buffers.
    """
    if do_minify:
        text = minify_text(text)

    font = _get_font()
    wrap_width, lines_per_frame, line_h = _calibrate(font)

    # Strip ANSI escape sequences then flatten newlines to spaces
    buf = _ANSI_RE.sub("", text)
    buf = re.sub(r"\n+", " ", buf).strip()

    frames: list[bytes] = []
    while buf.strip():
        frame_text, buf = _consume_frame(buf, wrap_width, lines_per_frame)
        if not frame_text.strip():
            break

        img = PILImage.new("RGB", (FRAME_SIZE, FRAME_SIZE), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        y = MARGIN
        for line in frame_text.splitlines():
            draw.text((MARGIN, y), line, fill=(0, 0, 0), font=font)
            y += line_h

        frames.append(_finalize_frame(img, draw, font, line_h, len(frames) + 1))

    # Patch total page count into all frames
    if len(frames) > 1:
        total = len(frames)
        patched: list[bytes] = []
        for idx, raw in enumerate(frames, 1):
            img = PILImage.open(io.BytesIO(raw))
            draw = ImageDraw.Draw(img)
            footer_y = FRAME_SIZE - MARGIN - int(line_h)
            draw.rectangle([0, footer_y, FRAME_SIZE, FRAME_SIZE], fill=(255, 255, 255))
            footer = f"— page {idx}/{total} —"
            fw = draw.textlength(footer, font=font)
            draw.text(
                ((FRAME_SIZE - fw) / 2, footer_y),
                footer, fill=(128, 128, 128), font=font,
            )
            out = io.BytesIO()
            img.save(out, format="PNG", optimize=True)
            patched.append(out.getvalue())
        frames = patched

    return frames or [_empty_frame()]


def _finalize_frame(img, draw, font, line_h: int, page_num: int) -> bytes:
    """Add a provisional page footer and serialize to PNG bytes."""
    footer = f"— page {page_num}/? —"
    fw = draw.textlength(footer, font=font)
    draw.text(
        ((FRAME_SIZE - fw) / 2, FRAME_SIZE - MARGIN - line_h),
        footer, fill=(128, 128, 128), font=font,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _empty_frame() -> bytes:
    """Return a single blank frame with a 'no results' note."""
    img = PILImage.new("RGB", (FRAME_SIZE, FRAME_SIZE), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _get_font()
    draw.text((MARGIN, MARGIN), "No results.", fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def estimate_chars_per_frame() -> int:
    """Estimate how many characters fit in one frame after minification."""
    font = _get_font()
    wrap_width, lines_per_frame, _ = _calibrate(font)
    return lines_per_frame * wrap_width


def wrap_as_images(text: str, *, max_pages: int = 3) -> list["Image"]:
    """Convert text into a list of FastMCP Image objects (PNG frames).

    Truncates output to *max_pages* frames to bound vision-token cost.
    """
    try:
        from fastmcp.utilities.types import Image
    except ImportError:
        from mcp.server.fastmcp.utilities.types import Image

    frames = text_to_png_frames(text)[:max_pages]
    return [Image(data=frame, format="png") for frame in frames]
