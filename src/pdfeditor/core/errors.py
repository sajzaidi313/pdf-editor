"""The app's own exception types.

PyMuPDF raises errors with technical messages ("Failed to open file ... as
type pdf"). The core catches those and raises one of the classes below
instead, with a message that can be shown to the user as it is. The original
error stays attached (`raise ... from error`), so the full technical story
is still available for the "Details" part of an error dialog.

Having our own types also lets the UI say `except PdfOpenError:` and know it
is handling "this file could not be opened", not some unrelated bug.
"""


class PdfEditorError(Exception):
    """Base class for every error this app raises on purpose."""


class PdfOpenError(PdfEditorError):
    """A file could not be opened as a PDF. The message is written for the user."""


class EncryptedError(PdfEditorError):
    """Pages were asked for while the document is still locked by a password."""


class UnsupportedFeature(PdfEditorError):
    """The PDF uses something this app cannot handle (first used in milestone M7)."""


class SaveError(PdfEditorError):
    """A document could not be saved (first used in milestone M4)."""
