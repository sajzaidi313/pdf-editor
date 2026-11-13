"""PageView: layout, drawing only what is visible, zoom and navigation.

The `view` fixture (tests/ui/conftest.py) is a shown, empty 900 x 700 view.
page_labels.pdf has eight Letter pages, more than fit in the window.
"""

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent

from pdfeditor.core import geometry
from pdfeditor.ui.page_view import PageView, ZoomMode


@pytest.fixture
def eight_pages(view, model, fixtures_dir) -> PageView:
    """The view showing the eight pages of page_labels.pdf."""
    model.open(fixtures_dir / "page_labels.pdf")
    view.set_document(model)
    return view


def view_scale_of(view: PageView) -> float:
    """Pixels per point the view currently magnifies by (m11 is the
    horizontal scale factor of a transform)."""
    return view.transform().m11()


def turn_wheel(view: PageView, notches: int, ctrl: bool) -> None:
    """Send the view a mouse wheel event, as if the user turned the wheel."""
    modifiers = (
        Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    )
    position = QPointF(view.viewport().rect().center())
    event = QWheelEvent(
        position,
        QPointF(view.viewport().mapToGlobal(position.toPoint())),
        QPoint(0, 0),
        QPoint(0, 120 * notches),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    view.wheelEvent(event)


# --- showing a document ---------------------------------------------------------


def test_empty_view_has_no_pages(view):
    assert view.page_count == 0
    assert view.rendered_pages() == set()


def test_one_item_per_page(eight_pages):
    assert eight_pages.page_count == 8
    assert len(eight_pages.scene().items()) == 8


def test_only_visible_pages_are_drawn(eight_pages):
    # A 700 pixel high window at 100% shows part of the first page only.
    assert eight_pages.rendered_pages() == {0}


def test_scrolling_draws_new_pages_and_drops_old_ones(eight_pages):
    eight_pages.go_to_page(7)

    assert 7 in eight_pages.rendered_pages()
    assert 0 not in eight_pages.rendered_pages()


def test_set_document_none_empties_the_view(eight_pages):
    eight_pages.set_document(None)

    assert eight_pages.page_count == 0
    assert eight_pages.rendered_pages() == set()
    assert eight_pages.scene().items() == []


def test_new_document_starts_at_the_first_page(eight_pages, model, fixtures_dir):
    eight_pages.go_to_page(5)

    model.open(fixtures_dir / "rotated_pages.pdf")
    eight_pages.set_document(model)

    assert eight_pages.page_count == 4
    assert eight_pages.current_page == 0
    assert 0 in eight_pages.rendered_pages()


# --- zoom -----------------------------------------------------------------------


def test_starts_at_100_percent(view):
    assert view.zoom == 1.0
    assert view_scale_of(view) == pytest.approx(
        geometry.view_scale(1.0, view.logicalDpiX())
    )


def test_set_zoom_changes_the_magnification_not_the_scene(eight_pages):
    scene_rect_before = eight_pages.sceneRect()

    eight_pages.set_zoom(2.0)

    expected = geometry.view_scale(2.0, eight_pages.logicalDpiX())
    assert view_scale_of(eight_pages) == pytest.approx(expected)
    assert eight_pages.sceneRect() == scene_rect_before


def test_zoom_in_and_out_follow_the_steps(eight_pages):
    eight_pages.zoom_in()
    assert eight_pages.zoom == 1.1

    eight_pages.zoom_out()
    eight_pages.zoom_out()
    assert eight_pages.zoom == 0.9


def test_zoom_stays_within_25_and_800_percent(eight_pages):
    eight_pages.set_zoom(50)
    assert eight_pages.zoom == 8.0

    eight_pages.set_zoom(0.001)
    assert eight_pages.zoom == 0.25


def test_zoom_emits_a_signal(qtbot, eight_pages):
    # waitSignal passes only if the signal is emitted inside the block.
    with qtbot.waitSignal(eight_pages.zoom_changed) as signal:
        eight_pages.set_zoom(1.5)

    assert signal.args == [1.5]


def image_scale_at(view: PageView, zoom: float) -> float:
    """The pixels per point a Letter page's picture should have at `zoom`."""
    scale = geometry.view_scale(zoom, view.logicalDpiX())
    return geometry.render_scale(scale, view.devicePixelRatioF(), 612, 792)


def test_pages_are_redrawn_sharp_shortly_after_a_zoom(qtbot, eight_pages):
    first_page = eight_pages.scene().items(Qt.SortOrder.AscendingOrder)[0]
    old_scale = image_scale_at(eight_pages, 1.0)
    assert first_page.has_image_at(old_scale)

    eight_pages.set_zoom(1.5)

    # Right away the old picture is still there (Qt stretches it)...
    assert first_page.has_image_at(old_scale)
    # ...and a moment later it has been replaced by a sharp one.
    new_scale = image_scale_at(eight_pages, 1.5)
    qtbot.waitUntil(lambda: first_page.has_image_at(new_scale), timeout=2000)


def test_zooming_out_draws_the_pages_that_come_into_view(eight_pages):
    eight_pages.set_zoom(0.25)
    eight_pages.render_visible_pages()  # don't wait for the timer

    assert len(eight_pages.rendered_pages()) > 1


def test_actual_size_returns_to_100_percent(eight_pages):
    eight_pages.set_zoom(3.0)

    eight_pages.actual_size()

    assert eight_pages.zoom == 1.0


def test_ctrl_wheel_zooms(eight_pages):
    turn_wheel(eight_pages, notches=1, ctrl=True)
    assert eight_pages.zoom == 1.1

    turn_wheel(eight_pages, notches=-2, ctrl=True)
    assert eight_pages.zoom == 0.9


def test_plain_wheel_scrolls_and_does_not_zoom(eight_pages):
    scroll_bar = eight_pages.verticalScrollBar()
    before = scroll_bar.value()

    turn_wheel(eight_pages, notches=-3, ctrl=False)

    assert eight_pages.zoom == 1.0
    assert scroll_bar.value() > before


def test_fit_width_makes_the_pages_fill_the_window(eight_pages):
    eight_pages.fit_width()

    page_and_margins = (612 + 2 * geometry.PAGE_GAP) * view_scale_of(eight_pages)
    viewport_width = eight_pages.viewport().width()
    assert eight_pages.zoom_mode is ZoomMode.FIT_WIDTH
    assert viewport_width - 4 <= page_and_margins <= viewport_width
    assert eight_pages.horizontalScrollBar().maximum() == 0  # nothing to scroll


def test_fit_width_follows_the_window_size(qtbot, eight_pages):
    eight_pages.fit_width()
    zoom_before = eight_pages.zoom

    eight_pages.resize(600, 700)
    qtbot.waitUntil(lambda: eight_pages.zoom < zoom_before, timeout=2000)

    assert eight_pages.zoom_mode is ZoomMode.FIT_WIDTH


def test_choosing_a_zoom_leaves_fit_mode(qtbot, eight_pages):
    eight_pages.fit_width()

    eight_pages.set_zoom(2.0)
    eight_pages.resize(600, 700)
    qtbot.wait(50)

    assert eight_pages.zoom_mode is ZoomMode.CUSTOM
    assert eight_pages.zoom == 2.0


def test_fit_page_shows_the_whole_current_page(eight_pages):
    eight_pages.go_to_page(3)

    eight_pages.fit_page()

    page_height_pixels = 792 * view_scale_of(eight_pages)
    assert eight_pages.zoom_mode is ZoomMode.FIT_PAGE
    assert page_height_pixels <= eight_pages.viewport().height()
    assert eight_pages.current_page == 3


# --- navigation -----------------------------------------------------------------


def test_go_to_page_changes_the_current_page(qtbot, eight_pages):
    with qtbot.waitSignal(eight_pages.current_page_changed) as signal:
        eight_pages.go_to_page(4)

    assert eight_pages.current_page == 4
    assert signal.args == [4]


def test_next_and_previous_page(eight_pages):
    eight_pages.next_page()
    eight_pages.next_page()
    assert eight_pages.current_page == 2

    eight_pages.previous_page()
    assert eight_pages.current_page == 1


def test_first_and_last_page(eight_pages):
    eight_pages.last_page()
    assert eight_pages.current_page == 7

    eight_pages.first_page()
    assert eight_pages.current_page == 0


def test_navigation_stops_at_the_ends(eight_pages):
    eight_pages.previous_page()
    assert eight_pages.current_page == 0

    eight_pages.go_to_page(99)
    assert eight_pages.current_page == 7


def test_go_to_page_is_honest_when_several_pages_fit(eight_pages):
    """At a small zoom several whole pages are visible at once. The page
    that was asked for must still be reported as the current one."""
    eight_pages.set_zoom(0.25)

    eight_pages.go_to_page(3)

    assert eight_pages.current_page == 3


def test_navigation_without_a_document_does_nothing(view):
    view.next_page()
    view.go_to_page(3)
    view.fit_width()

    assert view.current_page == 0
