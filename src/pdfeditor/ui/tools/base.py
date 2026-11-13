"""Tool: the base class for everything the mouse can do on a page.

The same click means different things depending on what the user is doing:
selecting text now; later placing a note or drawing a line. Instead of one
giant "if the mode is ... elif the mode is ..." inside the PageView, each
behavior is its own class with the same few methods. The view hands every
mouse event to whichever tool is active. This is called the "state
pattern" (docs/02 §5.2). For now there is one tool, SelectTool; switching
between tools arrives with the annotation tools.

Tools never see pixels or scene coordinates. The view converts each mouse
event into a PageEvent first: which page, and where on it in PDF points.
"""

from dataclasses import dataclass

import pymupdf
from PySide6.QtCore import QObject, Qt


@dataclass(frozen=True)
class PageEvent:
    """A mouse event, translated into "where on which page"."""

    page_index: int
    # Unrotated PDF points on that page. While dragging, the point may lie
    # outside the page.
    pdf_point: pymupdf.Point
    modifiers: Qt.KeyboardModifier  # Shift, Ctrl, ... held during the event
    button: Qt.MouseButton
    click_count: int = 1  # 2 for a double-click, 3 for a triple-click


# A tool is a QObject so that subclasses can have signals.
class Tool(QObject):
    """Does nothing by itself. Subclasses override what they need."""

    def on_press(self, event: PageEvent) -> None:
        """The left button went down on a page."""

    def on_move(self, event: PageEvent) -> None:
        """The mouse moved with the button held. `event.page_index` stays
        the page the press was on, even when the pointer has left it."""

    def on_release(self, event: PageEvent) -> None:
        """The left button was let go."""

    def reset(self) -> None:
        """Forget everything in progress: the document changed, or the
        user clicked beside the pages."""

    def cursor_at(self, event: PageEvent) -> Qt.CursorShape:
        """The mouse pointer to show while hovering at this spot."""
        return Qt.CursorShape.ArrowCursor
