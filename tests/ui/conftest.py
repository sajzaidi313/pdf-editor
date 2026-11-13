"""Pytest fixtures shared by the GUI tests.

Two rules keep GUI tests safe to run anywhere:

- No test may touch the real settings of the person running it. Every
  window gets a throwaway settings file instead.
- No test may open a real dialog: it would wait forever for a click. The
  two dialog functions are replaced by stand-ins that record what happened.
  monkeypatch (a built-in pytest fixture) swaps them and puts the originals
  back after each test.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QSettings

from pdfeditor.ui.dialogs import error_dialog, password_dialog
from pdfeditor.ui.main_window import MainWindow
from pdfeditor.ui.page_view import PageView


@pytest.fixture
def settings(tmp_path) -> QSettings:
    """A settings store in the test's own temporary folder."""
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def shown_errors(monkeypatch) -> list[tuple[str, str]]:
    """Replaces the error dialog. Holds (title, message) of each error "shown"."""
    errors: list[tuple[str, str]] = []

    def record_error(parent, title, message, details=""):
        errors.append((title, message))

    monkeypatch.setattr(error_dialog, "show_error", record_error)
    return errors


class PasswordPrompt:
    """Stand-in for the password dialog.

    A test puts what the "user" will type into `answers` (None = Cancel).
    `wrong_before_flags` records, per prompt, whether the dialog would have
    said that the previous password was wrong.
    """

    def __init__(self) -> None:
        self.answers: list[str | None] = []
        self.wrong_before_flags: list[bool] = []

    def ask(self, parent, file_name, wrong_before):
        self.wrong_before_flags.append(wrong_before)
        # pop(0) with nothing left raises: an unexpected prompt fails the
        # test instead of hanging it.
        return self.answers.pop(0)


@pytest.fixture
def password_prompt(monkeypatch) -> PasswordPrompt:
    prompt = PasswordPrompt()
    monkeypatch.setattr(password_dialog, "ask_password", prompt.ask)
    return prompt


# `qtbot` comes from pytest-qt. Asking for it makes sure a QApplication
# exists, which Qt requires before any widget is created.
@pytest.fixture
def window(qtbot, settings, shown_errors, password_prompt) -> Iterator[MainWindow]:
    """A shown main window with test settings and stand-in dialogs."""
    main_window = MainWindow(settings=settings)
    qtbot.addWidget(main_window)  # qtbot destroys the window after the test
    main_window.show()
    qtbot.waitExposed(main_window)
    yield main_window
    main_window.close()  # closes the open PDF as well


@pytest.fixture
def view(qtbot, model) -> Iterator[PageView]:
    """A shown, empty PageView of a fixed size."""
    page_view = PageView()
    qtbot.addWidget(page_view)
    page_view.resize(900, 700)
    page_view.show()
    qtbot.waitExposed(page_view)
    yield page_view
    # The view must let go of the document before the `model` fixture
    # closes it. Otherwise a redraw still waiting on the view's timer would
    # ask a closed document for pages. The main window follows the same
    # order when it closes.
    page_view.set_document(None)
