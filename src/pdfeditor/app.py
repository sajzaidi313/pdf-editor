"""Application startup: read the command line, create the Qt app, show the window."""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from pdfeditor.self_test import run_self_test
from pdfeditor.ui.main_window import MainWindow

# QSettings files the app's preferences under these two names (on Windows:
# the registry key HKEY_CURRENT_USER\Software\pdfeditor\PDF Editor).
ORGANIZATION_NAME = "pdfeditor"
APPLICATION_NAME = "PDF Editor"


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    """Read the command line: an optional PDF to open, or --self-test.

    argparse checks the arguments, writes the --help text and reports
    mistakes on its own; the result has one attribute per argument.
    """
    parser = argparse.ArgumentParser(
        prog="pdfeditor", description="A desktop PDF editor."
    )
    # nargs="?" makes the file optional. type=Path converts the text to a Path.
    parser.add_argument("file", nargs="?", type=Path, help="a PDF file to open")
    # action="store_true": the flag takes no value; it is True when present.
    # argparse stores "--self-test" as `options.self_test`.
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="check that the app can open and draw a PDF, then exit",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Start the app and return its exit code once the last window closes."""
    if arguments is None:
        arguments = sys.argv[1:]  # everything after the program's own name
    options = parse_arguments(arguments)
    if options.self_test:
        return run_self_test()

    # Every Qt program needs exactly one QApplication. It owns the "event
    # loop": a loop that waits for clicks, key presses and repaint requests
    # and hands each one to the widget it belongs to.
    app = QApplication(sys.argv[:1])
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APPLICATION_NAME)

    window = MainWindow()
    window.show()
    if options.file is not None:
        # singleShot(0, ...) runs the function as soon as the event loop
        # starts, when the window is really on screen. An error dialog
        # then appears on top of the window instead of before it.
        QTimer.singleShot(0, lambda: window.open_path(options.file))

    # exec() runs the event loop. It only returns when the app quits, which
    # is why nothing after show() happens until the window is closed.
    return app.exec()
