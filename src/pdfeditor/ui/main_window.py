"""The main application window."""

from PySide6.QtWidgets import QMainWindow, QWidget

WINDOW_TITLE = "PDF Editor"


class MainWindow(QMainWindow):
    """Top-level window of the app.

    QMainWindow is Qt's ready-made window with places for a menu bar,
    toolbars, a status bar and one central widget. It is empty for now;
    the menus and the page view arrive in milestone M1.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        # super().__init__ runs QMainWindow's own setup first. Forgetting it
        # is a classic Qt mistake that crashes as soon as the window is used.
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1000, 700)
