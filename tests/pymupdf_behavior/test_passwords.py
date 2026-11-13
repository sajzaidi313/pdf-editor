"""PyMuPDF behavior: password-protected files (docs/04 §1).

DocumentModel's password handling is built around these facts, including
one trap: `doc.needs_pass` is not a harmless question.
"""

import pymupdf
import pytest

USER_PASSWORD = "test"  # the passwords of encrypted_user_pw.pdf
OWNER_PASSWORD = "owner"
PROTECTED_TEXT = "This page is password protected."


@pytest.fixture
def locked_doc(fixtures_dir):
    """The encrypted fixture, freshly opened and still locked."""
    doc = pymupdf.open(fixtures_dir / "encrypted_user_pw.pdf")
    yield doc
    doc.close()


def test_encrypted_file_needs_pass_and_plain_file_does_not(locked_doc, fixtures_dir):
    assert locked_doc.needs_pass
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as plain_doc:
        assert not plain_doc.needs_pass


def test_locked_document_counts_pages_but_will_not_load_them(locked_doc):
    assert locked_doc.page_count == 1
    with pytest.raises(ValueError, match="encrypted"):
        locked_doc[0]


def test_authenticate_returns_zero_when_wrong_and_positive_when_right(locked_doc):
    assert locked_doc.authenticate("wrong") == 0
    assert locked_doc.authenticate(USER_PASSWORD) > 0


def test_owner_password_also_unlocks(locked_doc):
    assert locked_doc.authenticate(OWNER_PASSWORD) > 0
    assert PROTECTED_TEXT in locked_doc[0].get_text()


def test_wrong_attempts_before_the_right_one_do_no_harm(locked_doc):
    """The retry prompt relies on this: three tries on one open document."""
    locked_doc.authenticate("wrong")
    locked_doc.authenticate("")
    locked_doc.authenticate("also wrong")

    locked_doc.authenticate(USER_PASSWORD)

    assert PROTECTED_TEXT in locked_doc[0].get_text()


def test_authenticate_on_unprotected_file_reports_success(fixtures_dir):
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        assert doc.authenticate("anything") > 0


def test_reading_needs_pass_after_unlocking_breaks_decryption(locked_doc):
    """The trap. MuPDF answers `needs_pass` by trying an empty password, and
    a wrong password after the right one throws the key away. No exception
    is raised: pages simply come out blank.

    That is why DocumentModel reads `needs_pass` exactly once, right after
    opening. If this test ever FAILS after a PyMuPDF upgrade, the trap has
    been fixed upstream: delete this test and the warning in docs/04 §1.
    """
    locked_doc.authenticate(USER_PASSWORD)
    assert PROTECTED_TEXT in locked_doc[0].get_text()

    _ = locked_doc.needs_pass  # looks like a harmless question...

    assert locked_doc[0].get_text().strip() == ""  # ...but the text is gone
    pymupdf.TOOLS.reset_mupdf_warnings()  # drop the errors MuPDF just logged


def test_wrong_password_after_the_right_one_breaks_decryption(locked_doc):
    """Same trap through authenticate(): never try again once unlocked."""
    locked_doc.authenticate(USER_PASSWORD)

    locked_doc.authenticate("wrong")

    assert locked_doc[0].get_text().strip() == ""
    pymupdf.TOOLS.reset_mupdf_warnings()
