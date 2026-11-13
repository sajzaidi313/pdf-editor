"""core/text.py: reading a page's characters, hit-testing and selection.

Most tests use page 1 of search_and_select.pdf (tests/fixtures/README.md).
Its text is laid out as these lines; the number in front is the offset at
which each line starts:

      0  "The quick brown fox jumps over the lazy"
     39  "dog and then the very lazy dog sleeps for"
     80  "a long while under the old oak tree near"
    120  "the river bank."
    135  "This is an exam-"
    151  "ple of hyphenation."
    170  "fox fox FOX"
"""

import pymupdf
import pytest

from pdfeditor.core import text
from pdfeditor.core.text import PageText, TextLine

LINES = [
    "The quick brown fox jumps over the lazy",
    "dog and then the very lazy dog sleeps for",
    "a long while under the old oak tree near",
    "the river bank.",
    "This is an exam-",
    "ple of hyphenation.",
    "fox fox FOX",
]
LINE_STARTS = [0, 39, 80, 120, 135, 151, 170]


@pytest.fixture
def page_text(model, fixtures_dir) -> PageText:
    """The text of page 1 of search_and_select.pdf."""
    model.open(fixtures_dir / "search_and_select.pdf")
    return text.extract_page_text(model.page(0))


def point_on(page_text: PageText, line: int, column: int, across: float = 0.5):
    """A point on one character: `across` 0.0 is its left edge, 1.0 its right."""
    x0, y0, x1, y1 = page_text.lines[line].boxes[column]
    return pymupdf.Point(x0 + (x1 - x0) * across, (y0 + y1) / 2)


def a_range(result: tuple[int, int] | None) -> tuple[int, int]:
    """word_range_at and line_range_at may return None. Where a test
    expects a range, this fails clearly instead of at the unpacking."""
    assert result is not None
    return result


# --- reading the text off a page ------------------------------------------------


def test_extract_gives_the_lines_in_reading_order(page_text):
    assert [line.text for line in page_text.lines] == LINES
    assert list(page_text.line_starts) == LINE_STARTS
    assert page_text.char_count == 181
    assert not page_text.is_empty


def test_lines_of_one_paragraph_share_a_block(page_text):
    assert [line.block for line in page_text.lines] == [0, 0, 0, 0, 1, 1, 2]


def test_every_character_has_a_box_inside_its_line(page_text):
    for line in page_text.lines:
        assert len(line.boxes) == len(line.text)
        line_x0, line_y0, line_x1, line_y1 = line.bbox
        for x0, y0, x1, y1 in line.boxes:
            assert line_x0 - 0.01 <= x0 <= x1 <= line_x1 + 0.01
            assert line_y0 - 0.01 <= y0 <= y1 <= line_y1 + 0.01
    first_box = page_text.lines[0].boxes[0]
    assert first_box[0] == pytest.approx(72)  # the paragraph starts at x = 72


def test_text_on_a_rotated_page_keeps_unrotated_positions(model, fixtures_dir):
    model.open(fixtures_dir / "search_and_select.pdf")
    upright = text.extract_page_text(model.page(1))  # "Second page: ..."
    rotated = text.extract_page_text(model.page(2))  # rotated by 90 degrees

    assert model.page(2).rotation == 90
    assert rotated.lines[0].text == "A lazy dog on a rotated page."
    # Both pages were written with their first line starting at (72, 90),
    # and that is where both report it, rotated or not.
    assert rotated.lines[0].bbox[:2] == pytest.approx(upright.lines[0].bbox[:2])
    assert rotated.lines[0].direction == (1.0, 0.0)


def test_scanned_page_has_no_text(model, fixtures_dir):
    model.open(fixtures_dir / "scanned_no_text.pdf")
    scanned = text.extract_page_text(model.page(0))

    assert scanned.is_empty
    assert scanned.char_count == 0
    assert text.offset_at(scanned, pymupdf.Point(100, 85)) is None
    assert not text.is_over_text(scanned, pymupdf.Point(100, 85))
    assert text.word_range_at(scanned, pymupdf.Point(100, 85)) is None
    assert text.text_in_range(scanned, 0, 10) == ""
    assert text.quads_in_range(scanned, 0, 10) == []


# --- from a point to a position ---------------------------------------------------


def test_offset_is_before_a_character_when_the_point_is_on_its_left_half(page_text):
    # Line 0, column 4 is the "q" of "quick".
    assert text.offset_at(page_text, point_on(page_text, 0, 4, across=0.2)) == 4
    assert text.offset_at(page_text, point_on(page_text, 0, 4, across=0.8)) == 5


def test_offset_on_a_later_line_counts_the_lines_before_it(page_text):
    # Line 1 starts at offset 39; its column 0 is the "d" of "dog".
    assert text.offset_at(page_text, point_on(page_text, 1, 0, across=0.2)) == 39
    assert text.offset_at(page_text, point_on(page_text, 1, 2, across=0.8)) == 42


def test_point_right_of_a_line_gives_the_end_of_that_line(page_text):
    x0, y0, x1, y1 = page_text.lines[0].bbox

    assert text.offset_at(page_text, pymupdf.Point(x1 + 100, (y0 + y1) / 2)) == 39


