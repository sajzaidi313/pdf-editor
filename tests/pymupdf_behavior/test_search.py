"""PyMuPDF behavior: page.search_for() (docs/04 §4).

The app does *not* search with search_for. These tests pin down why
(core/search.py), and what our own search copies from it. Should a future
PyMuPDF group its results by match, the first test fails and the decision
can be looked at again.

Page 1 of search_and_select.pdf contains "lazy dog" twice: once split over
two lines, once on a single line.
"""

import pymupdf


def test_search_for_returns_line_pieces_not_matches(fixtures_dir):
    with pymupdf.open(fixtures_dir / "search_and_select.pdf") as doc:
        quads = doc[0].search_for("lazy dog", quads=True)

    # Two matches, but three quads: "lazy" / "dog" of the split match count
    # separately, and nothing in the result ties them together.
    assert len(quads) == 3


def test_search_for_ignores_case(fixtures_dir):
    with pymupdf.open(fixtures_dir / "search_and_select.pdf") as doc:
        assert len(doc[0].search_for("FOX")) == 4
        assert len(doc[0].search_for("fox")) == 4


def test_search_for_joins_a_word_hyphenated_at_a_line_end(fixtures_dir):
    with pymupdf.open(fixtures_dir / "search_and_select.pdf") as doc:
        whole_word = doc[0].search_for("example")
        with_hyphen = doc[0].search_for("exam-")

    assert len(whole_word) == 2  # "exam-" and "ple", one piece per line
    assert with_hyphen == []  # the hyphen itself cannot be found


def test_search_for_treats_runs_of_spaces_as_one(fixtures_dir):
    with pymupdf.open(fixtures_dir / "search_and_select.pdf") as doc:
        assert len(doc[0].search_for("lazy    dog")) == 3
