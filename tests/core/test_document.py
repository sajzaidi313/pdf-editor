"""DocumentModel: opening, closing, passwords and page labels.

These tests go through DocumentModel only, the way the rest of the app
does. What PyMuPDF itself does is pinned down in tests/pymupdf_behavior/.

`model` and `fixtures_dir` are pytest fixtures from tests/conftest.py.
"""

import shutil

import pytest

from pdfeditor.core.document import DocumentModel, find_page_index
from pdfeditor.core.errors import EncryptedError, PdfOpenError

# --- opening and closing ------------------------------------------------------


def test_new_model_has_no_document(model):
    assert not model.is_open
    assert model.path is None
    assert model.page_count == 0


def test_open_simple_text(model, fixtures_dir):
    path = fixtures_dir / "simple_text.pdf"

    model.open(path)

    assert model.is_open
    assert model.path == path
    assert model.page_count == 2
    assert "Lorem ipsum" in model.page(0).get_text()
    assert not model.was_repaired
    assert not model.needs_password


def test_rotated_pages_has_one_page_per_rotation(model, fixtures_dir):
    model.open(fixtures_dir / "rotated_pages.pdf")

    assert [page.rotation for page in model.pages()] == [0, 90, 180, 270]


def test_close_forgets_the_document(model, fixtures_dir):
    model.open(fixtures_dir / "simple_text.pdf")

    model.close()
    model.close()  # closing twice is allowed

    assert not model.is_open
    assert model.path is None
    assert model.page_count == 0


def test_opening_a_second_file_replaces_the_first(model, fixtures_dir):
    model.open(fixtures_dir / "simple_text.pdf")

    model.open(fixtures_dir / "rotated_pages.pdf")

    assert model.path == fixtures_dir / "rotated_pages.pdf"
    assert model.page_count == 4


def test_file_name_with_unicode_characters(model, fixtures_dir, tmp_path):
    # tmp_path is a built-in pytest fixture: a fresh empty folder per test.
    path = tmp_path / "ünïcødé 📄 файл.pdf"
    shutil.copy(fixtures_dir / "simple_text.pdf", path)

    model.open(path)

    assert model.page_count == 2


def test_page_index_out_of_range_raises(model, fixtures_dir):
    model.open(fixtures_dir / "simple_text.pdf")

    # pytest.raises passes only if the block raises that exception.
    with pytest.raises(IndexError):
        model.page(2)
    with pytest.raises(IndexError):
        model.page(-1)


def test_asking_for_a_page_with_nothing_open_is_a_bug():
    with pytest.raises(RuntimeError):
        DocumentModel().page(0)


# --- files that cannot be opened ----------------------------------------------


def test_not_a_pdf_raises_friendly_error(model, fixtures_dir):
    with pytest.raises(PdfOpenError) as caught:
        model.open(fixtures_dir / "not_a_pdf.pdf")

    message = str(caught.value)
    assert "not_a_pdf.pdf" in message
    assert "not a valid PDF" in message
    # The technical PyMuPDF error stays attached for the "Details" box.
    assert caught.value.__cause__ is not None
    assert not model.is_open


def test_missing_file_raises_friendly_error(model, tmp_path):
    with pytest.raises(PdfOpenError, match="was not found"):
        model.open(tmp_path / "does_not_exist.pdf")


def test_folder_instead_of_file_raises_friendly_error(model, tmp_path):
    with pytest.raises(PdfOpenError, match="is a folder"):
        model.open(tmp_path)


def test_zero_byte_file_raises_friendly_error(model, tmp_path):
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")

    with pytest.raises(PdfOpenError, match="is empty"):
        model.open(path)


def test_web_page_saved_as_pdf_raises_friendly_error(model, tmp_path):
    # A classic: a download failed and the browser saved the error page.
    # PyMuPDF opens HTML without complaint, so the model has to refuse it.
    path = tmp_path / "download.pdf"
    path.write_bytes(b"<html><body><h1>404 Not Found</h1></body></html>")

    with pytest.raises(PdfOpenError, match="is not a PDF file"):
        model.open(path)


def test_failed_open_keeps_the_current_document(model, fixtures_dir):
    good = fixtures_dir / "simple_text.pdf"
    model.open(good)

    with pytest.raises(PdfOpenError):
        model.open(fixtures_dir / "not_a_pdf.pdf")

    assert model.path == good
    assert "Lorem ipsum" in model.page(0).get_text()


