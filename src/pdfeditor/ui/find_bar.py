"""The find bar: a strip under the toolbar for searching the document.

    Find: [ text ............ ]  Previous  Next   3 of 17   Close

The bar itself knows nothing about PDFs. It only tells whoever listens
what the user wants: "search for this", "next", "previous", "I was
closed". The FindController (find_controller.py) does the searching.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeyEvent
from PySide6.QtWidgets import QLabel, QLineEdit, QToolBar, QWidget

# How long to wait after the last keystroke before searching. Searching on
# every single letter of a word would start, and throw away, a search for
# each one.
SEARCH_DELAY_MS = 300


def find_status(number: int, total: int, searching: bool) -> str:
    """The text beside the find box, for example "3 of 17".

    `number` is the position of the current hit (0 when there is none yet).
    A trailing "…" says that the search is still running and the total may
    grow.
    """
    if total == 0:
        return "Searching…" if searching else "No matches"
    still_counting = "…" if searching else ""
    return f"{number} of {total}{still_counting}"


class FindBox(QLineEdit):
    """The text box of the find bar. Enter and Escape get special meaning."""

    # Emitted on Enter; the value is True when Shift was held.
    enter_pressed = Signal(bool)
    escape_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.enter_pressed.emit(shift_held)
        elif event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
        else:
            super().keyPressEvent(event)  # ordinary typing


class FindBar(QToolBar):
    """Hidden until Edit > Find opens it."""

    search_requested = Signal(str)  # the text to look for has changed
    next_requested = Signal()
    previous_requested = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Find bar", parent)
        self.setMovable(False)
        self.box = FindBox(self)
        self.box.setPlaceholderText("Find in document")
        self.box.setClearButtonEnabled(True)
        self.box.setFixedWidth(260)
        self.status_label = QLabel(self)
        self.previous_action = QAction("Previous", self)
        self.previous_action.setToolTip("Previous match (Shift+Enter)")
        self.next_action = QAction("Next", self)
        self.next_action.setToolTip("Next match (Enter)")
        self.close_action = QAction("Close", self)
        self.close_action.setToolTip("Close the find bar (Esc)")
        self._lay_out()
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.setInterval(SEARCH_DELAY_MS)
        self._delay.timeout.connect(self._request_search)
        # textEdited fires when the *user* changes the text, not when the
        # program does. The lambda drops the new text the signal passes.
        self.box.textEdited.connect(lambda _text: self._delay.start())
        self.box.enter_pressed.connect(self._on_enter)
        self.box.escape_pressed.connect(self.close_bar)
        self.previous_action.triggered.connect(lambda: self.previous_requested.emit())
        self.next_action.triggered.connect(lambda: self.next_requested.emit())
        self.close_action.triggered.connect(lambda: self.close_bar())
        self.hide()

    def _lay_out(self) -> None:
        self.addWidget(QLabel(" Find: ", self))
        self.addWidget(self.box)
        self.addAction(self.previous_action)
        self.addAction(self.next_action)
        self.addWidget(self.status_label)
        self.addSeparator()
        self.addAction(self.close_action)

    # --- used by the main window and the controller -----------------------------

    def open_bar(self) -> None:
        """Show the bar and put the text cursor into its box."""
        self.show()
        self.box.setFocus()
        self.box.selectAll()  # typing replaces what was searched before

    def close_bar(self) -> None:
        self._delay.stop()
        self.hide()
        self.closed.emit()

    def text(self) -> str:
        return self.box.text()

    def set_status(self, status: str) -> None:
        self.status_label.setText(f"  {status}  " if status else "")

    def status(self) -> str:
        return self.status_label.text().strip()

    # --- helpers ----------------------------------------------------------------

    def _request_search(self) -> None:
        self.search_requested.emit(self.box.text())

    def _on_enter(self, shift_held: bool) -> None:
        if self._delay.isActive():
            # Enter came before the typing delay ran out: search right now.
            self._delay.stop()
            self._request_search()
        elif shift_held:
            self.previous_requested.emit()
        else:
            self.next_requested.emit()
