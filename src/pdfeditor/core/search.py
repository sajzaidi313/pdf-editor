"""Finding text in a page.

PyMuPDF has a search of its own, page.search_for(), but it returns one
rectangle per *line piece*. A match that starts at the end of one line and
ends on the next comes back as two rectangles, and nothing says that they
belong together, so "3 of 17" could not be counted correctly
(tests/pymupdf_behavior/test_search.py proves it).

So the search runs over the characters that core/text.py read off the page:
join them into one long string, look for the wanted text with str.find, and
translate each match back into offsets and rectangles. Search and text
selection then always agree about where the text is.

This file must not import Qt (CLAUDE.md, hard rule 1).
"""

import bisect
from collections.abc import Sequence
from dataclasses import dataclass

import pymupdf

from pdfeditor.core.text import PageText, quads_in_range

# A hyphen at the end of a line usually means a word was split in two:
# "exam-" on one line and "ple" on the next read "example". These are the
# ordinary hyphen, the soft hyphen and the typographic hyphen.
LINE_END_HYPHENS = "-­‐"


@dataclass(frozen=True)
class SearchHit:
    """One place where the wanted text was found."""

    page_index: int
    start: int  # the range of the match in the page's text (see core/text.py)
    end: int
    quads: tuple[pymupdf.Quad, ...]  # the areas to highlight, one per line


def find_in_page(page_text: PageText, needle: str, page_index: int) -> list[SearchHit]:
    """Every place on a page where `needle` occurs, in reading order.

    Upper and lower case are treated alike, any run of spaces or a line
    break counts as one space, and a word split by a hyphen at a line end
    is found as if it were whole. Matches do not overlap.
    """
    wanted = normalize_needle(needle)
    if not wanted:
        return []
    haystack, offsets = searchable_text(page_text)
    hits: list[SearchHit] = []
    position = haystack.find(wanted)
    while position != -1:
        # offsets[i] is the page offset of the character that haystack[i]
        # came from, so the match's first and last characters give its range.
        start = offsets[position]
        end = offsets[position + len(wanted) - 1] + 1
        quads = tuple(quads_in_range(page_text, start, end))
        hits.append(SearchHit(page_index, start, end, quads))
        position = haystack.find(wanted, position + len(wanted))
    return hits


def normalize_needle(needle: str) -> str:
    """The text to look for, in the same simplified form as searchable_text().

    casefold() is lower() made for comparing: it also turns the German "ß"
    into "ss", for example. split() without arguments cuts at any run of
    whitespace and drops it at both ends.
    """
    return " ".join(needle.casefold().split())


def searchable_text(page_text: PageText) -> tuple[str, list[int]]:
    """The page as one simplified string, plus where each character came from.

    Returns (text, offsets). text[i] was made from the page character at
    offset offsets[i]. The two differ in length from the page's own text:
    runs of spaces shrink to one space, line breaks become a space, and a
    hyphen that splits a word at a line end disappears.
    """
    pieces: list[str] = []
    offsets: list[int] = []
    for index, line in enumerate(page_text.lines):
        line_start = page_text.line_starts[index]
        for position, character in enumerate(line.text):
            _append_simplified(pieces, offsets, character, line_start + position)
        if _word_continues_on_next_line(page_text, index):
            pieces.pop()  # drop the hyphen: "exam-" + "ple" reads "example"
            offsets.pop()
        else:
            last_offset = line_start + len(line.text) - 1
            _append_simplified(pieces, offsets, " ", last_offset)
    return "".join(pieces), offsets


def _append_simplified(
    pieces: list[str], offsets: list[int], character: str, offset: int
) -> None:
    if character.isspace():
        if pieces and pieces[-1] != " ":  # several spaces in a row count as one
            pieces.append(" ")
            offsets.append(offset)
        return
    # casefold() can turn one character into two ("ß" -> "ss"); both then
    # point back at the same character on the page.
    for folded in character.casefold():
        pieces.append(folded)
        offsets.append(offset)


def _word_continues_on_next_line(page_text: PageText, index: int) -> bool:
    """True when line `index` ends in a hyphen that splits a word in two."""
    if index + 1 >= len(page_text.lines):
        return False
    line = page_text.lines[index]
    next_line = page_text.lines[index + 1]
    return (
        line.text[-1] in LINE_END_HYPHENS
        and len(line.text) > 1
        and line.text[-2].isalpha()
        and next_line.block == line.block  # same paragraph
        and next_line.text[0].isalpha()
    )


def _document_order(hit: SearchHit) -> tuple[int, int]:
    return hit.page_index, hit.start


class SearchResults:
    """The hits found so far, kept in document order.

    Pages are not always searched front to back (the search starts at the
    page the user is looking at), so each page's hits are filed in their
    proper place. bisect finds that place by halving the list, without
    comparing against every hit.
    """

    def __init__(self) -> None:
        self._hits: list[SearchHit] = []

    def add(self, hits: Sequence[SearchHit]) -> None:
        """File the hits of one page, given in reading order, in their place."""
        if not hits:
            return
        position = bisect.bisect_left(
            self._hits, _document_order(hits[0]), key=_document_order
        )
        # Assigning to an empty slice inserts the whole list at that spot.
        self._hits[position:position] = hits

    def __len__(self) -> int:
        return len(self._hits)

    def on_page(self, page_index: int) -> list[SearchHit]:
        first = bisect.bisect_left(self._hits, (page_index, 0), key=_document_order)
        end = bisect.bisect_left(self._hits, (page_index + 1, 0), key=_document_order)
        return self._hits[first:end]

    def number_of(self, hit: SearchHit) -> int:
        """Position of `hit` among all hits, counted from 1 ("3 of 17")."""
        return self._index_of(hit) + 1

    def after(self, hit: SearchHit) -> SearchHit:
        """The hit following `hit`; after the last one comes the first."""
        return self._hits[(self._index_of(hit) + 1) % len(self._hits)]

    def before(self, hit: SearchHit) -> SearchHit:
        """The hit preceding `hit`; before the first one comes the last."""
        return self._hits[(self._index_of(hit) - 1) % len(self._hits)]

    def _index_of(self, hit: SearchHit) -> int:
        index = bisect.bisect_left(
            self._hits, _document_order(hit), key=_document_order
        )
        if index == len(self._hits) or self._hits[index] != hit:
            raise ValueError("This hit is not part of the results.")
        return index