def test_damaged_file_opens_and_reports_the_repair(model, fixtures_dir):
    model.open(fixtures_dir / "broken_xref.pdf")

    assert model.was_repaired
    assert model.page_count == 2
    assert "Lorem ipsum" in model.page(0).get_text()


# --- passwords ----------------------------------------------------------------

USER_PASSWORD = "test"  # the passwords of encrypted_user_pw.pdf, see its README
OWNER_PASSWORD = "owner"
PROTECTED_TEXT = "This page is password protected."


def test_encrypted_file_opens_locked(model, fixtures_dir):
    model.open(fixtures_dir / "encrypted_user_pw.pdf")

    assert model.is_open
    assert model.needs_password
    with pytest.raises(EncryptedError):
        model.page(0)


def test_wrong_password_returns_false_and_stays_locked(model, fixtures_dir):
    model.open(fixtures_dir / "encrypted_user_pw.pdf")

    assert model.authenticate("wrong") is False
    assert model.needs_password


def test_right_password_after_wrong_ones_unlocks(model, fixtures_dir):
    model.open(fixtures_dir / "encrypted_user_pw.pdf")
    model.authenticate("wrong")
    model.authenticate("")

    assert model.authenticate(USER_PASSWORD) is True

    assert not model.needs_password
    assert PROTECTED_TEXT in model.page(0).get_text()


def test_owner_password_unlocks_too(model, fixtures_dir):
    model.open(fixtures_dir / "encrypted_user_pw.pdf")

    assert model.authenticate(OWNER_PASSWORD) is True
    assert PROTECTED_TEXT in model.page(0).get_text()


def test_password_can_be_given_when_opening(model, fixtures_dir):
    model.open(fixtures_dir / "encrypted_user_pw.pdf", password=USER_PASSWORD)

    assert not model.needs_password
    assert PROTECTED_TEXT in model.page(0).get_text()


def test_document_stays_readable_after_more_password_calls(model, fixtures_dir):
    """Once unlocked, nothing the model offers may lock or break it again.

    This guards the trap described in docs/04 §1: in PyMuPDF itself a wrong
    password (or reading `needs_pass`) after the right one makes every page
    come out blank.
    """
    model.open(fixtures_dir / "encrypted_user_pw.pdf")
    model.authenticate(USER_PASSWORD)

    assert model.authenticate("wrong") is True  # already unlocked: nothing to do
    assert not model.needs_password
    assert not model.needs_password

    assert PROTECTED_TEXT in model.page(0).get_text()


def test_unprotected_file_accepts_any_password(model, fixtures_dir):
    model.open(fixtures_dir / "simple_text.pdf")

    assert model.authenticate("anything") is True


# --- page labels --------------------------------------------------------------


def test_page_labels_are_read_from_the_file(model, fixtures_dir):
    model.open(fixtures_dir / "page_labels.pdf")

    assert model.has_page_labels
    labels = [model.page_label(index) for index in range(model.page_count)]
    assert labels == ["i", "ii", "iii", "iv", "1", "2", "3", "4"]


def test_file_without_labels_has_empty_labels(model, fixtures_dir):
    model.open(fixtures_dir / "simple_text.pdf")

    assert not model.has_page_labels
    assert model.page_label(0) == ""


# parametrize runs the same test once per row: (what was typed, expected index).
@pytest.mark.parametrize(
    ("typed", "expected_index"),
    [
        ("iii", 2),  # a label
        ("III", 2),  # labels match without regard to case
        ("  iv ", 3),  # spaces around the text are ignored
        ("3", 6),  # the page *labelled* 3 wins over the third page
        ("5", 4),  # no label "5", so it means the fifth page
        ("8", 7),
        ("9", None),  # only 8 pages
        ("0", None),
        ("-1", None),
        ("zz", None),
        ("", None),
    ],
)
def test_find_page_in_labelled_document(model, fixtures_dir, typed, expected_index):
    model.open(fixtures_dir / "page_labels.pdf")

    assert model.find_page(typed) == expected_index


def test_find_page_without_labels_uses_the_page_number(model, fixtures_dir):
    model.open(fixtures_dir / "simple_text.pdf")

    assert model.find_page("2") == 1
    assert model.find_page("3") is None
    assert model.find_page("ii") is None


def test_find_page_index_is_plain_logic():
    # The rule itself needs no PDF at all.
    assert find_page_index("b", ["a", "b"], page_count=2) == 1
    assert find_page_index("2", ["", ""], page_count=2) == 1
    assert find_page_index("x", ["", ""], page_count=2) is None
