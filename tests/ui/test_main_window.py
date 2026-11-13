"""The main window: title, status bar, page box, menus' commands.

The `window` fixture (tests/ui/conftest.py) is a shown MainWindow with
throwaway settings and stand-in dialogs.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from pdfeditor.ui.main_window import status_text
from pdfeditor.ui.toolbar import page_box_text


def status_of(window) -> str:
    return window._status_label.text()


def type_in_page_box(qtbot, window, text: str) -> None:
    """Replace the page box's text and press Enter, like a user would."""
    box = window.toolbar.page_box
    box.setFocus()
    box.selectAll()
    qtbot.keyClicks(box, text)
    qtbot.keyClick(box, Qt.Key.Key_Return)


# --- the empty window -----------------------------------------------------------


def test_main_window_opens_with_title(window):
    assert window.isVisible()
    assert window.windowTitle() == "PDF Editor"


def test_empty_window_has_nothing_to_zoom_or_page_through(window):
    assert status_of(window) == ""
    assert not window.zoom_in_action.isEnabled()
    assert not window.next_page_action.isEnabled()
    assert not window.toolbar.page_box.isEnabled()
    assert window.open_action.isEnabled()


# --- with a document ------------------------------------------------------------


def test_opening_a_file_shows_it(window, fixtures_dir):
    assert window.open_path(fixtures_dir / "simple_text.pdf") is True

    assert window.windowTitle() == "simple_text.pdf - PDF Editor"
    assert window.view.page_count == 2
    assert status_of(window) == "Page 1 / 2 · 100%"
    assert window.toolbar.page_box.text() == "1"
    assert window.zoom_in_action.isEnabled()
    assert window.next_page_action.isEnabled()


def test_status_bar_follows_zoom_and_page(window, fixtures_dir):
    window.open_path(fixtures_dir / "simple_text.pdf")

    # trigger() runs an action as if its menu entry had been clicked.
    window.zoom_in_action.trigger()
    window.zoom_in_action.trigger()
    window.next_page_action.trigger()

    assert status_of(window) == "Page 2 / 2 · 125%"
    assert window.toolbar.page_box.text() == "2"


def test_view_menu_commands(window, fixtures_dir):
    window.open_path(fixtures_dir / "page_labels.pdf")

    window.last_page_action.trigger()
    assert window.view.current_page == 7
    window.previous_page_action.trigger()
    assert window.view.current_page == 6
    window.first_page_action.trigger()
    assert window.view.current_page == 0

    window.zoom_out_action.trigger()
    assert window.view.zoom == 0.9
    window.actual_size_action.trigger()
    assert window.view.zoom == 1.0
    window.fit_width_action.trigger()
    assert window.view.zoom != 1.0
    window.fit_page_action.trigger()
    assert window.view.current_page == 0


def test_status_text_format():
    assert status_text(page_index=2, page_count=120, zoom=1.25) == "Page 3 / 120 · 125%"
    assert status_text(page_index=0, page_count=1, zoom=0.33) == "Page 1 / 1 · 33%"


def test_damaged_file_is_reported_in_the_status_bar(window, fixtures_dir):
    window.open_path(fixtures_dir / "broken_xref.pdf")

    assert "repaired" in window.statusBar().currentMessage()
    assert window.view.page_count == 2


def test_closing_the_window_closes_the_document(window, fixtures_dir):
    window.open_path(fixtures_dir / "simple_text.pdf")

    window.close()

    assert not window.model.is_open


# --- File > Open ----------------------------------------------------------------


def test_file_open_dialog_opens_the_chosen_file(window, fixtures_dir, monkeypatch):
    chosen = fixtures_dir / "rotated_pages.pdf"
    # Stand in for the real file dialog: "the user picked this file".
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(chosen), "")
    )

    window.open_action.trigger()

    assert window.model.path == chosen
    assert window.view.page_count == 4


def test_cancelling_the_file_dialog_changes_nothing(window, fixtures_dir, monkeypatch):
    window.open_path(fixtures_dir / "simple_text.pdf")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("", "")
    )

    window.open_action.trigger()

    assert window.windowTitle() == "simple_text.pdf - PDF Editor"


# --- the go-to-page box ---------------------------------------------------------


def test_page_box_text_without_and_with_labels():
    assert page_box_text(page_index=3, page_count=120, label="") == "4"
    assert page_box_text(page_index=3, page_count=120, label="iv") == "iv (4 of 120)"


def test_typing_a_page_number_goes_there(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "simple_text.pdf")

    type_in_page_box(qtbot, window, "2")

    assert window.view.current_page == 1
    assert status_of(window) == "Page 2 / 2 · 100%"


def test_page_box_shows_the_label_and_the_position(window, fixtures_dir):
    window.open_path(fixtures_dir / "page_labels.pdf")

    assert window.toolbar.page_box.text() == "i (1 of 8)"

    window.view.go_to_page(5)

    assert window.toolbar.page_box.text() == "2 (6 of 8)"


@pytest.mark.parametrize(
    ("typed", "expected_index"),
    [("iii", 2), ("IV", 3), ("3", 6), ("8", 7)],
)
def test_typing_a_label_or_number_in_a_labelled_document(
    qtbot, window, fixtures_dir, typed, expected_index
):
    window.open_path(fixtures_dir / "page_labels.pdf")

    type_in_page_box(qtbot, window, typed)

    assert window.view.current_page == expected_index


def test_typing_nonsense_keeps_the_page_and_says_why(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "page_labels.pdf")
    window.view.go_to_page(2)

    type_in_page_box(qtbot, window, "banana")

    assert window.view.current_page == 2
    assert 'no page "banana"' in window.statusBar().currentMessage()
    assert window.toolbar.page_box.text() == "iii (3 of 8)"  # put back


def test_pressing_enter_on_the_unchanged_text_does_nothing(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "page_labels.pdf")
    box = window.toolbar.page_box
    box.setFocus()

    qtbot.keyClick(box, Qt.Key.Key_Return)

    assert window.view.current_page == 0
    assert window.statusBar().currentMessage() == ""