def test_point_left_of_a_line_gives_its_start(page_text):
    x0, y0, x1, y1 = page_text.lines[2].bbox

    assert text.offset_at(page_text, pymupdf.Point(x0 - 50, (y0 + y1) / 2)) == 80


def test_point_beside_a_short_line_stays_on_that_line(page_text):
    # Line 3 ("the river bank.") is short. A point far to its right is
    # closer to the long line above, but it is level with line 3, and that
    # is the line a reader means.
    x0, y0, x1, y1 = page_text.lines[3].bbox
    beside = pymupdf.Point(280, (y0 + y1) / 2)

    assert text.offset_at(page_text, beside) == 120 + len("the river bank.")


def test_points_above_and_below_all_text_give_the_nearest_line(page_text):
    assert text.offset_at(page_text, pymupdf.Point(72, 0)) == 0
    assert text.offset_at(page_text, pymupdf.Point(500, 780)) == 181


def test_offset_follows_the_direction_of_sideways_text():
    # Two characters written bottom to top: "a" sits below "b". The line's
    # direction (0, -1) says that reading goes upward.
    line = TextLine(
        text="ab",
        boxes=((10, 90, 20, 100), (10, 80, 20, 90)),
        bbox=(10, 80, 20, 100),
        block=0,
        direction=(0.0, -1.0),
    )
    sideways = PageText(lines=(line,), line_starts=(0,))

    assert text.offset_at(sideways, pymupdf.Point(15, 97)) == 0  # low on the "a"
    assert text.offset_at(sideways, pymupdf.Point(15, 92)) == 1  # high on the "a"
    assert text.offset_at(sideways, pymupdf.Point(15, 82)) == 2  # high on the "b"


def test_is_over_text_only_on_a_line(page_text):
    assert text.is_over_text(page_text, point_on(page_text, 0, 4))
    assert not text.is_over_text(page_text, pymupdf.Point(400, 80))  # right margin
    assert not text.is_over_text(page_text, pymupdf.Point(100, 180))  # between blocks


# --- words and lines ----------------------------------------------------------------


def test_word_range_covers_the_word_under_the_point(page_text):
    start, end = a_range(text.word_range_at(page_text, point_on(page_text, 0, 6)))

    assert (start, end) == (4, 9)
    assert text.text_in_range(page_text, start, end) == "quick"


def test_word_range_leaves_out_the_full_stop(page_text):
    # Line 3 is "the river bank."; column 11 is the "a" of "bank".
    start, end = a_range(text.word_range_at(page_text, point_on(page_text, 3, 11)))

    assert text.text_in_range(page_text, start, end) == "bank"


def test_punctuation_is_a_word_of_its_own(page_text):
    start, end = a_range(text.word_range_at(page_text, point_on(page_text, 3, 14)))

    assert text.text_in_range(page_text, start, end) == "."


def test_no_word_on_a_space_or_away_from_text(page_text):
    assert text.word_range_at(page_text, point_on(page_text, 0, 3)) is None  # a space
    assert text.word_range_at(page_text, pymupdf.Point(400, 80)) is None


def test_line_range_covers_the_whole_line(page_text):
    start, end = a_range(text.line_range_at(page_text, point_on(page_text, 1, 10)))

    assert (start, end) == (39, 80)
    assert text.text_in_range(page_text, start, end) == LINES[1]
    assert text.line_range_at(page_text, pymupdf.Point(400, 80)) is None


# --- from a range to text and rectangles ----------------------------------------------


def test_text_in_range_within_one_line(page_text):
    assert text.text_in_range(page_text, 4, 9) == "quick"


def test_text_in_range_across_lines_has_one_line_per_text_line(page_text):
    # From "quick" on line 0 to the end of "dog" on line 1.
    assert text.text_in_range(page_text, 4, 42) == (
        "quick brown fox jumps over the lazy\ndog"
    )


def test_text_of_the_whole_page(page_text):
    assert text.text_in_range(page_text, 0, page_text.char_count) == "\n".join(LINES)


def test_empty_and_out_of_range_ranges(page_text):
    assert text.text_in_range(page_text, 7, 7) == ""
    assert text.quads_in_range(page_text, 7, 7) == []
    assert text.text_in_range(page_text, 170, 5000) == "fox fox FOX"


def test_quads_in_range_gives_one_quad_per_line(page_text):
    quads = text.quads_in_range(page_text, 4, 42)

    assert len(quads) == 2
    first, second = (quad.rect for quad in quads)
    # The first quad runs from the "q" to the end of line 0 ...
    assert first.x0 == pytest.approx(page_text.lines[0].boxes[4][0])
    assert first.x1 == pytest.approx(page_text.lines[0].bbox[2])
    # ... the second from the start of line 1 to the end of "dog".
    assert second.x0 == pytest.approx(72)
    assert second.x1 == pytest.approx(page_text.lines[1].boxes[2][2])
    assert second.y0 > first.y0


def test_quad_of_a_single_word_is_as_wide_as_the_word(page_text):
    (quad,) = text.quads_in_range(page_text, 4, 9)

    assert quad.rect.x0 == pytest.approx(page_text.lines[0].boxes[4][0])
    assert quad.rect.x1 == pytest.approx(page_text.lines[0].boxes[8][2])
