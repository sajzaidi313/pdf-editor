"""The main toolbar and its go-to-page box."""

from collections.abc import Sequence

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFocusEvent
from PySide6.QtWidgets import QLabel, QLineEdit, QToolBar, QWidget


def page_box_text(page_index: int, page_count: int, label: str) -> str:
    """What the page box shows for a page.

    A PDF without page labels just shows the page number: "4". With labels
    it shows the label first and the position after it: "iv (4 of 120)".
    """
    number = page_index + 1
    if label:
        return f"{label} ({number} of {page_count})"
    return str(number)


class PageBox(QLineEdit):
    """A small text box: shows the current page, and jumps to the page the
    user types (a number or a page label) when Enter is pressed."""

    # Emitted with the typed text when the user presses Enter.
    page_entered = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(130)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip("Go to page: type a page number or label, then press Enter")
        self.returnPressed.connect(self._emit_page_entered)

    def _emit_page_entered(self) -> None:
        self.page_entered.emit(self.text())

    def focusInEvent(self, event: QFocusEvent) -> None:
        """Select the whole text when the box is clicked, so typing replaces it."""
        super().focusInEvent(event)
        # A mouse click places the text cursor *after* this event, which
        # would undo a selection made now. singleShot(0, ...) runs the
        # function a moment later, once Qt has finished handling the click.
        QTimer.singleShot(0, self.selectAll)


class MainToolBar(QToolBar):
    """[Open] | Page: [ box ] | [zoom buttons]

    The buttons are QActions made by the main window. An action is one
    command (its text, shortcut and what it does); putting the same action
    in a menu and on a toolbar keeps the two in step.
    """

    def __init__(
        self,
        open_action: QAction,
        zoom_actions: Sequence[QAction],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Main toolbar", parent)
        self.setMovable(False)
        self.page_box = PageBox(self)
        self.addAction(open_action)
        self.addSeparator()
        self.addWidget(QLabel(" Page: ", self))
        self.addWidget(self.page_box)
        self.addSeparator()
        for action in zoom_actions:
            self.addAction(action)
