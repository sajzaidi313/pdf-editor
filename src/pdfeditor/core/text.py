"""Text on a page: where every character sits, hit-testing and selection.

A PDF has no paragraphs and no words. It only says "draw this letter
shape at this spot", thousands of times (docs/03). MuPDF works out which
letters form a line and hands back each character with its box. This file
turns that into a PageText and answers the questions the mouse asks:

- which character is under this point?
- which characters lie between these two points?
- what do they say, and which rectangles cover them?

Positions in the text are *offsets*: an offset counts the characters of
the page from its start and names the gap in front of that character, like
the text cursor in an editor. Offset 0 is before the first character. A
range (start, end) covers the characters from `start` up to, but not
including, `end`.

Everything here is in unrotated PDF points, and the file must not import
Qt (CLAUDE.md, hard rules 1 and 3).
"""

import bisect
import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, cast

import pymupdf

# A rectangle as plain numbers: left, top, right, bottom.
Box = tuple[float, float, float, float]

# What MuPDF should do while reading the text. Starting from PyMuPDF's
# defaults for "rawdict", two things are switched off:
# - TEXT_PRESERVE_LIGATURES: a ligature is one glyph for several letters,
#   such as "fi" drawn as a single shape. Off means it comes back as the
#   letters "f" and "i", so searching for "office" and copying both work.
# - TEXT_PRESERVE_IMAGES: pictures are not text.
EXTRACT_FLAGS = (
    pymupdf.TEXTFLAGS_RAWDICT
    & ~pymupdf.TEXT_PRESERVE_LIGATURES
    & ~pymupdf.TEXT_PRESERVE_IMAGES
)

# How far outside a line's box, in points, the pointer still counts as
# being on that line.
LINE_SLACK = 2.0

# Characters that belong to a word besides letters and digits.
EXTRA_WORD_CHARACTERS = "_'’"  # underscore, apostrophe, curly apostrophe


@dataclass(frozen=True)
class TextLine:
    """One line of text as MuPDF found it."""

    text: str  # the line's characters, in reading order
    boxes: tuple[Box, ...]  # one box per character of `text`
    bbox: Box  # the box around the whole line
    block: int  # number of the paragraph-like block the line belongs to
    direction: tuple[float, float]  # (1, 0) for ordinary left-to-right text


@dataclass(frozen=True)
class PageText:
    """Every line of a page, plus the offset at which each line starts."""

    lines: tuple[TextLine, ...]
    line_starts: tuple[int, ...]

    @property
    def is_empty(self) -> bool:
        """True for a page without text, such as a scan."""
        return not self.lines

    @property
    def char_count(self) -> int:
        if not self.lines:
            return 0
        return self.line_starts[-1] + len(self.lines[-1].text)


# --- reading the text off a page -------------------------------------------------


def extract_page_text(page: pymupdf.Page) -> PageText:
    """Read all characters of `page` with their boxes.

    "rawdict" is PyMuPDF's most detailed text format: blocks contain
    lines, lines contain spans (runs in one font), spans contain single
    characters. The boxes are in unrotated coordinates even on a rotated
    page, like everything in core/.
    """
    raw = read_rawdict(page)
    lines: list[TextLine] = []
    for block in raw["blocks"]:
        if block["type"] != 0:  # 0 is a text block, 1 an image
            continue
        for raw_line in block["lines"]:
            line = _make_line(raw_line, block["number"])
            if line is not None:
                lines.append(line)
    line_starts: list[int] = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line.text)
    return PageText(tuple(lines), tuple(line_starts))


def read_rawdict(page: pymupdf.Page, flags: int = EXTRACT_FLAGS) -> dict[str, Any]:
    """page.get_text("rawdict") with a return type the type checker accepts.

    get_text() returns a string, a list or a dict depending on its first
    argument. A type checker only sees "one of the three", and would then
    object to raw["blocks"]. cast() tells it which one this is; it changes
    nothing while the program runs.
    """
    return cast(dict[str, Any], page.get_text("rawdict", flags=flags))


def _make_line(raw_line: dict[str, Any], block: int) -> TextLine | None:
    chars = [char for span in raw_line["spans"] for char in span["chars"]]
    if not chars:
        return None
    x0, y0, x1, y1 = raw_line["bbox"]
    direction_x, direction_y = raw_line["dir"]
    return TextLine(
        text="".join(char["c"] for char in chars),
        boxes=tuple(char["bbox"] for char in chars),
        bbox=(x0, y0, x1, y1),
        block=block,
        direction=(direction_x, direction_y),
    )


# --- from a point to a position in the text --------------------------------------


def offset_at(page_text: PageText, point: pymupdf.Point) -> int | None:
    """The offset nearest to `point`, or None when the page has no text.

    The point may be anywhere, even off the page: dragging past the end of
    a line selects up to its end, as in a text editor.
    """
    line_index = _line_near(page_text, point)
    if line_index is None:
        return None
    line = page_text.lines[line_index]
    return page_text.line_starts[line_index] + _gap_in_line(line, point)


def is_over_text(page_text: PageText, point: pymupdf.Point) -> bool:
    """True when `point` is on a line of text (for the I-beam cursor)."""
    return _line_under(page_text, point) is not None


