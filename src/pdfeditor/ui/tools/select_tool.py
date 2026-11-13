"""SelectTool: select text with the mouse.

Drag to select, double-click for a word, triple-click for a line. The tool
only decides *which characters* are selected; core/text.py does the
measuring and the PageView draws the result as an overlay.

A selection stays within one page (docs/11, 2026-11-13).
"""

from PySide6.QtCore import QObject, Qt, Signal

from pdfeditor.core import text
from pdfeditor.core.document import DocumentModel
from pdfeditor.ui.overlays import OverlayLayer
from pdfeditor.ui.page_view import PageView
from pdfeditor.ui.tools.base import PageEvent, Tool


class SelectTool(Tool):
    """Keeps the current text selection and shows it on the view."""

    # Emitted whenever the selected text changes (the main window uses it
    # to switch Edit > Copy on and off).
    selection_changed = Signal()
    # Emitted with the page index when the user tries to select on a page
    # that has no text, such as a scan.
    page_without_text = Signal(int)

    def __init__(
        self, model: DocumentModel, view: PageView, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._view = view
        self._page: int | None = None  # the page the selection is on
        self._range: tuple[int, int] | None = None  # offsets, see core/text.py
        # Offset where the current drag began; None when no drag is going on.
        self._anchor: int | None = None

    # --- what is selected -------------------------------------------------------

    @property
    def has_selection(self) -> bool:
        return self._range is not None

    @property
    def selection_page(self) -> int | None:
        """Index of the page the selection is on, or None without one."""
        return self._page if self.has_selection else None

    def selected_text(self) -> str:
        """The selected characters, one line per line on the page."""
        if self._page is None or self._range is None:
            return ""
        return text.text_in_range(self._model.page_text(self._page), *self._range)

    # --- mouse ------------------------------------------------------------------

    def on_press(self, event: PageEvent) -> None:
        self._select(event.page_index, None)  # a new click drops the old selection
        self._anchor = None
        page_text = self._model.page_text(event.page_index)
        if page_text.is_empty:
            self.page_without_text.emit(event.page_index)
            return
        if event.click_count == 2:
            self._select(
                event.page_index, text.word_range_at(page_text, event.pdf_point)
            )
        elif event.click_count >= 3:
            self._select(
                event.page_index, text.line_range_at(page_text, event.pdf_point)
            )
        else:
            self._anchor = text.offset_at(page_text, event.pdf_point)

    def on_move(self, event: PageEvent) -> None:
        if self._anchor is None:
            return
        page_text = self._model.page_text(event.page_index)
        here = text.offset_at(page_text, event.pdf_point)
        if here is None:
            return
        # Dragging backwards is fine: the range always runs low to high.
        selected = (min(self._anchor, here), max(self._anchor, here))
        self._select(event.page_index, selected)

    def on_release(self, event: PageEvent) -> None:
        self._anchor = None  # the drag is over; the selection stays

    def reset(self) -> None:
        self._anchor = None
        self._select(None, None)

    def cursor_at(self, event: PageEvent) -> Qt.CursorShape:
        """An I-beam over text, the ordinary arrow elsewhere."""
        page_text = self._model.page_text(event.page_index)
        if text.is_over_text(page_text, event.pdf_point):
            return Qt.CursorShape.IBeamCursor
        return Qt.CursorShape.ArrowCursor

    # --- helpers ----------------------------------------------------------------

    def _select(self, page: int | None, selected: tuple[int, int] | None) -> None:
        """Make `selected` on `page` the selection, and show it."""
        if selected is not None and selected[0] == selected[1]:
            selected = None  # nothing between the two ends
        if page is None or selected is None:
            page, selected = None, None
        if (page, selected) == (self._page, self._range):
            return
        if page != self._page:
            self._view.clear_overlay(OverlayLayer.SELECTION)
        self._page, self._range = page, selected
        if page is not None and selected is not None:
            quads = text.quads_in_range(self._model.page_text(page), *selected)
            self._view.set_overlay(OverlayLayer.SELECTION, page, quads)
        self.selection_changed.emit()
