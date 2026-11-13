"""PageView: the scrolling, zooming canvas that shows the document's pages.

A QGraphicsView is a window onto a QGraphicsScene (see page_item.py). The
scene holds one PageItem per page, stacked top to bottom and measured in
PDF points. Zooming never moves or resizes anything in the scene: it only
changes the view's "transform", the magnification the view looks through.
Qt then stretches the existing page pictures at once, and a moment later
this class replaces them with sharp ones.

For now pages are drawn right here on the UI thread, and only the pages
that are visible. Milestone M3 moves the drawing to a separate process.

The view also passes mouse clicks and drags on to the active tool (see
tools/base.py) and shows overlays such as search hits (see overlays.py).
"""

import time
from collections.abc import Sequence
from enum import Enum

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QResizeEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from pdfeditor.core import geometry
from pdfeditor.core.document import DocumentModel
from pdfeditor.core.geometry import PagePlacement
from pdfeditor.render.renderer import render_page
from pdfeditor.ui.overlays import OverlayLayer, QuadOverlay
from pdfeditor.ui.page_item import PageItem
from pdfeditor.ui.tools.base import PageEvent, Tool

BACKGROUND_COLOR = "#525659"  # the gray most PDF viewers use around pages

# How long to wait after the last zoom change before drawing sharp pages.
# Turning the mouse wheel sends many zoom changes in a row; drawing after
# each one would make zooming stutter.
RENDER_DELAY_MS = 120

# Qt reports wheel movement in eighths of a degree; one "click" of an
# ordinary mouse wheel is 15 degrees = 120 units.
WHEEL_NOTCH = 120

# A fit mode leaves this many pixels spare so that rounding can never make
# a scroll bar appear and disappear in turns.
FIT_SLACK_PIXELS = 2

# A third click counts as a triple-click when it lands this close, in
# pixels, to the double-click before it.
TRIPLE_CLICK_DISTANCE = 6


class ZoomMode(Enum):
    """How the zoom is chosen. An Enum is a fixed set of named values, so a
    typo like ZoomMode.FIT_WIDHT is an error instead of a silent bug."""

    CUSTOM = "custom"  # a fixed percentage picked by the user
    FIT_WIDTH = "fit_width"  # the widest page fills the window's width
    FIT_PAGE = "fit_page"  # the current page is entirely visible


