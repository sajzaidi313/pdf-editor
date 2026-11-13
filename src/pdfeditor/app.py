"""Application startup: create the Qt application and show the main window."""

import sys

from PySide6.QtWidgets import QApplication

from pdfeditor.ui.main_window import MainWindow


def main() -> int:
    """Start the app and return its exit code once the last window closes."""
    # Every Qt program needs exactly one QApplication. It owns the "event
    # loop": a loop that waits for clicks, key presses and repaint requests
    # and hands each one to the widget it belongs to.
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    # exec() runs the event loop. It only returns when the app quits, which
    # is why nothing after show() happens until the window is closed.
    return app.exec()
