"""PageItem: one page on the canvas.

Qt's graphics framework has three parts. A QGraphicsScene is an imaginary
sheet with its own coordinates. QGraphicsItems are the things lying on it.
A QGraphicsView is a window that looks at part of the sheet, scrolled and
zoomed (see page_view.py).

Each PDF page is one PageItem. Its size is the page's size in PDF points,
so the scene is measured in points and never changes when the user zooms;
only the view's magnification does (docs/05 §1).
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from pdfeditor.core.geometry import PagePlacement

SHADOW_OFFSET = 2.0  # points; the shadow peeks out right and below the page
SHADOW_COLOR = "#3a3d40"
BORDER_COLOR = "#2b2d2f"


class PageItem(QGraphicsItem):
    """Paints one page: its picture when there is one, blank paper otherwise."""

    def __init__(self, placement: PagePlacement) -> None:
        super().__init__()
        self.placement = placement
        # The page in the item's own coordinates: (0, 0) is its top-left.
        self._page_rect = QRectF(0, 0, placement.width, placement.height)
        self._image: QImage | None = None
        self._image_scale = 0.0
        # setPos moves the whole item to its place in the scene.
        self.setPos(placement.origin_x, placement.origin_y)

    # --- the picture ----------------------------------------------------------

    def set_image(self, image: QImage, scale: float) -> None:
        """Show `image`, which was drawn at `scale` pixels per point."""
        self._image = image
        self._image_scale = scale
        self.update()  # ask Qt to repaint this item soon

    def clear_image(self) -> None:
        """Forget the picture to free its memory (the page is off screen)."""
        self._image = None
        self._image_scale = 0.0
        self.update()

    def has_image_at(self, scale: float) -> bool:
        """True when the current picture was drawn at exactly this scale."""
        return self._image is not None and self._image_scale == scale

    @property
    def has_image(self) -> bool:
        return self._image is not None

    # --- what Qt calls --------------------------------------------------------
    # These two methods have Qt's own camelCase names because Qt calls them.

    def boundingRect(self) -> QRectF:
        """The area this item may paint in. Qt uses it to decide what to redraw."""
        return self._page_rect.adjusted(0, 0, SHADOW_OFFSET, SHADOW_OFFSET)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the shadow, the paper, the picture and a thin border."""
        shadow = self._page_rect.translated(SHADOW_OFFSET, SHADOW_OFFSET)
        painter.fillRect(shadow, QColor(SHADOW_COLOR))
        painter.fillRect(self._page_rect, Qt.GlobalColor.white)
        if self._image is not None:
            # The picture is stretched to the page's size in points. Right
            # after a zoom it has the wrong pixel size for a moment; smooth
            # scaling makes that look soft instead of blocky.
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(self._page_rect, self._image)
        # A pen of width 0 is "cosmetic": always one screen pixel wide,
        # whatever the zoom.
        painter.setPen(QPen(QColor(BORDER_COLOR), 0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._page_rect)
