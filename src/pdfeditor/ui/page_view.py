"""PageView: the scrolling, zooming canvas that shows the document's pages.

A QGraphicsView is a window onto a QGraphicsScene (see page_item.py). The
scene holds one PageItem per page, stacked top to bottom and measured in
PDF points. Zooming never moves or resizes anything in the scene: it only
changes the view's "transform", the magnification the view looks through.
Qt then stretches the existing page pictures at once, and a moment later
this class replaces them with sharp ones.

For now pages are drawn right here on the UI thread, and only the pages
that are visible. Milestone M3 moves the drawing to a separate process.
"""

from enum import Enum

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QResizeEvent, QTransform, QWheelEvent
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QWidget

from pdfeditor.core import geometry
from pdfeditor.core.document import DocumentModel
from pdfeditor.core.geometry import PagePlacement
from pdfeditor.render.renderer import render_page
from pdfeditor.ui.page_item import PageItem

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
        self._scene.clear()  # removes and deletes every item
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

    # --- events Qt sends ------------------------------------------------------
    # Qt calls these camelCase methods when something happens to the
    # widget. Overriding one means: "do this instead of, or on top of, the
    # default behavior".

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
