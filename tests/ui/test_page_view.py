"""PageView: layout, drawing only what is visible, zoom, navigation, overlays
and passing mouse events on to a tool.

The `view` fixture (tests/ui/conftest.py) is a shown, empty 900 x 700 view.
page_labels.pdf has eight Letter pages, more than fit in the window.
"""

import pymupdf
import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QWheelEvent

from pdfeditor.core import geometry
from pdfeditor.ui.overlays import OverlayLayer
from pdfeditor.ui.page_view import PageView, ZoomMode
from pdfeditor.ui.tools.base import PageEvent, Tool


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


# --- overlays -------------------------------------------------------------------

A_QUAD = pymupdf.Rect(72, 80, 172, 95).quad  # in unrotated PDF points


def test_an_overlay_sits_on_its_page_at_the_quads_position(eight_pages):
    eight_pages.set_overlay(OverlayLayer.SELECTION, 2, [A_QUAD])

    overlay = eight_pages.overlay(OverlayLayer.SELECTION, 2)
    # It is a child of the third page item, so it uses that page as origin.
    assert overlay.parentItem().placement.page_index == 2
    assert overlay.boundingRect() == QRectF(72, 80, 100, 15)
    assert overlay.sceneBoundingRect().top() == eight_pages.placement(2).origin_y + 80
    assert overlay.shape_count == 1


def test_an_overlay_on_a_rotated_page_is_turned_with_it(view, model, fixtures_dir):
    model.open(fixtures_dir / "rotated_pages.pdf")
    view.set_document(model)

    view.set_overlay(OverlayLayer.SEARCH_HITS, 1, [A_QUAD])  # the 90 degree page

    # (x, y) -> (792 - y, x): the wide, flat box becomes narrow and tall.
    area = view.overlay(OverlayLayer.SEARCH_HITS, 1).boundingRect()
    assert (area.left(), area.top()) == pytest.approx((697, 72))
    assert (area.width(), area.height()) == pytest.approx((15, 100))


def test_setting_an_overlay_again_replaces_its_shapes(eight_pages):
    eight_pages.set_overlay(OverlayLayer.SEARCH_HITS, 0, [A_QUAD])
    first = eight_pages.overlay(OverlayLayer.SEARCH_HITS, 0)

    other_quad = pymupdf.Rect(72, 200, 100, 215).quad
    eight_pages.set_overlay(OverlayLayer.SEARCH_HITS, 0, [A_QUAD, other_quad])

    assert eight_pages.overlay(OverlayLayer.SEARCH_HITS, 0) is first  # reused
    assert first.shape_count == 2


def test_no_quads_removes_the_overlay_of_that_page_only(eight_pages):
    eight_pages.set_overlay(OverlayLayer.SEARCH_HITS, 0, [A_QUAD])
    eight_pages.set_overlay(OverlayLayer.SEARCH_HITS, 3, [A_QUAD])

    eight_pages.set_overlay(OverlayLayer.SEARCH_HITS, 0, [])

    assert eight_pages.overlay_pages(OverlayLayer.SEARCH_HITS) == {3}
    assert len(eight_pages.scene().items()) == 8 + 1  # the pages and one overlay


def test_layers_are_kept_apart(eight_pages):
    eight_pages.set_overlay(OverlayLayer.SEARCH_HITS, 0, [A_QUAD])
    eight_pages.set_overlay(OverlayLayer.SELECTION, 0, [A_QUAD])

    eight_pages.clear_overlay(OverlayLayer.SEARCH_HITS)

    assert eight_pages.overlay_pages(OverlayLayer.SEARCH_HITS) == set()
    assert eight_pages.overlay_pages(OverlayLayer.SELECTION) == {0}


def test_the_selection_is_drawn_above_search_hits(eight_pages):
    eight_pages.set_overlay(OverlayLayer.SEARCH_HITS, 0, [A_QUAD])
    eight_pages.set_overlay(OverlayLayer.CURRENT_HIT, 0, [A_QUAD])
    eight_pages.set_overlay(OverlayLayer.SELECTION, 0, [A_QUAD])

    levels = [
        eight_pages.overlay(layer, 0).zValue()
        for layer in (
            OverlayLayer.SEARCH_HITS,
            OverlayLayer.CURRENT_HIT,
            OverlayLayer.SELECTION,
        )
    ]
    assert levels == sorted(levels)
    assert len(set(levels)) == 3


def test_overlays_go_away_with_the_document(eight_pages):
    eight_pages.set_overlay(OverlayLayer.SELECTION, 0, [A_QUAD])

    eight_pages.set_document(None)

    assert eight_pages.overlay_pages(OverlayLayer.SELECTION) == set()


# --- scrolling to a spot --------------------------------------------------------


def test_scroll_to_brings_a_far_spot_into_view(eight_pages):
    eight_pages.scroll_to(6, [A_QUAD])

    assert eight_pages.current_page == 6
    top = eight_pages.placement(6).origin_y + 80
    visible = eight_pages.mapToScene(eight_pages.viewport().rect()).boundingRect()
    assert visible.top() < top < visible.bottom()


def test_scroll_to_leaves_the_view_alone_when_the_spot_is_visible(eight_pages):
    before = eight_pages.verticalScrollBar().value()

    eight_pages.scroll_to(0, [A_QUAD])

    assert eight_pages.verticalScrollBar().value() == before


