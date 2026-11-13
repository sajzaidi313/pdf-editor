"""Selecting text with the mouse, and copying it.

The tests click and drag on the real page view of a main window. Page 1 of
search_and_select.pdf is laid out as these lines (see test_text.py):

    line 0  "The quick brown fox jumps over the lazy"
    line 1  "dog and then the very lazy dog sleeps for"
    line 2  "a long while under the old oak tree near"
    line 3  "the river bank."
"""

import pymupdf
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from pdfeditor.ui.main_window import NO_TEXT_MESSAGE, MainWindow
from pdfeditor.ui.overlays import OverlayLayer
from pdfeditor.ui.tools.base import PageEvent

LEFT = Qt.MouseButton.LeftButton


@pytest.fixture
def text_window(window, fixtures_dir) -> MainWindow:
    """A window showing search_and_select.pdf at 200%, so that single
    characters are comfortably wider than one pixel."""
    window.open_path(fixtures_dir / "search_and_select.pdf")
    window.view.set_zoom(2.0)
    return window


def spot_on(
    window: MainWindow, page: int, line: int, column: int, across: float = 0.5
) -> QPoint:
    """The pixel in the page view that shows one character.

    `across` 0.0 is the character's left edge, 1.0 its right edge. The view
    is scrolled first if the character is not in sight.
    """
    x0, y0, x1, y1 = window.model.page_text(page).lines[line].boxes[column]
    pdf_point = pymupdf.Point(x0 + (x1 - x0) * across, (y0 + y1) / 2)
    scene_x, scene_y = window.view.placement(page).pdf_to_scene(pdf_point)
    if (
        not window.view.viewport()
        .rect()
        .contains(window.view.mapFromScene(scene_x, scene_y))
    ):
        window.view.centerOn(scene_x, scene_y)
    return window.view.mapFromScene(scene_x, scene_y)


def drag(qtbot, window: MainWindow, start: QPoint, end: QPoint) -> None:
    """Press the left button at `start`, move to `end`, let go."""
    viewport = window.view.viewport()
    qtbot.mousePress(viewport, LEFT, pos=start)
    qtbot.mouseMove(viewport, end)
    qtbot.mouseRelease(viewport, LEFT, pos=end)


def selected(window: MainWindow) -> str:
    return window.select_tool.selected_text()


# --- dragging -------------------------------------------------------------------


def test_nothing_is_selected_at_first(text_window):
    assert not text_window.select_tool.has_selection
    assert selected(text_window) == ""
    assert not text_window.copy_action.isEnabled()


def test_dragging_across_a_word_selects_it(qtbot, text_window):
    start = spot_on(text_window, 0, 0, 4, across=0.2)  # the "q" of "quick"
    end = spot_on(text_window, 0, 0, 8, across=0.8)  # its "k"

    drag(qtbot, text_window, start, end)

    assert selected(text_window) == "quick"
    assert text_window.select_tool.selection_page == 0
    assert text_window.copy_action.isEnabled()


def test_dragging_over_two_lines_selects_to_the_line_end_and_on(qtbot, text_window):
    start = spot_on(text_window, 0, 0, 4, across=0.2)  # "quick" on line 0
    end = spot_on(text_window, 0, 1, 2, across=0.8)  # the "g" of "dog" on line 1

    drag(qtbot, text_window, start, end)

    assert selected(text_window) == "quick brown fox jumps over the lazy\ndog"
    # One shape per line of the selection.
    overlay = text_window.view.overlay(OverlayLayer.SELECTION, 0)
    assert overlay.shape_count == 2


def test_dragging_backwards_selects_the_same_text(qtbot, text_window):
    start = spot_on(text_window, 0, 1, 2, across=0.8)
    end = spot_on(text_window, 0, 0, 4, across=0.2)

    drag(qtbot, text_window, start, end)

    assert selected(text_window) == "quick brown fox jumps over the lazy\ndog"


def test_the_selection_grows_while_the_mouse_moves(qtbot, text_window):
    viewport = text_window.view.viewport()
    qtbot.mousePress(viewport, LEFT, pos=spot_on(text_window, 0, 0, 4, across=0.2))

    qtbot.mouseMove(viewport, spot_on(text_window, 0, 0, 8, across=0.8))
    assert selected(text_window) == "quick"

    qtbot.mouseMove(viewport, spot_on(text_window, 0, 0, 14, across=0.8))
    assert selected(text_window) == "quick brown"

    qtbot.mouseRelease(viewport, LEFT, pos=spot_on(text_window, 0, 0, 14, across=0.8))
    assert selected(text_window) == "quick brown"


def test_moving_the_mouse_after_letting_go_changes_nothing(qtbot, text_window):
    drag(
        qtbot,
        text_window,
        spot_on(text_window, 0, 0, 4, across=0.2),
        spot_on(text_window, 0, 0, 8, across=0.8),
    )

    qtbot.mouseMove(text_window.view.viewport(), spot_on(text_window, 0, 2, 5))

    assert selected(text_window) == "quick"


