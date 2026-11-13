"""PyMuPDF behavior: the outline, read with doc.get_toc() (docs/04 §1).

DocumentModel.outline() is built on these facts.
"""

import pymupdf


def test_get_toc_rows_are_level_title_and_page_counted_from_one(fixtures_dir):
    with pymupdf.open(fixtures_dir / "outline_nested.pdf") as doc:
        toc = doc.get_toc()

    assert toc[:3] == [
        [1, "Chapter 1", 1],
        [2, "Section 1.1", 2],
        [3, "Detail 1.1.1", 3],
    ]


def test_a_bookmark_without_target_has_page_minus_one(fixtures_dir):
    with pymupdf.open(fixtures_dir / "outline_nested.pdf") as doc:
        assert doc.get_toc()[-1] == [1, "Lost bookmark", -1]


def test_document_without_outline_gives_an_empty_list(fixtures_dir):
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        assert doc.get_toc() == []


def test_deleting_a_page_leaves_its_bookmark_pointing_nowhere(fixtures_dir):
    with pymupdf.open(fixtures_dir / "outline_nested.pdf") as doc:
        doc.delete_page(4)  # the page "Chapter 2" points to
        toc = doc.get_toc()

    assert [1, "Chapter 2", -1] in toc
    # The entries before it are untouched, the one after it moved up a page.
    assert toc[3] == [2, "Section 1.2", 4]
    assert [2, "Section 2.1", 5] in toc
