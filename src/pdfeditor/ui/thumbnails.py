"""Thumbnails: the list of small page pictures in the sidebar.

This is the app's first use of Qt's "model/view" idea. A *view*
(ThumbnailView, a QListView) knows how to show a scrolling list, but not
what is in it. For that it asks a *model* (ThumbnailModel): "how many rows
are there?" and, for each row it is about to draw, "what is the text of
row 7? its picture? its size?". The model answers from our data.

The useful consequence: the view only asks about rows that are on screen.
A 1,000 page document therefore costs nothing until its thumbnails scroll
into view, and only then are they drawn, one at a time, in the pauses
between other work so the window never freezes.

There is a third part: a *delegate* (ThumbnailDelegate) paints each row.
So the model knows the data, the view arranges and scrolls the rows, and
the delegate decides what one row looks like.

(Milestone M3 moves the drawing into the render process; reordering pages
by dragging thumbnails arrives with the page commands in M6.)
"""

import math
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from pdfeditor.core import geometry
from pdfeditor.core.document import DocumentModel
from pdfeditor.render.renderer import render_thumbnail

# The box a thumbnail must fit in, in logical pixels. An ordinary page ends
# up THUMBNAIL_WIDTH wide; only a very tall page is limited by the height.
THUMBNAIL_WIDTH = 120
THUMBNAIL_MAX_HEIGHT = 180

ITEM_PADDING = 6  # empty space around each thumbnail
LABEL_HEIGHT = 18  # room for the page number under it
BORDER_COLOR = "#8a8d91"
SELECTION_TINT_ALPHA = 70  # 0 = invisible, 255 = solid

# Pictures kept in memory. Each is about 60 KB, so this is some 25 MB.
MAX_CACHED_THUMBNAILS = 400
# Requests waiting to be drawn. Scrolling fast through a long document asks
# for far more thumbnails than anyone will look at; the oldest requests
# are dropped.
MAX_WAITING = 40

# The type of the `index` Qt passes into a model's methods.
Index = QModelIndex | QPersistentModelIndex


def thumbnail_size(page_width: float, page_height: float) -> QSize:
    """The size of a page's thumbnail in logical pixels.

    A picture cannot be 155.3 pixels high. PyMuPDF rounds such a size up
    to the next whole pixel, so this does the same; the room reserved for
    a thumbnail then matches the picture that arrives later.
    """
    scale = geometry.fit_scale(
        page_width, page_height, THUMBNAIL_WIDTH, THUMBNAIL_MAX_HEIGHT
    )
    return QSize(_whole_pixels(page_width * scale), _whole_pixels(page_height * scale))


def _whole_pixels(length: float) -> int:
    # The small allowance keeps 120.0000001 from becoming 121.
    return max(1, math.ceil(length - 0.001))