def test_scroll_to_does_not_shift_sideways_for_a_spot_further_down(eight_pages):
    eight_pages.set_zoom(2.0)  # now the pages are wider than the window
    sideways = eight_pages.horizontalScrollBar()
    sideways.setValue(sideways.minimum())  # look at the left part of the pages

    eight_pages.scroll_to(6, [A_QUAD])  # near the left edge of a later page

    assert eight_pages.current_page == 6
    assert sideways.value() == sideways.minimum()


def test_scroll_to_shifts_sideways_when_the_spot_is_out_of_sight(eight_pages):
    eight_pages.set_zoom(2.0)
    sideways = eight_pages.horizontalScrollBar()
    sideways.setValue(sideways.maximum())  # look at the right part of the pages
    assert sideways.maximum() > sideways.minimum()

    eight_pages.scroll_to(0, [A_QUAD])  # at the left edge, hidden just now

    assert sideways.value() < sideways.maximum()


def test_scroll_to_ignores_nonsense(eight_pages):
    eight_pages.scroll_to(99, [A_QUAD])
    eight_pages.scroll_to(0, [])

    assert eight_pages.current_page == 0


# --- handing mouse events to a tool ---------------------------------------------


class RecordingTool(Tool):
    """A tool that only notes what it is told."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, PageEvent | None]] = []

    def on_press(self, event: PageEvent) -> None:
        self.calls.append(("press", event))

    def on_move(self, event: PageEvent) -> None:
        self.calls.append(("move", event))

    def on_release(self, event: PageEvent) -> None:
        self.calls.append(("release", event))

    def reset(self) -> None:
        self.calls.append(("reset", None))


@pytest.fixture
def tool(eight_pages) -> RecordingTool:
    recording_tool = RecordingTool()
    eight_pages.set_tool(recording_tool)
    return recording_tool


def pixel_of(view: PageView, page_index: int, x: float, y: float) -> QPoint:
    """The pixel of the view that shows the PDF point (x, y) of a page."""
    scene_x, scene_y = view.placement(page_index).pdf_to_scene(pymupdf.Point(x, y))
    return view.mapFromScene(scene_x, scene_y)


def test_a_press_reaches_the_tool_as_page_and_pdf_point(qtbot, eight_pages, tool):
    spot = pixel_of(eight_pages, 0, 100, 200)

    qtbot.mousePress(eight_pages.viewport(), Qt.MouseButton.LeftButton, pos=spot)

    name, event = tool.calls[-1]
    assert name == "press"
    assert event.page_index == 0
    # Within a pixel: the mouse position is a whole number of pixels.
    assert (event.pdf_point.x, event.pdf_point.y) == pytest.approx((100, 200), abs=1)
    assert event.click_count == 1
    assert event.button == Qt.MouseButton.LeftButton


def test_a_drag_keeps_reporting_the_page_it_began_on(qtbot, eight_pages, tool):
    viewport = eight_pages.viewport()
    start = pixel_of(eight_pages, 0, 100, 20)
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)

    # 15 pixels further up is above the top edge of the first page.
    above = QPoint(start.x(), 2)
    qtbot.mouseMove(viewport, above)
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=above)

    names = [name for name, _ in tool.calls]
    assert names == ["press", "move", "release"]
    moved = tool.calls[1][1]
    assert moved.page_index == 0
    assert moved.pdf_point.y < 0  # outside the page, and reported as such


def test_a_press_beside_the_pages_resets_the_tool(qtbot, eight_pages, tool):
    eight_pages.set_zoom(0.5)  # leaves gray space left of the pages

    qtbot.mousePress(
        eight_pages.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(3, 3)
    )

    assert tool.calls == [("reset", None)]


def test_a_double_click_is_reported_with_click_count_two(qtbot, eight_pages, tool):
    spot = pixel_of(eight_pages, 0, 100, 200)

    qtbot.mouseDClick(eight_pages.viewport(), Qt.MouseButton.LeftButton, pos=spot)

    assert tool.calls[-1][1].click_count == 2


def test_a_press_right_after_a_double_click_counts_as_the_third(
    qtbot, eight_pages, tool
):
    viewport = eight_pages.viewport()
    spot = pixel_of(eight_pages, 0, 100, 200)
    qtbot.mouseDClick(viewport, Qt.MouseButton.LeftButton, pos=spot)
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=spot)

    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=spot)

    assert tool.calls[-1][1].click_count == 3


def test_the_right_button_is_not_passed_to_the_tool(qtbot, eight_pages, tool):
    spot = pixel_of(eight_pages, 0, 100, 200)

    qtbot.mouseClick(eight_pages.viewport(), Qt.MouseButton.RightButton, pos=spot)

    assert tool.calls == []


def test_a_new_document_resets_the_tool(eight_pages, tool):
    eight_pages.set_document(None)

    assert tool.calls == [("reset", None)]


def test_clicks_without_a_tool_do_nothing(qtbot, eight_pages):
    spot = pixel_of(eight_pages, 0, 100, 200)

    qtbot.mouseClick(eight_pages.viewport(), Qt.MouseButton.LeftButton, pos=spot)
    qtbot.mouseDClick(eight_pages.viewport(), Qt.MouseButton.LeftButton, pos=spot)

    assert eight_pages.current_page == 0  # still alive and unchanged
