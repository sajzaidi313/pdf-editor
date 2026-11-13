"""FindController: runs a search and steps through its hits.

Searching a long document takes a while, and Qt can only react to the
mouse and keyboard between two pieces of our code. If the whole document
were searched in one go, the window would freeze until the end.

So the search is cut into small pieces: one page per piece. A timer with
interval 0 fires whenever Qt has nothing else to do; each firing searches
one page and returns. Typing, scrolling and "Next" keep working meanwhile,
and hits show up as they are found.

(Milestone M3 moves the searching itself into the background process.)
"""

from PySide6.QtCore import QObject, QTimer, Signal

from pdfeditor.core import search
from pdfeditor.core.document import DocumentModel
from pdfeditor.core.search import SearchHit, SearchResults
from pdfeditor.ui.find_bar import FindBar, find_status
from pdfeditor.ui.overlays import OverlayLayer
from pdfeditor.ui.page_view import PageView


class FindController(QObject):
    """Connects the find bar, the document and the page view."""

    finished = Signal()  # every page has been searched

    def __init__(
        self,
        model: DocumentModel,
        view: PageView,
        bar: FindBar,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._view = view
        self._bar = bar
        self.results = SearchResults()
        self.current: SearchHit | None = None  # the hit Next/Previous are on
        self._needle = ""  # the text being searched for
        self._pages_left: list[int] = []  # pages still to search, in order
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._search_one_page)
        bar.search_requested.connect(self.start)
        bar.next_requested.connect(self.find_next)
        bar.previous_requested.connect(self.find_previous)
        bar.closed.connect(self.clear)

    @property
    def is_searching(self) -> bool:
        return self._timer.isActive()

    # --- starting and stopping ----------------------------------------------------

    def start(self, needle: str) -> None:
        """Search the whole document for `needle`, replacing any earlier search."""
        self.clear()
        if not search.normalize_needle(needle) or self._view.page_count == 0:
            return
        self._needle = needle
        # Begin with the page the user is looking at and go on to the end,
        # then take the pages before it. The first hit found is then the
        # one nearest ahead, and it can be shown at once.
        first = self._view.current_page
        self._pages_left = [*range(first, self._model.page_count), *range(first)]
        self._timer.start()
        self._show_status()

    def clear(self) -> None:
        """Stop searching and forget all hits. Must be called before the
        document is closed or replaced."""
        self._timer.stop()
        self._pages_left = []
        self._needle = ""
        self.results = SearchResults()
        self.current = None
        self._view.clear_overlay(OverlayLayer.SEARCH_HITS)
        self._view.clear_overlay(OverlayLayer.CURRENT_HIT)
        self._bar.set_status("")

    def _search_one_page(self) -> None:
        """Called by the timer: search the next page in line."""
        page_index = self._pages_left.pop(0)
        page_text = self._model.page_text(page_index, remember=False)
        hits = search.find_in_page(page_text, self._needle, page_index)
        if hits:
            self.results.add(hits)
            quads = [quad for hit in hits for quad in hit.quads]
            self._view.set_overlay(OverlayLayer.SEARCH_HITS, page_index, quads)
            if self.current is None:
                self._go_to(hits[0])
        if not self._pages_left:
            self._timer.stop()
            self._show_status()
            self.finished.emit()
        elif hits:
            self._show_status()

    # --- stepping through the hits ------------------------------------------------

    def find_next(self) -> None:
        self._step(forward=True)

    def find_previous(self) -> None:
        self._step(forward=False)

    def _step(self, forward: bool) -> None:
        if len(self.results) == 0:
            # Nothing found yet. If nothing was searched either (a new
            # document was opened, say), search for what the box holds.
            if not self.is_searching and not self._needle:
                self.start(self._bar.text())
            return
        if self.current is None:
            return
        if forward:
            self._go_to(self.results.after(self.current))
        else:
            self._go_to(self.results.before(self.current))

    def _go_to(self, hit: SearchHit) -> None:
        """Make `hit` the current one: mark it and bring it into view."""
        self.current = hit
        self._view.clear_overlay(OverlayLayer.CURRENT_HIT)
        self._view.set_overlay(OverlayLayer.CURRENT_HIT, hit.page_index, hit.quads)
        self._view.scroll_to(hit.page_index, hit.quads)
        self._show_status()

    def _show_status(self) -> None:
        number = 0 if self.current is None else self.results.number_of(self.current)
        self._bar.set_status(find_status(number, len(self.results), self.is_searching))