def test_a_plain_click_selects_nothing_and_drops_the_old_selection(qtbot, text_window):
    drag(
        qtbot,
        text_window,
        spot_on(text_window, 0, 0, 4, across=0.2),
        spot_on(text_window, 0, 0, 8, across=0.8),
    )

    qtbot.mouseClick(
        text_window.view.viewport(), LEFT, pos=spot_on(text_window, 0, 2, 5)
    )

    assert not text_window.select_tool.has_selection
    assert text_window.view.overlay_pages(OverlayLayer.SELECTION) == set()
    assert not text_window.copy_action.isEnabled()


def test_a_click_beside_the_pages_drops_the_selection(qtbot, text_window):
    text_window.view.set_zoom(0.5)  # small pages leave gray space beside them
    drag(
        qtbot,
        text_window,
        spot_on(text_window, 0, 0, 4, across=0.1),
        spot_on(text_window, 0, 0, 20, across=0.9),
    )
    assert text_window.select_tool.has_selection

    qtbot.mouseClick(text_window.view.viewport(), LEFT, pos=QPoint(3, 3))

    assert not text_window.select_tool.has_selection


def test_dragging_off_the_page_selects_to_the_end_of_its_text(qtbot, text_window):
    view = text_window.view
    view.set_zoom(0.5)  # the whole first page and the gap below fit in view
    start = spot_on(text_window, 0, 3, 4, across=0.1)  # "river" on line 3
    page_bottom = view.placement(0).bottom
    below_page = view.mapFromScene(view.placement(0).origin_x + 300, page_bottom + 6)

    drag(qtbot, text_window, start, below_page)

    # The drag began on page 1 and stays there: everything to its last line.
    assert text_window.select_tool.selection_page == 0
    assert selected(text_window).startswith("river bank.\nThis is an exam-")
    assert selected(text_window).endswith("fox fox FOX")


# --- double and triple click ----------------------------------------------------


def test_double_click_selects_the_word(qtbot, text_window):
    spot = spot_on(text_window, 0, 0, 6)  # inside "quick"

    qtbot.mouseDClick(text_window.view.viewport(), LEFT, pos=spot)

    assert selected(text_window) == "quick"


def test_double_click_on_a_space_selects_nothing(qtbot, text_window):
    spot = spot_on(text_window, 0, 0, 3)  # the space after "The"

    qtbot.mouseDClick(text_window.view.viewport(), LEFT, pos=spot)

    assert not text_window.select_tool.has_selection


def test_a_third_click_selects_the_line(qtbot, text_window):
    viewport = text_window.view.viewport()
    spot = spot_on(text_window, 0, 1, 10)

    qtbot.mouseDClick(viewport, LEFT, pos=spot)
    qtbot.mouseRelease(viewport, LEFT, pos=spot)
    qtbot.mouseClick(viewport, LEFT, pos=spot)  # right away, on the same spot

    assert selected(text_window) == "dog and then the very lazy dog sleeps for"


def test_a_click_elsewhere_after_a_double_click_is_an_ordinary_click(
    qtbot, text_window
):
    viewport = text_window.view.viewport()

    qtbot.mouseDClick(viewport, LEFT, pos=spot_on(text_window, 0, 1, 10))
    qtbot.mouseRelease(viewport, LEFT, pos=spot_on(text_window, 0, 1, 10))
    qtbot.mouseClick(viewport, LEFT, pos=spot_on(text_window, 0, 3, 2))

    assert not text_window.select_tool.has_selection


def test_triple_click_through_the_tool_itself(text_window):
    """The same thing without the mouse: hand the tool a PageEvent."""
    x0, y0, x1, y1 = text_window.model.page_text(0).lines[3].boxes[5]
    point = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
    event = PageEvent(0, point, Qt.KeyboardModifier.NoModifier, LEFT, click_count=3)

    text_window.select_tool.on_press(event)

    assert selected(text_window) == "the river bank."


# --- other pages ----------------------------------------------------------------


def test_selecting_on_a_rotated_page(qtbot, text_window):
    # Page 3 is rotated by 90 degrees: its line runs top to bottom on screen.
    text_window.view.set_zoom(1.0)
    start = spot_on(text_window, 2, 0, 2, across=0.2)  # "lazy"
    end = spot_on(text_window, 2, 0, 9, across=0.8)  # the "g" of "dog"

    drag(qtbot, text_window, start, end)

    assert selected(text_window) == "lazy dog"
    assert text_window.select_tool.selection_page == 2
    # On screen the marked area is tall and narrow, like the turned text.
    area = text_window.view.overlay(OverlayLayer.SELECTION, 2).boundingRect()
    assert area.height() > 2 * area.width()


