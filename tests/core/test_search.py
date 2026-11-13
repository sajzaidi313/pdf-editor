"""core/search.py: finding text in a page and keeping the hits in order.

Page 1 of search_and_select.pdf is laid out as the lines listed at the top
of test_text.py. One "lazy dog" is split over lines 0 and 1.
"""

import pytest

from pdfeditor.core import search, text
from pdfeditor.core.search import SearchHit, SearchResults
from pdfeditor.core.text import PageText, TextLine


@pytest.fixture
def page_text(model, fixtures_dir) -> PageText:
    """The text of page 1 of search_and_select.pdf."""
    model.open(fixtures_dir / "search_and_select.pdf")
    return text.extract_page_text(model.page(0))


def made_up_page(lines: list[str], blocks: list[int] | None = None) -> PageText:
    """A PageText built by hand: every character is a 10 x 10 box.

    Handy for cases that are awkward to put into a real PDF.
    """
    blocks = blocks or [0] * len(lines)
    text_lines = []
    starts = []
    offset = 0
    for row, line in enumerate(lines):
        top = row * 20
        boxes = tuple(
            (column * 10, top, column * 10 + 10, top + 10)
            for column in range(len(line))
        )
        bbox = (0, top, len(line) * 10, top + 10)
        text_lines.append(TextLine(line, boxes, bbox, blocks[row], (1.0, 0.0)))
        starts.append(offset)
        offset += len(line)
    return PageText(tuple(text_lines), tuple(starts))


def found(page_text: PageText, needle: str) -> list[str]:
    """The text each hit covers, as it stands on the page."""
    hits = search.find_in_page(page_text, needle, page_index=0)
    return [text.text_in_range(page_text, hit.start, hit.end) for hit in hits]


# --- finding ------------------------------------------------------------------------


def test_a_hit_split_over_two_lines_is_one_hit_with_two_quads(page_text):
    hits = search.find_in_page(page_text, "lazy dog", page_index=0)

    assert len(hits) == 2
    wrapped, on_one_line = hits
    # "lazy" ends line 0 (offsets 35..39), "dog" starts line 1 (39..42).
    assert (wrapped.start, wrapped.end) == (35, 42)
    assert len(wrapped.quads) == 2
    assert (on_one_line.start, on_one_line.end) == (61, 69)
    assert len(on_one_line.quads) == 1
    assert all(hit.page_index == 0 for hit in hits)


def test_search_ignores_upper_and_lower_case(page_text):
    assert found(page_text, "FOX") == ["fox", "fox", "fox", "FOX"]
    assert found(page_text, "the QUICK") == ["The quick"]


def test_a_word_hyphenated_at_a_line_end_is_found_whole(page_text):
    (hit,) = search.find_in_page(page_text, "example", page_index=0)

    assert text.text_in_range(page_text, hit.start, hit.end) == "exam-\nple"
    assert len(hit.quads) == 2


def test_the_hyphen_of_a_split_word_cannot_be_searched_for(page_text):
    # The price of the rule above: for searching, the hyphen is not there.
    assert found(page_text, "exam-") == []
    assert found(page_text, "exam") == ["exam"]


def test_spaces_in_the_wanted_text_are_flexible(page_text):
    assert len(found(page_text, "  lazy    dog ")) == 2


def test_nothing_to_look_for_finds_nothing(page_text):
    assert found(page_text, "") == []
    assert found(page_text, "   ") == []
    assert found(page_text, "unicorn") == []


def test_hits_do_not_overlap():
    assert found(made_up_page(["aaaa"]), "aa") == ["aa", "aa"]


def test_case_folding_that_changes_the_length():
    # "ß" compares equal to "ss"; the hit still covers the 6 real characters.
    page = made_up_page(["Straße"])
    (hit,) = search.find_in_page(page, "STRASSE", page_index=3)

    assert (hit.page_index, hit.start, hit.end) == (3, 0, 6)


def test_several_spaces_on_the_page_count_as_one():
    assert found(made_up_page(["lazy    dog"]), "lazy dog") == ["lazy    dog"]


def test_a_hyphen_only_joins_within_one_block():
    same_block = made_up_page(["exam-", "ple"], blocks=[0, 0])
    two_blocks = made_up_page(["exam-", "ple"], blocks=[0, 1])

    assert found(same_block, "example") == ["exam-\nple"]
    assert found(two_blocks, "example") == []


def test_a_dash_that_is_not_part_of_a_word_stays():
    page = made_up_page(["apples -", "pears"])

    assert found(page, "applespears") == []
    assert found(page, "apples - pears") == ["apples -\npears"]


def test_searchable_text_and_its_offsets():
    page = made_up_page(["Ab  c", "D"])

    simplified, offsets = search.searchable_text(page)

    assert simplified == "ab c d "
    # "a"=0, "b"=1, first space=2 (the second space, 3, is dropped), "c"=4,
    # the line break (counted at the last character, 4), "d"=5, its line end.
    assert offsets == [0, 1, 2, 4, 4, 5, 5]


def test_normalize_needle():
    assert search.normalize_needle("  Lazy \t DOG\n") == "lazy dog"


# --- SearchResults --------------------------------------------------------------------


def hit(page_index: int, start: int) -> SearchHit:
    return SearchHit(page_index, start, start + 3, quads=())


def test_results_start_empty():
    results = SearchResults()

    assert len(results) == 0
    assert results.on_page(0) == []


def test_results_stay_in_document_order_whatever_the_order_of_adding():
    results = SearchResults()
    results.add([hit(5, 10), hit(5, 40)])
    results.add([hit(2, 7)])
    results.add([hit(9, 0)])
    results.add([])

    assert len(results) == 4
    assert results.on_page(5) == [hit(5, 10), hit(5, 40)]
    assert results.on_page(3) == []
    assert results.number_of(hit(2, 7)) == 1
    assert results.number_of(hit(5, 40)) == 3
    assert results.number_of(hit(9, 0)) == 4


def test_after_and_before_wrap_around():
    results = SearchResults()
    results.add([hit(0, 1), hit(0, 9), hit(4, 2)])

    assert results.after(hit(0, 1)) == hit(0, 9)
    assert results.after(hit(4, 2)) == hit(0, 1)  # past the end: back to the start
    assert results.before(hit(0, 9)) == hit(0, 1)
    assert results.before(hit(0, 1)) == hit(4, 2)


def test_asking_about_an_unknown_hit_is_an_error():
    results = SearchResults()
    results.add([hit(0, 1)])

    with pytest.raises(ValueError, match="not part of the results"):
        results.number_of(hit(7, 7))
