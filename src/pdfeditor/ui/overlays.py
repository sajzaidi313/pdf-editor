"""Overlays: colored areas drawn on top of a page.

Search hits and the text selection are not part of the PDF. They are extra
QGraphicsItems laid over the page picture. Each one is a *child* of its
PageItem: a child item uses its parent's coordinates and moves with it, so
an overlay stays glued to its page whatever the scrolling and zoom.
"""

from collections.abc import Sequence
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget


class OverlayLayer(Enum):
    """The kinds of overlay. Each kind has its own color and its own level."""

    SEARCH_HITS = "search_hits"  # every place the searched text was found
    CURRENT_HIT = "current_hit"  # the one hit "Next" and "Previous" are on
    SELECTION = "selection"  # the text selected with the mouse


# Light colors, because they are mixed with the page like a highlighter pen
# (see QuadOverlay.paint).
LAYER_COLORS = {
    OverlayLayer.SEARCH_HITS: "#ffe866",  # yellow
    OverlayLayer.CURRENT_HIT: "#ffa94d",  # orange
    OverlayLayer.SELECTION: "#a9d1ff",  # blue
}

# A higher "z value" is drawn later, so it ends up on top.
LAYER_Z_VALUES = {
    OverlayLayer.SEARCH_HITS: 1.0,
    OverlayLayer.CURRENT_HIT: 2.0,
    OverlayLayer.SELECTION: 3.0,
}

# One shape: its corner points, going around the outline.
Outline = Sequence[tuple[float, float]]


class QuadOverlay(QGraphicsItem):
    """All shapes of one layer on one page, painted in the layer's color."""

    def __init__(self, layer: OverlayLayer, page_item: QGraphicsItem) -> None:
        # Passing the page item as parent makes this overlay its child.
        super().__init__(page_item)
        self.layer = layer
        self._color = QColor(LAYER_COLORS[layer])
        self._path = QPainterPath()
        self.setZValue(LAYER_Z_VALUES[layer])

    def set_outlines(self, outlines: Sequence[Outline]) -> None:
        """Replace the shapes. Each outline is a list of corner points on
        the displayed page (see PagePlacement.quad_on_page)."""
        # A QPainterPath is a collection of shapes that can be filled in
        # one go.
        path = QPainterPath()
        # WindingFill: where two shapes overlap, the overlap is filled too.
        path.setFillRule(Qt.FillRule.WindingFill)
        for outline in outlines:
            path.addPolygon(QPolygonF([QPointF(x, y) for x, y in outline]))
            path.closeSubpath()
        # Qt must be told before an item changes the area it covers.
        self.prepareGeometryChange()
        self._path = path
        self.update()

    @property
    def shape_count(self) -> int:
        """How many shapes this overlay holds (used by the tests)."""
        return len(self._path.toSubpathPolygons())

    # --- what Qt calls --------------------------------------------------------

    def boundingRect(self) -> QRectF:
        return self._path.boundingRect()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        # "Multiply" mixes the color with what is already there the way a
        # highlighter pen does on paper: white becomes the color, black
        # stays black. The text under the overlay remains fully readable.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        painter.fillPath(self._path, self._color)