class PageView(QGraphicsView):
    """Shows all pages of a DocumentModel and handles zoom and navigation."""

    # Signals are Qt's way for an object to announce "something happened"
    # without knowing who listens. The main window connects functions to
    # these, and Qt calls them on every emit().
    zoom_changed = Signal(float)  # the new zoom; 1.0 means 100%
    current_page_changed = Signal(int)  # the new current page index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._model: DocumentModel | None = None
        self._placements: list[PagePlacement] = []
        self._items: list[PageItem] = []
        self._pages_with_image: set[int] = set()
        self._zoom = 1.0
        self._zoom_mode = ZoomMode.CUSTOM
        self._current_page = 0
        self._wheel_units = 0  # wheel movement not yet turned into a zoom step
        # The overlays of each layer, by page index (see set_overlay).
        self._overlays: dict[OverlayLayer, dict[int, QuadOverlay]] = {
            layer: {} for layer in OverlayLayer
        }
        self._tool: Tool | None = None  # what gets the mouse clicks and drags
        self._pressed_page: int | None = None  # page of the drag in progress
        self._double_click_time = 0.0  # when and where the last double-click was
        self._double_click_spot = QPointF()
        self._configure_view()
        # A single-shot timer calls its function once, some time after
        # start(). Calling start() again before it fires restarts the wait.
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(RENDER_DELAY_MS)
        self._render_timer.timeout.connect(self.render_visible_pages)
        self.verticalScrollBar().valueChanged.connect(self._on_scrolled)
        self._apply_zoom_transform()

    def _configure_view(self) -> None:
        self.setBackgroundBrush(QColor(BACKGROUND_COLOR))
        self.setFrameShape(QFrame.Shape.NoFrame)
        # When the pages are narrower than the window, center them.
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        # Repaint only the parts of the window that changed.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        # Always show the vertical scroll bar. If it came and went, the
        # usable width would change and "fit width" would never settle.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # Dropped files are handled by the main window, not by the canvas.
        self.setAcceptDrops(False)
        # Normally a widget hears about mouse movement only while a button
        # is held. Mouse tracking reports every movement, which the I-beam
        # cursor over text needs. In a QGraphicsView the mouse events
        # arrive at the inner "viewport" widget, so it is switched on there.
        self.viewport().setMouseTracking(True)

    # --- showing a document ---------------------------------------------------

    def set_document(self, model: DocumentModel | None) -> None:
        """Show the pages of `model`, or an empty canvas when it is None.

        Builds one PageItem per page from the page sizes alone. Drawing the
        pages comes afterwards and only for the visible ones.

        The view asks the model for pages whenever it has to draw, so call
        set_document(None) *before* closing the model or opening another
        file in it.
        """
        self._render_timer.stop()
        if self._tool is not None:
            self._tool.reset()  # a selection belongs to the old document
        self._pressed_page = None
        self._scene.clear()  # removes and deletes every item, overlays included
        self._overlays = {layer: {} for layer in OverlayLayer}
        self._items = []
        self._pages_with_image = set()
        self._model = model
        self._placements = [] if model is None else geometry.layout_pages(model.pages())
        for placement in self._placements:
            item = PageItem(placement)
            self._scene.addItem(item)
            self._items.append(item)
        width, height = geometry.content_size(self._placements)
        margin = geometry.PAGE_GAP
        # The scene rect is the area the scroll bars cover: all pages plus
        # a margin around them.
        self._scene.setSceneRect(
            -margin, -margin, width + 2 * margin, height + 2 * margin
        )
        self._current_page = 0
        self._refit()
        self.centerOn(width / 2, 0)
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())
        self.render_visible_pages()
        self.current_page_changed.emit(0)

    @property
    def page_count(self) -> int:
        return len(self._placements)

    def placement(self, page_index: int) -> PagePlacement:
        """Where the page at `page_index` sits in the scene."""
        return self._placements[page_index]

    def rendered_pages(self) -> set[int]:
        """Indexes of the pages that currently hold a picture."""
        return set(self._pages_with_image)

    def render_visible_pages(self) -> None:
        """Draw every visible page sharply at the current zoom.

        Pictures of pages that scrolled out of sight are thrown away, so
        memory use depends on the window size, not on the document length.
        """
        model = self._model
        if model is None:
            return
        visible = self._visible_scene_rect()
        wanted = set(
            geometry.visible_pages(self._placements, visible.top(), visible.bottom())
        )
        for index in self._pages_with_image - wanted:
            self._items[index].clear_image()
        self._pages_with_image &= wanted
        scale = geometry.view_scale(self._zoom, self.logicalDpiX())
        for index in sorted(wanted):
            placement = self._placements[index]
            image_scale = geometry.render_scale(
                scale, self.devicePixelRatioF(), placement.width, placement.height
            )
            item = self._items[index]
            if not item.has_image_at(image_scale):
                item.set_image(render_page(model.page(index), image_scale), image_scale)
                self._pages_with_image.add(index)

    def _visible_scene_rect(self) -> QRectF:
        """The part of the scene the window currently shows, in points."""
        # mapToScene converts window pixels to scene coordinates, undoing
        # both the scrolling and the zoom.
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def _on_scrolled(self, _value: int = 0) -> None:
        # While a zoom is settling the timer will draw; don't draw twice.
        if not self._render_timer.isActive():
            self.render_visible_pages()
        self._update_current_page()

    # --- zoom -----------------------------------------------------------------

    @property
    def zoom(self) -> float:
        """The current zoom; 1.0 means 100% (real paper size)."""
        return self._zoom

    @property
    def zoom_mode(self) -> ZoomMode:
        return self._zoom_mode

    def set_zoom(self, zoom: float, under_mouse: bool = False) -> None:
        """Zoom to a fixed value. `under_mouse` keeps the spot under the
        mouse pointer in place (for the wheel); otherwise the middle of the
        window stays put."""
        self._zoom_mode = ZoomMode.CUSTOM
        self._change_zoom(zoom, under_mouse)

    def zoom_in(self, under_mouse: bool = False) -> None:
        self.set_zoom(geometry.next_zoom_step(self._zoom), under_mouse)

    def zoom_out(self, under_mouse: bool = False) -> None:
        self.set_zoom(geometry.previous_zoom_step(self._zoom), under_mouse)

    def actual_size(self) -> None:
        self.set_zoom(1.0)

    def fit_width(self) -> None:
        """Make the widest page fill the window's width, and keep it so
        when the window is resized."""
        self._zoom_mode = ZoomMode.FIT_WIDTH
        self._refit()

    def fit_page(self) -> None:
        """Make the whole current page visible."""
        self._zoom_mode = ZoomMode.FIT_PAGE
        self._refit()
        self.go_to_page(self._current_page)

    def _refit(self) -> None:
        """Work out the zoom again when a fit mode is on (new mode, new
        document or new window size)."""
        if self._zoom_mode is ZoomMode.CUSTOM or not self._placements:
            return
        margins = 2 * geometry.PAGE_GAP
        dpi = self.logicalDpiX()
        room_x = self.viewport().width() - FIT_SLACK_PIXELS
        room_y = self.viewport().height() - FIT_SLACK_PIXELS
        widest, _ = geometry.content_size(self._placements)
        zoom = geometry.zoom_to_fit(room_x, widest + margins, dpi)
        if self._zoom_mode is ZoomMode.FIT_PAGE:
            page = self._placements[self._current_page]
            zoom = min(
                geometry.zoom_to_fit(room_x, page.width + margins, dpi),
                geometry.zoom_to_fit(room_y, page.height + margins, dpi),
            )
        self._change_zoom(zoom)

    def _change_zoom(self, zoom: float, under_mouse: bool = False) -> None:
        zoom = geometry.clamp_zoom(zoom)
        if zoom == self._zoom:
            return
        self._zoom = zoom
        anchor = QGraphicsView.ViewportAnchor.AnchorViewCenter
        if under_mouse:
            anchor = QGraphicsView.ViewportAnchor.AnchorUnderMouse
        self.setTransformationAnchor(anchor)
        # Start the countdown to sharp pictures *before* changing the
        # magnification. The change also moves the scroll bars, and
        # _on_scrolled must find the timer running, or it would redraw
        # everything at once on every wheel notch.
        self._render_timer.start()
        self._apply_zoom_transform()  # Qt stretches the old pictures for now
        self.zoom_changed.emit(zoom)
        self._update_current_page()

    def _apply_zoom_transform(self) -> None:
        # logicalDpiX: how many pixels the system counts as one inch on
        # this screen (96 on a standard Windows display).
        scale = geometry.view_scale(self._zoom, self.logicalDpiX())
        self.setTransform(QTransform.fromScale(scale, scale))

    # --- navigation -----------------------------------------------------------

    @property
    def current_page(self) -> int:
        """Index of the page the user is looking at."""
        return self._current_page

    def go_to_page(self, index: int) -> None:
        """Scroll so the page at `index` starts at the top of the window."""
        if not self._placements:
            return
        index = max(0, min(index, len(self._placements) - 1))
        placement = self._placements[index]
        visible = self._visible_scene_rect()
        # Half a gap above the page: a little air, without pulling the
        # previous page back into view.
        top = placement.origin_y - geometry.PAGE_GAP / 2
        # centerOn wants the point for the window's middle. Keep the
        # horizontal position as it is.
        self.centerOn(visible.center().x(), top + visible.height() / 2)

    def next_page(self) -> None:
        self.go_to_page(self._current_page + 1)

    def previous_page(self) -> None:
        self.go_to_page(self._current_page - 1)

    def first_page(self) -> None:
        self.go_to_page(0)

    def last_page(self) -> None:
        self.go_to_page(len(self._placements) - 1)

    def _update_current_page(self) -> None:
        visible = self._visible_scene_rect()
        page = geometry.most_visible_page(
            self._placements, visible.top(), visible.bottom()
        )
        if page != self._current_page:
            self._current_page = page
            self.current_page_changed.emit(page)

    def scroll_to(self, page_index: int, quads: Sequence[pymupdf.Quad]) -> None:
        """Bring an area of a page into view (a search hit, say).

        `quads` are in unrotated PDF points on that page. When all of them
        can already be seen, nothing moves. Otherwise they are centered,
        but only in the direction in which they were out of sight: a hit
        further down the document does not shift the view sideways.
        """
        if not quads or not 0 <= page_index < len(self._placements):
            return
        placement = self._placements[page_index]
        corners = [corner for quad in quads for corner in placement.quad_on_page(quad)]
        left = min(x for x, _ in corners) + placement.origin_x
        top = min(y for _, y in corners) + placement.origin_y
        right = max(x for x, _ in corners) + placement.origin_x
        bottom = max(y for _, y in corners) + placement.origin_y
        visible = self._visible_scene_rect()
        target = visible.center()  # where the middle of the window is now
        if left < visible.left() or right > visible.right():
            target.setX((left + right) / 2)
        if top < visible.top() or bottom > visible.bottom():
            target.setY((top + bottom) / 2)
        if target != visible.center():
            self.centerOn(target)

    # --- overlays -------------------------------------------------------------

    def set_overlay(
        self, layer: OverlayLayer, page_index: int, quads: Sequence[pymupdf.Quad]
    ) -> None:
        """Show `quads` on a page in the given layer, replacing what that
        layer showed on that page before. No quads: remove it.

        `quads` are in unrotated PDF points, as core hands them out; the
        page's placement turns them into the displayed orientation.
        """
        overlays = self._overlays[layer]
        overlay = overlays.get(page_index)
        if not quads:
            if overlay is not None:
                self._scene.removeItem(overlay)
                del overlays[page_index]
            return
        if overlay is None:
            overlay = QuadOverlay(layer, self._items[page_index])
            overlays[page_index] = overlay
        placement = self._placements[page_index]
        overlay.set_outlines([placement.quad_on_page(quad) for quad in quads])

    def clear_overlay(self, layer: OverlayLayer) -> None:
        """Remove a layer's overlays from every page."""
        for overlay in self._overlays[layer].values():
            self._scene.removeItem(overlay)
        self._overlays[layer].clear()

    def overlay(self, layer: OverlayLayer, page_index: int) -> QuadOverlay | None:
        """The overlay a layer shows on a page, if any (used by the tests)."""
        return self._overlays[layer].get(page_index)

    def overlay_pages(self, layer: OverlayLayer) -> set[int]:
        """The pages on which a layer shows something."""
        return set(self._overlays[layer])

    # --- tools ----------------------------------------------------------------

    def set_tool(self, tool: Tool | None) -> None:
        """Choose what receives mouse clicks and drags on the pages."""
        if self._tool is not None:
            self._tool.reset()
        self._tool = tool
        self._pressed_page = None

    def _page_event(
        self, event: QMouseEvent, page_index: int | None, click_count: int = 1
    ) -> PageEvent | None:
        """Translate a mouse event into "where on which page".

        With page_index None the page under the pointer is used, and the
        result is None when there is none. A drag passes the page it began
        on, so the point may then lie outside that page.
        """
        scene_point = self.mapToScene(event.position().toPoint())
        if page_index is None:
            page_index = geometry.page_at(
                self._placements, scene_point.x(), scene_point.y()
            )
            if page_index is None:
                return None
        placement = self._placements[page_index]
        pdf_point = placement.scene_to_pdf(scene_point.x(), scene_point.y())
        return PageEvent(
            page_index, pdf_point, event.modifiers(), event.button(), click_count
        )

    def _press(self, event: QMouseEvent, click_count: int) -> None:
        """A left press, double-click or triple-click: tell the tool."""
        if self._tool is None:
            return
        page_event = self._page_event(event, None, click_count)
        if page_event is None:
            self._tool.reset()  # a click beside the pages
            return
        self._pressed_page = page_event.page_index
        self._tool.on_press(page_event)

    def _is_third_click(self, event: QMouseEvent) -> bool:
        """True when this press follows a double-click quickly and nearby.

        Qt reports single and double clicks but has no triple-click, so
        the view notes when and where each double-click happened.
        """
        seconds_since = time.monotonic() - self._double_click_time
        distance = (event.position() - self._double_click_spot).manhattanLength()
        in_time = seconds_since * 1000 <= QApplication.doubleClickInterval()
        return in_time and distance <= TRIPLE_CLICK_DISTANCE

    # --- events Qt sends ------------------------------------------------------
    # Qt calls these camelCase methods when something happens to the
    # widget. Overriding one means: "do this instead of, or on top of, the
    # default behavior".

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._press(event, 3 if self._is_third_click(event) else 1)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Qt sends this instead of the second press of a double-click."""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        self._double_click_time = time.monotonic()
        self._double_click_spot = event.position()
        self._press(event, 2)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._tool is None:
            super().mouseMoveEvent(event)
            return
        if self._pressed_page is not None:  # a drag is in progress
            page_event = self._page_event(event, self._pressed_page)
            if page_event is not None:
                self._tool.on_move(page_event)
            return
        hover = self._page_event(event, None)
        if hover is None:
            self.viewport().unsetCursor()  # back to the ordinary arrow
        else:
            self.viewport().setCursor(self._tool.cursor_at(hover))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._tool is None or self._pressed_page is None:
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            page_event = self._page_event(event, self._pressed_page)
            self._pressed_page = None
            if page_event is not None:
                self._tool.on_release(page_event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Ctrl + wheel zooms around the mouse pointer; a plain wheel scrolls."""
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)  # the default: scroll
            return
        # Touchpads send many small movements. Add them up and zoom one
        # step for every full notch.
        self._wheel_units += event.angleDelta().y()
        while self._wheel_units >= WHEEL_NOTCH:
            self._wheel_units -= WHEEL_NOTCH
            self.zoom_in(under_mouse=True)
        while self._wheel_units <= -WHEEL_NOTCH:
            self._wheel_units += WHEEL_NOTCH
            self.zoom_out(under_mouse=True)
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """A different window size shows different pages, and a fit mode
        needs a new zoom."""
        super().resizeEvent(event)
        self._refit()
        if not self._render_timer.isActive():
            self.render_visible_pages()
        self._update_current_page()