def word_range_at(page_text: PageText, point: pymupdf.Point) -> tuple[int, int] | None:
    """The range of the word under `point` (for a double-click).

    Returns None when the point is not on text or is on a space. A
    character that is no letter or digit, such as a comma, is a "word" of
    its own.
    """
    line_index = _line_under(page_text, point)
    if line_index is None:
        return None
    line = page_text.lines[line_index]
    index = _char_near(line, point)
    if line.text[index].isspace():
        return None
    start, end = index, index + 1
    if _is_word_character(line.text[index]):
        while start > 0 and _is_word_character(line.text[start - 1]):
            start -= 1
        while end < len(line.text) and _is_word_character(line.text[end]):
            end += 1
    line_start = page_text.line_starts[line_index]
    return line_start + start, line_start + end


def line_range_at(page_text: PageText, point: pymupdf.Point) -> tuple[int, int] | None:
    """The range of the whole line under `point` (for a triple-click)."""
    line_index = _line_under(page_text, point)
    if line_index is None:
        return None
    start = page_text.line_starts[line_index]
    return start, start + len(page_text.lines[line_index].text)


def _distance_to_box(box: Box, point: pymupdf.Point) -> tuple[float, float]:
    """How far `point` is outside `box`, sideways and up/down. (0, 0) = inside."""
    x0, y0, x1, y1 = box
    sideways = max(x0 - point.x, 0.0, point.x - x1)
    up_down = max(y0 - point.y, 0.0, point.y - y1)
    return sideways, up_down


def _line_near(page_text: PageText, point: pymupdf.Point) -> int | None:
    """Index of the line a drag at `point` should land on; None without text."""

    def badness(index: int) -> tuple[bool, float]:
        sideways, up_down = _distance_to_box(page_text.lines[index].bbox, point)
        # Python compares tuples entry by entry and False sorts before
        # True. So a line level with the pointer always wins over one
        # above or below it, however close that one is. Dragging to the
        # right of a short last line then selects that line to its end,
        # instead of jumping to the longer line above.
        return up_down > 0, math.hypot(sideways, up_down)

    return min(range(len(page_text.lines)), key=badness, default=None)


def _line_under(page_text: PageText, point: pymupdf.Point) -> int | None:
    """Index of the line `point` is on (give or take LINE_SLACK), else None."""
    line_index = _line_near(page_text, point)
    if line_index is None:
        return None
    sideways, up_down = _distance_to_box(page_text.lines[line_index].bbox, point)
    if sideways > LINE_SLACK or up_down > LINE_SLACK:
        return None
    return line_index


def _gap_in_line(line: TextLine, point: pymupdf.Point) -> int:
    """How many of the line's characters come before `point`."""
    direction_x, direction_y = line.direction
    for index, (x0, y0, x1, y1) in enumerate(line.boxes):
        # How far the point lies beyond the middle of this character,
        # measured along the direction the line runs in. For ordinary text
        # the direction is (1, 0) and this is simply point.x - middle x.
        beyond_middle = (point.x - (x0 + x1) / 2) * direction_x + (
            point.y - (y0 + y1) / 2
        ) * direction_y
        if beyond_middle < 0:
            return index
    return len(line.boxes)


def _char_near(line: TextLine, point: pymupdf.Point) -> int:
    """Index of the line's character whose box is nearest to `point`."""

    def distance(index: int) -> float:
        return math.hypot(*_distance_to_box(line.boxes[index], point))

    return min(range(len(line.boxes)), key=distance)


def _is_word_character(character: str) -> bool:
    return character.isalnum() or character in EXTRA_WORD_CHARACTERS


# --- from a range to its text and its rectangles ---------------------------------


def text_in_range(page_text: PageText, start: int, end: int) -> str:
    """The characters from offset `start` up to `end`, one line per text line."""
    return "\n".join(
        line.text[first:last]
        for line, first, last in _line_slices(page_text, start, end)
    )


def quads_in_range(page_text: PageText, start: int, end: int) -> list[pymupdf.Quad]:
    """The areas covering the characters of a range: one per line it touches.

    A Quad is a four-cornered shape; unlike a Rect it may be tilted, which
    is why PDF text markup uses quads. One per line, not one big rectangle
    around everything: that would also cover the text left of the first
    selected word and right of the last one.
    """
    quads: list[pymupdf.Quad] = []
    for line, first, last in _line_slices(page_text, start, end):
        boxes = line.boxes[first:last]
        covering = pymupdf.Rect(
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        )
        quads.append(covering.quad)
    return quads


def _line_slices(
    page_text: PageText, start: int, end: int
) -> Iterator[tuple[TextLine, int, int]]:
    """For every line a range touches: the line and which part of it is inside.

    Yields (line, first, last), meaning line.text[first:last] is selected.
    """
    # bisect finds the last line that starts at or before `start` without
    # looking at every line (see geometry.visible_pages for how).
    first_line = max(bisect.bisect_right(page_text.line_starts, start) - 1, 0)
    for index in range(first_line, len(page_text.lines)):
        line_start = page_text.line_starts[index]
        if line_start >= end:
            break
        line = page_text.lines[index]
        first = max(start - line_start, 0)
        last = min(end - line_start, len(line.text))
        if first < last:
            yield line, first, last
