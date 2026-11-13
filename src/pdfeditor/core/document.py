"""DocumentModel: the one object that owns the open PDF.

Everything else in the app asks the model for pages instead of talking to
PyMuPDF's Document on its own. That gives one place to open and close the
file, one place that knows whether a password is still needed, and one place
that turns PyMuPDF's errors into our own (see errors.py).

This file must not import Qt (CLAUDE.md, hard rule 1).
"""

from collections.abc import Iterator
from pathlib import Path

import pymupdf

from pdfeditor.core.errors import EncryptedError, PdfOpenError


class DocumentModel:
    """Holds the currently open PDF, or nothing when no file is open."""

    def __init__(self) -> None:
        self.doc: pymupdf.Document | None = None
        self.path: Path | None = None
        # True when MuPDF had to fix a damaged file while opening it.
        self.was_repaired: bool = False
        # True while the file needs a password that has not been given yet.
        self._locked: bool = False
        # Page labels, read on first use (see _page_labels).
        self._labels: list[str] | None = None

    # --- opening and closing ------------------------------------------------

    def open(self, path: Path, password: str | None = None) -> None:
        """Open the PDF at `path`, replacing any document that was open.

        Raises PdfOpenError when the file is missing, is not a PDF, or is too
        damaged to open. In that case the previously open document stays open.

        A password-protected file opens "locked": check `needs_password` and
        call `authenticate()` before asking for pages. Passing `password`
        here tries it straight away.
        """
        new_doc = _open_pdf(path)
        self.close()
        self.doc = new_doc
        self.path = path
        self.was_repaired = bool(new_doc.is_repaired)
        # Read needs_pass exactly once, here. Reading it again after the
        # right password was given silently breaks decryption (pages come
        # out blank); see docs/04 §1. From now on only self._locked is used.
        self._locked = bool(new_doc.needs_pass)
        if password is not None:
            self.authenticate(password)

    def close(self) -> None:
        """Close the document. Does nothing when no document is open."""
        if self.doc is not None:
            self.doc.close()
        self.doc = None
        self.path = None
        self.was_repaired = False
        self._locked = False
        self._labels = None

    @property
    def is_open(self) -> bool:
        return self.doc is not None

    # --- passwords ----------------------------------------------------------

    @property
    def needs_password(self) -> bool:
        """True while the open file is waiting for its password."""
        return self._locked

    def authenticate(self, password: str) -> bool:
        """Try a password. Returns True when the document is unlocked.

        A wrong password is an ordinary event, not a bug, so it is reported
        with False instead of an exception; the UI simply asks again.
        """
        doc = self._require_doc()
        if not self._locked:
            # Already unlocked (or never locked). PyMuPDF must not be asked
            # again: a wrong password after the right one breaks decryption.
            return True
        # PyMuPDF returns 0 for a wrong password and a positive number for
        # a right one (2 = user password, 4 = owner password).
        if doc.authenticate(password) == 0:
            return False
        self._locked = False
        return True

    # --- pages --------------------------------------------------------------

    @property
    def page_count(self) -> int:
        """Number of pages, or 0 when no document is open."""
        return 0 if self.doc is None else self.doc.page_count

    def page(self, index: int) -> pymupdf.Page:
        """Return the page at `index` (0-based).

        Do not keep the returned object for long: later milestones replace
        pages (delete, reorder), which makes old Page objects invalid.
        """
        doc = self._require_unlocked_doc()
        if not 0 <= index < doc.page_count:
            raise IndexError(f"page index {index} is outside 0..{doc.page_count - 1}")
        return doc[index]

    def pages(self) -> Iterator[pymupdf.Page]:
        """Yield every page in order."""
        for index in range(self.page_count):
            yield self.page(index)

    # --- page labels ----------------------------------------------------------
    # A PDF can give its pages display names ("labels") that differ from
    # their position: a book may label its first pages i, ii, iii, iv and
    # only then start at 1. Most PDFs define no labels at all.

    @property
    def has_page_labels(self) -> bool:
        return any(self._page_labels())

    def page_label(self, index: int) -> str:
        """The label of the page at `index`, or "" when the PDF defines none."""
        labels = self._page_labels()
        if not 0 <= index < len(labels):
            raise IndexError(f"page index {index} is outside 0..{len(labels) - 1}")
        return labels[index]

    def find_page(self, text: str) -> int | None:
        """Turn what the user typed in the page box into a page index.

        Returns None when the text names no page. See find_page_index for
        the rule.
        """
        return find_page_index(text, self._page_labels(), self.page_count)

    def _page_labels(self) -> list[str]:
        """Every page's label, read once per document and then remembered."""
        if self._labels is not None:
            return self._labels
        doc = self._require_unlocked_doc()
        if doc.get_page_labels():
            labels = [str(page.get_label()) for page in doc]
        else:
            # No label rules in the file: skip loading every page.
            labels = [""] * doc.page_count
        self._labels = labels
        return labels

    # --- helpers --------------------------------------------------------------

    def _require_doc(self) -> pymupdf.Document:
        """Return the open document, or fail loudly: calling this with no
        document open is a bug in the caller, not something a user can cause."""
        if self.doc is None:
            raise RuntimeError("No document is open.")
        return self.doc

    def _require_unlocked_doc(self) -> pymupdf.Document:
        doc = self._require_doc()
        if self._locked:
            raise EncryptedError("This document is locked. Enter its password first.")
        return doc