def test_a_selection_on_another_page_replaces_the_first(qtbot, text_window):
    text_window.view.set_zoom(1.0)
    drag(
        qtbot,
        text_window,
        spot_on(text_window, 0, 0, 4, across=0.2),
        spot_on(text_window, 0, 0, 8, across=0.8),
    )

    drag(
        qtbot,
        text_window,
        spot_on(text_window, 1, 0, 0, across=0.2),
        spot_on(text_window, 1, 0, 5, across=0.8),
    )

    assert selected(text_window) == "Second"
    assert text_window.view.overlay_pages(OverlayLayer.SELECTION) == {1}


def test_a_scanned_page_says_that_it_has_no_text(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "scanned_no_text.pdf")
    middle_of_the_picture = window.view.mapFromScene(180, 85)

    drag(qtbot, window, middle_of_the_picture, middle_of_the_picture + QPoint(80, 0))

    assert not window.select_tool.has_selection
    assert window.statusBar().currentMessage() == NO_TEXT_MESSAGE


def test_opening_another_file_drops_the_selection(qtbot, text_window, fixtures_dir):
    drag(
        qtbot,
        text_window,
        spot_on(text_window, 0, 0, 4, across=0.2),
        spot_on(text_window, 0, 0, 8, across=0.8),
    )

    text_window.open_path(fixtures_dir / "simple_text.pdf")

    assert not text_window.select_tool.has_selection
    assert selected(text_window) == ""
    assert not text_window.copy_action.isEnabled()


# --- the mouse pointer ----------------------------------------------------------


def hover(window: MainWindow, spot: QPoint) -> None:
    """Move the mouse to `spot` in the page view without pressing a button.

    qtbot.mouseMove only reaches a widget reliably while a button is held,
    so the "mouse moved" event is built by hand and sent straight to the
    view's viewport, which is where real mouse events arrive too.
    """
    viewport = window.view.viewport()
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(spot),
        QPointF(viewport.mapToGlobal(spot)),
        Qt.MouseButton.NoButton,  # the button that caused the event: none
        Qt.MouseButton.NoButton,  # the buttons held down: none
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(viewport, event)


def test_the_view_hears_about_the_mouse_moving_without_a_button(text_window):
    # Without mouse tracking a widget only gets moves while a button is
    # held, and the pointer could never change on hovering.
    assert text_window.view.viewport().hasMouseTracking()


def test_the_pointer_is_an_i_beam_over_text_and_an_arrow_elsewhere(text_window):
    viewport = text_window.view.viewport()

    hover(text_window, spot_on(text_window, 0, 0, 6))
    assert viewport.cursor().shape() == Qt.CursorShape.IBeamCursor

    blank_part_of_the_page = text_window.view.mapFromScene(
        *text_window.view.placement(0).pdf_to_scene(pymupdf.Point(400, 180))
    )
    hover(text_window, blank_part_of_the_page)
    assert viewport.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_the_pointer_is_an_arrow_beside_the_pages(text_window):
    text_window.view.set_zoom(0.5)  # gray space left and right of the pages
    hover(text_window, spot_on(text_window, 0, 0, 6))
    assert text_window.view.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor

    hover(text_window, QPoint(3, 3))

    assert text_window.view.viewport().cursor().shape() == Qt.CursorShape.ArrowCursor


# --- copying --------------------------------------------------------------------


def test_copy_puts_the_selected_text_on_the_clipboard(qtbot, text_window, copied_texts):
    drag(
        qtbot,
        text_window,
        spot_on(text_window, 0, 0, 4, across=0.2),
        spot_on(text_window, 0, 1, 2, across=0.8),
    )

    text_window.copy_action.trigger()

    assert copied_texts == ["quick brown fox jumps over the lazy\ndog"]


def test_copy_with_nothing_selected_copies_nothing(text_window, copied_texts):
    text_window.copy_selection()

    assert copied_texts == []


def test_copy_a_whole_paragraph(text_window, copied_texts):
    """The milestone's goal: select a paragraph and copy it."""
    page_text = text_window.model.page_text(0)
    first = page_text.lines[0].boxes[0]
    last = page_text.lines[3].boxes[-1]
    tool = text_window.select_tool
    no_keys = Qt.KeyboardModifier.NoModifier

    tool.on_press(PageEvent(0, pymupdf.Point(first[0], first[1] + 5), no_keys, LEFT))
    tool.on_move(PageEvent(0, pymupdf.Point(last[2] + 1, last[1] + 5), no_keys, LEFT))
    tool.on_release(
        PageEvent(0, pymupdf.Point(last[2] + 1, last[1] + 5), no_keys, LEFT)
    )
    text_window.copy_selection()

    assert copied_texts == [
        "The quick brown fox jumps over the lazy\n"
        "dog and then the very lazy dog sleeps for\n"
        "a long while under the old oak tree near\n"
        "the river bank."
    ]
