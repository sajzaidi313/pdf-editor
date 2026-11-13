"""The dialog that tells the user something went wrong.

It is a plain function instead of a class so tests can swap it out: a real
message box would stop a test and wait for a click that never comes.
"""

import traceback

from PySide6.QtWidgets import QMessageBox, QWidget


def show_error(
    parent: QWidget | None, title: str, message: str, details: str = ""
) -> None:
    """Show a warning with a plain-language message.

    `details` (the technical error) is tucked away behind a "Show
    Details..." button: useless to most users, valuable in a bug report.
    """
    box = QMessageBox(
        QMessageBox.Icon.Warning, title, message, QMessageBox.StandardButton.Ok, parent
    )
    if details:
        box.setDetailedText(details)
    box.exec()  # show the box and wait until it is closed


def error_details(error: BaseException) -> str:
    """The full technical description of an error, including what caused it."""
    return "".join(traceback.format_exception(error))
