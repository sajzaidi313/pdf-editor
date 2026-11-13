"""Putting text on the system clipboard.

A plain function in a file of its own, like the dialogs, so that tests can
swap it out: a test must not overwrite what the person running it has
copied.
"""

from PySide6.QtGui import QGuiApplication


def copy_text(text: str) -> None:
    """Make `text` what the next Paste, in any program, inserts."""
    QGuiApplication.clipboard().setText(text)