class ThumbnailModel(QAbstractListModel):
    """Answers the view's questions about each page's thumbnail."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._document: DocumentModel | None = None
        self._device_pixel_ratio = 1.0
        self._sizes: list[QSize] = []  # thumbnail size of every page
        self._labels: list[str] = []  # the text under every thumbnail
        self._pictures: dict[int, QPixmap] = {}  # the thumbnails drawn so far
        self._blank_pictures: dict[tuple[int, int], QPixmap] = {}
        self._waiting: list[int] = []  # rows still to draw; the last is next
        # A timer with interval 0 fires whenever Qt has nothing else to do.
        # Drawing one thumbnail per firing leaves room for mouse and
        # keyboard events in between.
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._draw_one)

    def set_document(
        self, document: DocumentModel | None, device_pixel_ratio: float = 1.0
    ) -> None:
        """Show the pages of `document`, or nothing when it is None.

        Like the PageView, this asks the document for pages later on, so
        call set_document(None) before the document is closed.
        """
        # beginResetModel/endResetModel tell every attached view "forget
        # all you know about my rows and ask again".
        self.beginResetModel()
        self._timer.stop()
        self._document = document
        self._device_pixel_ratio = device_pixel_ratio
        self._sizes = []
        self._labels = []
        self._pictures = {}
        self._waiting = []
        if document is not None:
            for index, page in enumerate(document.pages()):
                self._sizes.append(thumbnail_size(page.rect.width, page.rect.height))
                self._labels.append(document.page_label(index) or str(index + 1))
        self.endResetModel()

    def drawn_rows(self) -> set[int]:
        """The rows whose thumbnail has been drawn (used by the tests)."""
        return set(self._pictures)

    # --- what Qt calls --------------------------------------------------------
    # These two methods are the whole "model" side of model/view.

    def rowCount(self, parent: Index | None = None) -> int:
        # `parent` only matters for trees: a list has rows at the top level
        # alone, where Qt passes an invalid ("no such row") parent.
        if parent is not None and parent.isValid():
            return 0
        return len(self._sizes)

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """One fact about one row. The `role` says which fact Qt wants."""
        if not index.isValid():
            return None
        row = index.row()
        if role == Qt.ItemDataRole.DisplayRole:  # the text
            return self._labels[row]
        if role == Qt.ItemDataRole.DecorationRole:  # the picture
            return self._picture(row)
        if role == Qt.ItemDataRole.SizeHintRole:  # how much room the row needs
            return QSize(
                THUMBNAIL_WIDTH + 2 * ITEM_PADDING,
                self._sizes[row].height() + LABEL_HEIGHT + 2 * ITEM_PADDING,
            )
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"Page {row + 1}"
        return None

    # --- drawing thumbnails when they are needed --------------------------------

    def _picture(self, row: int) -> QPixmap:
        """The thumbnail of `row`, or blank paper while it is being drawn."""
        picture = self._pictures.get(row)
        if picture is not None:
            return picture
        self._ask_for(row)
        return self._blank_picture(self._sizes[row])

    def _ask_for(self, row: int) -> None:
        if row in self._waiting:
            self._waiting.remove(row)
        self._waiting.append(row)  # asked for most recently: drawn first
        del self._waiting[:-MAX_WAITING]  # keep only the newest requests
        if not self._timer.isActive():
            self._timer.start()

    def _draw_one(self) -> None:
        """Draw the most recently requested thumbnail (called by the timer)."""
        if self._document is None or not self._waiting:
            self._timer.stop()
            return
        row = self._waiting.pop()
        image = render_thumbnail(
            self._document.page(row),
            THUMBNAIL_WIDTH,
            THUMBNAIL_MAX_HEIGHT,
            self._device_pixel_ratio,
        )
        picture = QPixmap.fromImage(image)
        _draw_border(picture)
        if len(self._pictures) >= MAX_CACHED_THUMBNAILS:
            oldest = next(iter(self._pictures))  # a dict remembers the order
            del self._pictures[oldest]
        self._pictures[row] = picture
        # dataChanged tells the view "ask me about this row again".
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])
        if not self._waiting:
            self._timer.stop()

    def _blank_picture(self, size: QSize) -> QPixmap:
        key = (size.width(), size.height())
        picture = self._blank_pictures.get(key)
        if picture is None:
            picture = QPixmap(size)
            picture.fill(Qt.GlobalColor.white)
            _draw_border(picture)
            self._blank_pictures[key] = picture
        return picture


def _draw_border(picture: QPixmap) -> None:
    """A thin frame, so a white page stands out from the white list."""
    size = picture.deviceIndependentSize()
    painter = QPainter(picture)
    painter.setPen(QPen(QColor(BORDER_COLOR), 0))
    # Half a pixel in from each edge puts the one pixel wide line fully
    # inside the picture.
    painter.drawRect(QRectF(0.5, 0.5, size.width() - 1, size.height() - 1))
    painter.end()  # a QPainter must be finished before its picture is used


class ThumbnailDelegate(QStyledItemDelegate):
    """Paints one row: the thumbnail in the middle, the page number below.

    The row of the current page gets a colored background. (Qt's standard
    delegate would tint the whole picture instead, which hides the page.)
    """

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: Index
    ) -> None:
        picture: QPixmap = index.data(Qt.ItemDataRole.DecorationRole)
        label: str = index.data(Qt.ItemDataRole.DisplayRole)
        row = QRectF(option.rect)  # the area of the list this row occupies
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        # save() and restore() put the painter back the way it was, so the
        # pen chosen here does not leak into the next row.
        painter.save()
        if selected:
            # The system's selection color (palette = the colors the user
            # chose in Windows), made mostly see-through: a soft tint.
            tint = QColor(option.palette.highlight().color())
            tint.setAlpha(SELECTION_TINT_ALPHA)
            painter.fillRect(row, tint)
        # On a HiDPI screen a picture has more pixels than the room it
        # takes up; deviceIndependentSize is that room.
        size = picture.deviceIndependentSize()
        left = row.x() + (row.width() - size.width()) / 2
        top = row.y() + ITEM_PADDING
        painter.drawPixmap(QPointF(left, top), picture)
        painter.setPen(option.palette.text().color())
        label_area = QRectF(row.x(), top + size.height(), row.width(), LABEL_HEIGHT)
        painter.drawText(label_area, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()


class ThumbnailView(QListView):
    """The scrolling column of thumbnails. A click asks to go to that page."""

    page_requested = Signal(int)  # the index of the page that was clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setItemDelegate(ThumbnailDelegate(self))
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        # Scroll smoothly instead of jumping a whole thumbnail at a time.
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setSpacing(2)
        scroll_bar_room = 28
        self.setMinimumWidth(THUMBNAIL_WIDTH + 2 * ITEM_PADDING + scroll_bar_room)
        # `clicked` is a mouse click, `activated` is Enter on the keyboard.
        self.clicked.connect(self._request_page)
        self.activated.connect(self._request_page)

    def _request_page(self, index: QModelIndex) -> None:
        self.page_requested.emit(index.row())

    def set_current_page(self, page_index: int) -> None:
        """Mark the thumbnail of the page the user is looking at, and
        scroll the list so that it can be seen."""
        model = self.model()
        if model is None:
            return
        index = model.index(page_index, 0)
        if index.isValid() and index != self.currentIndex():
            self.setCurrentIndex(index)
