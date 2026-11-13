"""PyMuPDF behavior: page labels (docs/04 §1).

DocumentModel.page_label() and find_page() are built on these two calls.
"""

import pymupdf


def test_get_label_returns_each_pages_label(fixtures_dir):
    with pymupdf.open(fixtures_dir / "page_labels.pdf") as doc:
        labels = [page.get_label() for page in doc]

    assert labels == ["i", "ii", "iii", "iv", "1", "2", "3", "4"]


def test_document_without_labels_gives_empty_strings_and_no_rules(fixtures_dir):
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        assert doc.get_page_labels() == []
        assert doc[0].get_label() == ""


def test_document_with_labels_reports_its_rules(fixtures_dir):
    with pymupdf.open(fixtures_dir / "page_labels.pdf") as doc:
        rules = doc.get_page_labels()

    assert len(rules) == 2