def find_page_index(text: str, labels: list[str], page_count: int) -> int | None:
    """Find the page a typed text refers to. Returns a 0-based index or None.

    The rule (docs/11, 2026-11-12): a page *label* wins, compared without
    regard to upper/lower case, so "III" finds the page labelled "iii". If no
    label matches and the text is a whole number, it is taken as the page's
    position counted from 1. In a book labelled i, ii, iii, iv, 1, 2, ...
    typing "3" therefore goes to the page with "3" printed on it, which is
    what a reader expects.
    """
    wanted = text.strip().lower()
    if not wanted:
        return None
    for index, label in enumerate(labels):
        if label.lower() == wanted:
            return index
    try:
        number = int(wanted)
    except ValueError:
        return None
    if 1 <= number <= page_count:
        return number - 1
    return None


def _open_pdf(path: Path) -> pymupdf.Document:
    """Open `path` with PyMuPDF, or raise PdfOpenError with a friendly message."""
    name = path.name
    if path.is_dir():
        raise PdfOpenError(f'"{name}" is a folder, not a PDF file.')
    if not path.is_file():
        raise PdfOpenError(f'The file "{name}" was not found.')
    try:
        doc = pymupdf.open(path)
    except pymupdf.EmptyFileError as error:
        message = f'"{name}" is empty (0 bytes), so there is nothing to open.'
        raise PdfOpenError(message) from error
    except (pymupdf.FileDataError, pymupdf.FileNotFoundError, OSError) as error:
        # pymupdf.FileNotFoundError is PyMuPDF's own class, not Python's
        # built-in one, so it has to be named explicitly (docs/04 §13).
        message = f'"{name}" is not a valid PDF, or it is too damaged to open.'
        raise PdfOpenError(message) from error
    problem = _why_unusable(doc, name)
    if problem is not None:
        doc.close()
        raise PdfOpenError(problem)
    return doc


def _why_unusable(doc: pymupdf.Document, name: str) -> str | None:
    """Return a message when an opened file is not a PDF we can show, else None."""
    # MuPDF also opens HTML, text, images and e-books. A web error page saved
    # as "report.pdf" opens without any error, so the extension proves
    # nothing: ask the document what it is.
    if not doc.is_pdf:
        return f'"{name}" is not a PDF file. Only PDF files can be opened.'
    if doc.page_count == 0:
        return f'"{name}" has no pages.'
    return None
