"""PyMuPDF behavior: what pymupdf.open() does with files that are not good PDFs.

DocumentModel (src/pdfeditor/core/document.py) turns each of these outcomes
into a friendly PdfOpenError, so it depends on them staying the same.
"""

import pymupdf
import pytest


def test_garbage_file_raises_file_data_error(fixtures_dir):
    """docs/04 §1 and §13: a file that is not a PDF raises FileDataError."""
    with pytest.raises(pymupdf.FileDataError):
        pymupdf.open(fixtures_dir / "not_a_pdf.pdf")


def test_empty_file_raises_empty_file_error(tmp_path):
    """docs/04 §13: a 0-byte file raises EmptyFileError, a kind of FileDataError."""
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")

    with pytest.raises(pymupdf.EmptyFileError):
        pymupdf.open(path)
    assert issubclass(pymupdf.EmptyFileError, pymupdf.FileDataError)


def test_missing_file_raises_pymupdfs_own_file_not_found_error(tmp_path):
    """docs/04 §13: pymupdf.FileNotFoundError is not Python's built-in one.

    `except FileNotFoundError:` therefore does NOT catch it; the code has to
    write `except pymupdf.FileNotFoundError:`.
    """
    with pytest.raises(pymupdf.FileNotFoundError) as caught:
        pymupdf.open(tmp_path / "does_not_exist.pdf")

    assert not isinstance(caught.value, FileNotFoundError)  # the built-in
    assert isinstance(caught.value, RuntimeError)


def test_html_saved_as_pdf_opens_but_is_not_a_pdf(tmp_path):
    """docs/04 §1: MuPDF looks at the content, not the name, and opens HTML.

    No error is raised, so `doc.is_pdf` is the only way to notice.
    """
    path = tmp_path / "download.pdf"
    path.write_bytes(b"<html><body><h1>404 Not Found</h1></body></html>")

    with pymupdf.open(path) as doc:
        assert not doc.is_pdf
        assert doc.page_count == 1


def test_image_saved_as_pdf_opens_but_is_not_a_pdf(fixtures_dir, tmp_path):
    """The same goes for a picture with a .pdf name."""
    path = tmp_path / "scan.pdf"
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        doc[0].get_pixmap().save(path, output="png")  # PNG bytes, .pdf name

    with pymupdf.open(path) as image_doc:
        assert not image_doc.is_pdf
        assert image_doc.page_count == 1


def test_real_pdf_reports_is_pdf_and_no_repair(fixtures_dir):
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        assert doc.is_pdf
        assert not doc.is_repaired


def test_wrong_startxref_is_repaired_on_open(fixtures_dir):
    """docs/04 §1: a damaged file still opens, and is_repaired says so."""
    with pymupdf.open(fixtures_dir / "broken_xref.pdf") as doc:
        assert doc.is_repaired
        assert doc.page_count == 2
        assert "Lorem ipsum" in doc[0].get_text()
