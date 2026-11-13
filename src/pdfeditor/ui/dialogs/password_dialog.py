"""The dialog that asks for a PDF's password.

A plain function, for the same reason as error_dialog.py: tests replace it.

The password is returned to the caller and nothing else: it is never
written to the settings or to a log (docs/09 §1).
"""

from PySide6.QtWidgets import QInputDialog, QLineEdit, QWidget


def ask_password(
    parent: QWidget | None, file_name: str, wrong_before: bool
) -> str | None:
    """Ask for the password of `file_name`.

    Returns the typed text, or None when the user cancelled. `wrong_before`
    adds a line saying that the previous attempt did not work.
    """
    prompt = (
        f'"{file_name}" is protected by a password.\nEnter the password to open it:'
    )
    if wrong_before:
        prompt = "That password did not work. Please try again.\n\n" + prompt
    # EchoMode.Password shows dots instead of the typed characters.
    text, accepted = QInputDialog.getText(
        parent, "Password required", prompt, QLineEdit.EchoMode.Password
    )
    return text if accepted else None
